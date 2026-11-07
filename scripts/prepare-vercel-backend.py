"""Stage the Python API without credentials, local data or neural caches."""
from pathlib import Path
import shutil
root=Path(__file__).resolve().parents[1]
stage=root/'runtime/vercel/backend'
stage.mkdir(parents=True,exist_ok=True)
for name in ['app','ai','ml','alembic']:
    shutil.copytree(root/'backend'/name,stage/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copy2(root/'backend/alembic.ini',stage/'alembic.ini')
shutil.copytree(root/'backend/runtime/models',stage/'models',dirs_exist_ok=True)
shutil.copytree(root/'deploy/vercel',stage,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
# Superseded files from earlier staging runs must not override the uv lockfile.
for filename in ['requirements.txt','uv.toml','index.py']:
    (stage/filename).unlink(missing_ok=True)
print('Vercel backend prepared in runtime/vercel/backend')
