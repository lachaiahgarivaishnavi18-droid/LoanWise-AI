"""Administrative commands; no credentials in arguments or logs."""
import argparse
import getpass
from pathlib import Path
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, delete
from .database import Base, engine, SessionLocal,ensure_schema
from .models import User, Document, Chunk, Session
from .security import hash_password, audit
from .seed import seed
from .config import settings
from ai.documents import extract, index_document


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('seed')
    sub.add_parser('create-admin')
    repayment_import=sub.add_parser('import-synthetic-repayments')
    repayment_import.add_argument('file')
    ingest = sub.add_parser('ingest')
    ingest.add_argument('file')
    ingest.add_argument('--product', type=int, required=True)
    ingest.add_argument('--version', required=True)
    ingest.add_argument('--effective-date', required=True)
    sub.add_parser('retention-preview')
    sub.add_parser('purge-expired-documents')
    args = parser.parse_args()
    ensure_schema()
    with SessionLocal() as db:
        from .normalized_services import initialize_roles
        initialize_roles(db)
        if args.command == 'seed':
            seed(db); print('Seed initialized. Generated local credentials: runtime/demo-credentials.txt')
        elif args.command=='import-synthetic-repayments':
            from .normalized_services import import_synthetic_repayments
            count=import_synthetic_repayments(db,Path(args.file))
            audit(db,None,'import_synthetic_repayments',count);db.commit()
            print(f'Imported {count} synthetic repayment observations; existing records preserved.')
        elif args.command == 'create-admin':
            email = input('Admin email: ').strip().lower()
            name = input('Admin name: ').strip()
            password = getpass.getpass('Password (10+ characters): ')
            if len(password) < 10 or '@' not in email or not name:
                raise ValueError('Valid email, name and password required')
            if db.scalar(select(User).where(User.email == email)):
                raise ValueError('User already exists')
            user = User(email=email, name=name, password_hash=hash_password(password), role='admin')
            db.add(user); db.flush(); audit(db, user, 'bootstrap_admin', user.id); db.commit(); print('Administrator created')
        elif args.command == 'ingest':
            from .models import Product
            from datetime import date
            date.fromisoformat(args.effective_date)
            if not db.get(Product, args.product):
                raise ValueError('Product does not exist')
            user = db.scalar(select(User).where(User.role == 'admin'))
            if not user:
                raise ValueError('Create an administrator first')
            file = Path(args.file)
            pages, extraction = extract(file.name, file.read_bytes())
            document = Document(owner_id=user.id, title=file.name, kind='policy', path='', product_id=args.product, version=args.version, effective_date=args.effective_date, pages=pages, extraction=extraction, synthetic=settings.demo_mode, reviewed=False)
            db.add(document); db.flush(); audit(db, user, 'cli_ingest_pending_review', document.id); db.commit()
            print(f'Document {document.id} ingested. Review it in Knowledge Base before indexing.')
        else:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=settings.retention_days)).isoformat()
            docs = db.scalars(select(Document).where(Document.kind == 'financial', Document.created_at < cutoff)).all()
            print(f'{len(docs)} financial documents exceed the configured retention period.')
            if args.command == 'purge-expired-documents':
                root = Path(settings.storage_dir).resolve()
                for doc in docs:
                    doc.content_bytes=None
                    if doc.path:
                        path = Path(doc.path).resolve()
                        if not path.is_relative_to(root):
                            raise ValueError('Storage containment check failed')
                        path.unlink(missing_ok=True)
                    for chunk in db.scalars(select(Chunk).where(Chunk.document_id==doc.id)).all():
                        chunk.text='';chunk.active=False
                    for page in doc.page_records:
                        page.text='';page.active=False
                        for entity in page.entities:
                            entity.quote='';entity.value=None;entity.active=False;entity.verified=False
                            for correction in entity.corrections:
                                correction.previous_value=None;correction.corrected_value=None;correction.reason='Purged under source retention policy'
                    doc.extraction = {'warnings': ['Source text purged by retention policy'], 'entities': []}
                    doc.reviewed=False
                    doc.path = ''
                    audit(db, None, 'retention_purge_document', doc.id)
                db.execute(delete(Session).where(Session.expires < datetime.now(timezone.utc).isoformat()))
                db.commit()


if __name__ == '__main__':
    main()
