import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT))
work=Path('/tmp/loanwise');work.mkdir(parents=True,exist_ok=True)
os.chdir(work)
os.environ.setdefault('RUNTIME_DIR',str(work/'runtime'))
os.environ.setdefault('STORAGE_DIR',str(work/'documents'))
os.environ.setdefault('DATA_DIR',str(work/'data'))
os.environ.setdefault('MODEL_DIR',str(ROOT/'models'))
os.environ.setdefault('DOCUMENT_STORAGE','database')
os.environ.setdefault('DEMO_MODE','false')
os.environ.setdefault('COOKIE_SECURE','true')
os.environ.setdefault('PARSER_PROCESS_MODE','subprocess')
from app.main import app
