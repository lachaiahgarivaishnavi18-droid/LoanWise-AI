from app.config import settings,Settings
from app.database import SessionLocal
from app.models import Document


def test_database_originals_survive_new_session_and_reextract(admin,monkeypatch):
    monkeypatch.setattr(settings,'document_storage','database')
    source=b'Monthly income: 50000\nMonthly debt: 12000'
    response=admin.post('/api/documents/upload',files={'file':('cloud-income.txt',source)},data={'application_id':499})
    assert response.status_code==201
    identifier=response.json()['id']
    assert 'content_bytes' not in response.json()
    with SessionLocal() as db:
        document=db.get(Document,identifier)
        assert document.path==''
        assert document.content_bytes==source
    download=admin.get(f'/api/documents/{identifier}/download')
    assert download.status_code==200 and download.content==source
    extracted=admin.post(f'/api/documents/{identifier}/extract')
    assert extracted.status_code==200
    assert 'Monthly income: 50000' in extracted.json()['pages'][0]['text']
    assert not extracted.json()['extraction']['verified']


def test_neon_postgresql_url_uses_psycopg_driver():
    configuration=Settings(database_url='postgresql://example:unused@localhost/example?sslmode=require')
    assert configuration.database_url.startswith('postgresql+psycopg://')
    assert configuration.database_url.endswith('?sslmode=require')
