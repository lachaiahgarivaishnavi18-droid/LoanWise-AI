from alembic import context
from sqlalchemy import create_engine,event
from app.config import settings
from app.database import Base
from app import models

config = context.config
if context.is_offline_mode():
    context.configure(url=settings.database_url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine=create_engine(settings.database_url,hide_parameters=True)
    if settings.database_url.startswith('sqlite'):
        @event.listens_for(engine,'connect')
        def transactional_sqlite(dbapi_connection,record):
            dbapi_connection.isolation_level=None
        @event.listens_for(engine,'begin')
        def begin_sqlite(connection):
            connection.exec_driver_sql('BEGIN')
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=settings.database_url.startswith('sqlite'),transactional_ddl=True)
        with context.begin_transaction():
            context.run_migrations()
