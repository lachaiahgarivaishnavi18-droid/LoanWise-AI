import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from .database import get_db
from .models import Session as AuthSession, User, Applicant, Application, Audit


def hash_password(password):
    salt = secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return f'{salt}:{value}'


def verify_password(password, stored):
    salt, expected = stored.split(':')
    value = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return hmac.compare_digest(value, expected)


def current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get('loanwise_session', '')
    session = db.get(AuthSession, hashlib.sha256(token.encode()).hexdigest())
    if not session or session.expires < datetime.now(timezone.utc).isoformat():
        raise HTTPException(401, 'Please sign in')
    return db.get(User, session.user_id)


def roles(*allowed):
    def check(user=Depends(current_user)):
        if user.role not in allowed:
            raise HTTPException(403, 'This operation requires an authorized role')
        return user
    return check


def applicant_access(db, user, applicant_id):
    item = db.get(Applicant, applicant_id)
    if not item or (user.role != 'admin' and item.owner_id != user.id):
        raise HTTPException(404, 'Applicant not found')
    return item


def application_access(db, user, application_id):
    item = db.get(Application, application_id)
    if not item:
        raise HTTPException(404, 'Application not found')
    applicant_access(db, user, item.applicant_id)
    return item


def policy_access(db,user,document):
    from .normalized_models import DocumentPermission
    return bool(document and (user.role=='admin' or db.get(DocumentPermission,(document.id,user.role)) is not None))


def evidence_access(db,user,value):
    """Recheck current source permissions even for historical snapshots and traces."""
    from .models import Document
    if isinstance(value,dict):
        identifier=value.get('document_id')
        if isinstance(identifier,int):
            document=db.get(Document,identifier)
            if not document or (document.kind=='policy' and not policy_access(db,user,document)):
                raise HTTPException(404,'Supporting source is unavailable to this role')
        for item in value.values():
            evidence_access(db,user,item)
    elif isinstance(value,list):
        for item in value:
            evidence_access(db,user,item)


def audit(db, user, action, resource):
    db.add(Audit(user_id=user.id if user else None, action=action, resource=str(resource)))
