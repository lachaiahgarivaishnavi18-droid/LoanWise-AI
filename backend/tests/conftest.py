import os
import tempfile
from pathlib import Path

ROOT = Path(tempfile.mkdtemp(prefix='loanwise-test-'))
os.environ['DATABASE_URL'] = os.environ.get('LOANWISE_TEST_DATABASE_URL','sqlite:///' + str(ROOT / 'test.db'))
os.environ['STORAGE_DIR'] = str(ROOT / 'documents')
os.environ['DEMO_MODE'] = 'false'
os.environ['MODEL_DIR'] = str(ROOT / 'models')
os.environ['RUNTIME_DIR'] = str(ROOT / 'runtime')
os.environ['DATA_DIR'] = str(ROOT / 'data')

import pytest
from fastapi.testclient import TestClient
from app.main import app, buckets
from app.database import Base, engine, SessionLocal
from app.seed import seed


@pytest.fixture(scope='session')
def client():
    with TestClient(app) as client:
        with SessionLocal() as db:
            seed(db)
        yield client
    engine.dispose()


@pytest.fixture
def admin(client):
    buckets.clear()
    credentials = (ROOT / 'runtime/demo-credentials.txt').read_text().splitlines()
    password = credentials[1].removeprefix('Password: ')
    response = client.post('/api/auth/login', json={'email': 'demo@loanwise.local', 'password': password})
    assert response.status_code == 200
    yield client
    client.post('/api/auth/logout')
