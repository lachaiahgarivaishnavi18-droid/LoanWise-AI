from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

Path('runtime').mkdir(exist_ok=True)
engine = create_engine(settings.database_url, hide_parameters=True, connect_args={'check_same_thread': False} if settings.database_url.startswith('sqlite') else {})
if settings.database_url.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def foreign_keys(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionLocal() as db:
        yield db


def ensure_schema():
    """Fresh local databases are stamped; existing schemas must use the upgrade command."""
    from sqlalchemy import inspect
    from alembic.config import Config
    from alembic import command
    inspector=inspect(engine)
    if inspector.has_table('loan_applications') and 'profile' in {c['name'] for c in inspector.get_columns('loan_applications')}:
        raise RuntimeError('Legacy database detected. Back up the database and run python -m alembic upgrade head before starting the service.')
    versioned=inspector.has_table('alembic_version')
    Base.metadata.create_all(engine)
    if not versioned:
        root=Path(__file__).resolve().parents[1]
        config=Config(str(root/'alembic.ini'))
        config.set_main_option('script_location',str(root/'alembic'))
        command.stamp(config,'head')
