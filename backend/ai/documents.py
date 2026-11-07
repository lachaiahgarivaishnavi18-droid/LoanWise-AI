import csv
import io
import json
import re
from pathlib import Path
from fastapi import HTTPException

MAX_BYTES = 8 * 1024 * 1024
ALLOWED = {'.pdf', '.docx', '.txt', '.csv', '.json', '.png', '.jpg', '.jpeg'}
INJECTION = re.compile(r'ignore\s+(all\s+)?(previous|prior|system)|system\s*prompt|reveal\s+(secrets|password)|you are now|<\|system', re.I)


def extract(filename, data):
    from app.config import settings
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED or not data or len(data) > MAX_BYTES:
        raise HTTPException(422, 'Use a nonempty PDF, DOCX, TXT, CSV, JSON, PNG or JPEG file up to 8 MB')
    config={'enabled':settings.ocr_enabled,'max_pages':settings.ocr_max_pages,'max_pixels':settings.ocr_max_pixels,'timeout':settings.parser_timeout_seconds,'memory_mb':settings.parser_memory_mb}
    if suffix in {'.pdf','.docx','.png','.jpg','.jpeg'}:
        from .parser_worker import parse_isolated
        return parse_isolated(filename,data,config)
    return extract_local(filename,data,config)


def extract_local(filename,data,config):
    suffix=Path(filename).suffix.lower()
    try:
        if suffix == '.pdf':
            if not data.startswith(b'%PDF-'):
                raise ValueError('Invalid PDF signature')
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            if len(reader.pages) > 200:
                raise ValueError('Maximum 200 pages')
            pages = [{'page': i + 1, 'text': p.extract_text() or ''} for i, p in enumerate(reader.pages)]
            if config['enabled']:
                from .ocr import scan_pdf
                pages=scan_pdf(data,pages,config)
        elif suffix in {'.png','.jpg','.jpeg'}:
            if not config['enabled']:
                raise HTTPException(422,'Image upload requires OCR_ENABLED=true')
            from .ocr import image_page
            pages=[image_page(data,config)]
        elif suffix == '.docx':
            import zipfile
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if sum(x.file_size for x in archive.infolist()) > 32 * 1024 * 1024:
                    raise ValueError('Expanded document too large')
            from docx import Document
            doc = Document(io.BytesIO(data))
            pages = [{'page': 1, 'text': '\n'.join(p.text for p in doc.paragraphs)}]
        else:
            content = data.decode('utf-8-sig')
            if '\x00' in content:
                raise ValueError('Binary content')
            if suffix == '.json':
                content = json.dumps(json.loads(content), indent=2)
            if suffix == '.csv':
                content = '\n'.join(' | '.join(row) for row in csv.reader(io.StringIO(content)))
            pages = [{'page': 1, 'text': content}]
        if sum(len(p['text']) for p in pages) > 2_000_000:
            raise ValueError('Extracted text too large')
        text = '\n'.join(p['text'] for p in pages)
        warnings = []
        ocr_pages=[p for p in pages if p.get('method')=='local_ocr']
        if ocr_pages:
            warnings.append('OCR-derived values are unverified. Recognition scores are not calibrated financial confidence; human source review is required.')
        if suffix=='.docx':
            warnings.append('DOCX uses logical extraction pages; rendered page numbers are not available.')
        if INJECTION.search(text):
            warnings.append('Potential prompt injection: document quarantined from retrieval.')
        if not text.strip():
            warnings.append('No text extracted. OCR is disabled or could not recognize the page; manual review is required.')
        entities = []
        for page in pages:
            for match in re.finditer(r'\b(monthly\s*income|salary|monthly\s*debt)\s*[:=]\s*([\d,]+(?:\.\d+)?)', page['text'], re.I):
                field={'monthlyincome':'monthly income','monthlydebt':'monthly debt','salary':'salary'}[re.sub(r'\s+','',match[1].lower())]
                entities.append({'field': field, 'value': float(match[2].replace(',', '')), 'page': page['page'], 'quote': match[0], 'verified': False})
        return pages, {'entities': entities, 'warnings': warnings, 'method': 'text extraction + local OCR; rule-based candidates' if ocr_pages else 'text extraction; rule-based candidates', 'confidence': None, 'verified': False, 'quarantined': bool(INJECTION.search(text))}
    except HTTPException:
        raise
    except ValueError as error:
        if str(error) in ['OCR image exceeds the configured pixel budget','Scanned PDF exceeds the configured OCR page budget','Rendered PDF page exceeds the configured pixel budget']:
            raise HTTPException(422,str(error))
        raise HTTPException(422, 'Document could not be parsed safely; check its format and size')
    except Exception:
        raise HTTPException(422, 'Document could not be parsed safely; check its format and size')


def index_document(db, document):
    from sqlalchemy import update
    from app.models import Chunk
    db.execute(update(Chunk).where(Chunk.document_id == document.id).values(active=False))
    if document.extraction.get('quarantined') or not document.reviewed:
        return 0
    count = 0
    for page in document.pages:
        text = page['text']
        source_page = next(p for p in document.page_records if p.page_number == page['page'] and p.active)
        for start in range(0, len(text), 800):
            part = text[start:start + 1000].strip()
            if part:
                db.add(Chunk(source_page=source_page, active=True, section=part.split('\n')[0][:120], text=part))
                count += 1
    db.flush()
    return count
