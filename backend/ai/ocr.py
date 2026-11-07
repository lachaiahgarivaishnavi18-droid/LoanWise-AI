"""Local CPU OCR; raw recognition scores are not verification or calibrated confidence."""
import io
import numpy as np


def recognize(image,config):
    from rapidocr_onnxruntime import RapidOCR
    import cv2
    cv2.setNumThreads(1)
    if image.width*image.height>config['max_pixels']:
        raise ValueError('OCR image exceeds the configured pixel budget')
    engine=RapidOCR(intra_op_num_threads=1,inter_op_num_threads=1)
    result,_=engine(np.asarray(image.convert('RGB')))
    lines=result or []
    return '\n'.join(str(line[1]) for line in lines), float(np.mean([float(line[2]) for line in lines])) if lines else None


def image_page(data,config):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS=config['max_pixels']
    with Image.open(io.BytesIO(data)) as image:
        if image.format not in ('PNG','JPEG'):
            raise ValueError('Only PNG and JPEG images are supported')
        if image.width*image.height>config['max_pixels']:
            raise ValueError('OCR image exceeds the configured pixel budget')
        image.load()
        text,confidence=recognize(image,config)
    return {'page':1,'text':text,'method':'local_ocr','ocr_confidence':confidence}


def scan_pdf(data,pages,config):
    missing=[p for p in pages if not p['text'].strip()]
    if len(missing)>config['max_pages']:
        raise ValueError('Scanned PDF exceeds the configured OCR page budget')
    if not missing:
        return pages
    import pypdfium2 as pdfium
    with pdfium.PdfDocument(data) as pdf:
        for record in missing:
            page=pdf[record['page']-1]
            try:
                width,height=page.get_size()
                scale=200/72
                if width*height*scale*scale>config['max_pixels']:
                    raise ValueError('Rendered PDF page exceeds the configured pixel budget')
                bitmap=page.render(scale=scale)
                try:
                    image=bitmap.to_pil()
                    try:
                        record['text'],record['ocr_confidence']=recognize(image,config)
                    finally:
                        image.close()
                finally:
                    bitmap.close()
                record['method']='local_ocr'
            finally:
                page.close()
    return pages
