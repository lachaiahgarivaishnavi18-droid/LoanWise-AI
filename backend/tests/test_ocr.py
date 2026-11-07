import io
from PIL import Image,ImageDraw,ImageFont
from ai.documents import extract
from app.config import settings
import pytest


def scan():
    image=Image.new('RGB',(1500,450),'white')
    drawing=ImageDraw.Draw(image)
    font=None
    for path in ['C:/Windows/Fonts/arial.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
        try:
            font=ImageFont.truetype(path,52);break
        except OSError:
            pass
    if font is None:
        font=ImageFont.load_default(size=52)
    drawing.text((70,80),'SYNTHETIC INCOME RECORD',font=font,fill='black')
    drawing.text((70,180),'Monthly income: 50000',font=font,fill='black')
    drawing.text((70,280),'Monthly debt: 12000',font=font,fill='black')
    return image


def test_real_local_image_ocr_is_unverified():
    data=io.BytesIO();scan().save(data,format='PNG')
    pages,result=extract('synthetic-scan.png',data.getvalue())
    assert pages[0]['method']=='local_ocr'
    assert '50000' in pages[0]['text']
    assert 0<=pages[0]['ocr_confidence']<=1
    assert result['verified'] is False
    assert result['confidence'] is None
    assert any('unverified' in warning for warning in result['warnings'])
    income=next(entity for entity in result['entities'] if entity['field']=='monthly income')
    assert income['value']==50000
    assert income['page']==1
    assert not income['verified']


def test_scanned_pdf_uses_page_level_ocr():
    data=io.BytesIO();scan().save(data,format='PDF')
    pages,result=extract('synthetic-scanned.pdf',data.getvalue())
    assert pages[0]['page']==1
    assert pages[0]['method']=='local_ocr'
    assert '50000' in pages[0]['text']
    assert any(entity['value']==12000 for entity in result['entities']), repr((pages,result))


def test_ocr_disabled_rejects_image(monkeypatch):
    monkeypatch.setattr(settings,'ocr_enabled',False)
    data=io.BytesIO();scan().save(data,format='PNG')
    with pytest.raises(Exception) as error:
        extract('synthetic.png',data.getvalue())
    assert error.value.status_code==422
    assert 'OCR_ENABLED' in error.value.detail


def test_oversize_pixels_are_rejected(monkeypatch):
    monkeypatch.setattr(settings,'ocr_max_pixels',1000)
    data=io.BytesIO();scan().save(data,format='PNG')
    with pytest.raises(Exception) as error:
        extract('synthetic.png',data.getvalue())
    assert error.value.status_code==422
