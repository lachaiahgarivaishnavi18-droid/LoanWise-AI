import os
import subprocess
import sys
from sqlalchemy import create_engine, inspect


def test_upgrade_is_repeatable_and_creates_tables():
    from conftest import ROOT
    url='sqlite:///'+str(ROOT/'migration.db')
    env={**os.environ,'DATABASE_URL':url}
    for _ in range(2):
        result=subprocess.run([sys.executable,'-m','alembic','upgrade','head'],env=env,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
    engine=create_engine(url)
    assert 'loan_applications' in inspect(engine).get_table_names()
    assert 'final_human_decisions' in inspect(engine).get_table_names()
    assert inspect(engine).get_foreign_keys('loan_applications')
    from app.database import Base
    inspector=inspect(engine)
    for name,table in Base.metadata.tables.items():
        assert set(table.c.keys())=={column['name'] for column in inspector.get_columns(name)}
    engine.dispose()


def test_failed_sqlite_upgrade_rolls_back_schema_changes():
    from conftest import ROOT
    from app.schema_v1 import metadata
    from sqlalchemy import text
    url='sqlite:///'+str(ROOT/'failed-upgrade.db')
    engine=create_engine(url)
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(metadata.tables['users'].insert().values(id=1,email='rollback@example.test',name='Synthetic invalid legacy fixture',password_hash='not-a-login',role='admin'))
        connection.execute(metadata.tables['applicants'].insert().values(id=1,owner_id=1,name='Synthetic applicant',reference='ROLLBACK',synthetic=True,created_at='2026-11-07T00:00:00+00:00'))
        connection.execute(metadata.tables['loan_products'].insert().values(id=1,name='Rollback product',description='Synthetic test',policy_version='1',jurisdiction='DEMO',criteria=[],synthetic=True))
        connection.execute(metadata.tables['loan_applications'].insert().values(id=1,applicant_id=1,product_id=1,amount=100000,tenure_months=12,annual_rate=0,profile=['invalid legacy profile'],status='Awaiting assessment',synthetic=True,created_at='2026-11-07T00:00:00+00:00'))
        connection.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)'))
        connection.execute(text("INSERT INTO alembic_version VALUES ('0001')"))
    result=subprocess.run([sys.executable,'-m','alembic','upgrade','head'],env={**os.environ,'DATABASE_URL':url},capture_output=True,text=True)
    assert result.returncode!=0
    inspector=inspect(engine)
    assert 'profile' in {c['name'] for c in inspector.get_columns('loan_applications')}
    assert 'active_version_id' not in {c['name'] for c in inspector.get_columns('loan_products')}
    with engine.connect() as connection:
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar()=='0001'
    engine.dispose()


def test_legacy_financial_data_is_migrated_without_json_columns():
    import json
    from conftest import ROOT
    from app.schema_v1 import metadata
    url=os.environ.get('LOANWISE_LEGACY_DATABASE_URL','sqlite:///'+str(ROOT/'legacy.db'))
    engine=create_engine(url)
    metadata.create_all(engine)
    quote='Minimum verified monthly income: 25000. Operator: min.'
    rule={'key':'monthly_income','label':'Minimum verified monthly income','operator':'min','threshold':25000,'document_id':7,'page':1,'quote':quote}
    profile={'monthly_income':50000,'monthly_debt':0,'monthly_expenses':10000,'employment_months':24,'credit_score':720,'credit_utilization':30,'missed_payments':0,'income_verified':True,'credit_verified':True,'income_conflict':False}
    timestamp='2026-11-07T00:00:00+00:00'
    with engine.begin() as connection:
        connection.execute(metadata.tables['users'].insert().values(id=1,email='migration@example.test',name='Synthetic migration record',password_hash='not-a-login',role='admin'))
        connection.execute(metadata.tables['applicants'].insert().values(id=1,owner_id=1,name='Synthetic applicant',reference='MIG-1',synthetic=True,created_at=timestamp))
        connection.execute(metadata.tables['loan_products'].insert().values(id=1,name='Synthetic product',description='Migration fixture',policy_version='1',jurisdiction='DEMO',criteria=[rule],synthetic=True))
        connection.execute(metadata.tables['loan_applications'].insert().values(id=1,applicant_id=1,product_id=1,amount=100000,tenure_months=12,annual_rate=0,profile=profile,status='Awaiting assessment',synthetic=True,created_at=timestamp))
        connection.execute(metadata.tables['financial_documents'].insert().values(id=7,owner_id=1,application_id=None,title='Synthetic source',kind='policy',path='',version='1',effective_date='2026-01-01',product_id=1,pages=[{'page':1,'text':quote}],extraction={'entities':[],'warnings':[],'quarantined':False},reviewed=True,synthetic=True,created_at=timestamp))
        connection.execute(metadata.tables['financial_documents'].insert().values(id=8,owner_id=1,application_id=1,title='Synthetic income source',kind='financial',path='',version='1',effective_date=None,product_id=None,pages=[{'page':1,'text':'Monthly income: 50000'}],extraction={'entities':[{'field':'monthly income','value':50000,'page':1,'quote':'Monthly income: 50000','verified':False}],'warnings':['Manual review required'],'quarantined':False},reviewed=False,synthetic=True,created_at=timestamp))
        from sqlalchemy import text
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        connection.execute(text("INSERT INTO alembic_version VALUES ('0001')"))
    result=subprocess.run([sys.executable,'-m','alembic','upgrade','head'],env={**os.environ,'DATABASE_URL':url},capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    from sqlalchemy.orm import Session
    from app.models import Application,Product,Document
    from app.normalized_models import IncomeRecord,Liability,DocumentPage,EligibilityCriterion
    from sqlalchemy import select,func
    with Session(engine) as db:
        assert db.get(Application,1).profile['monthly_income']==50000
        assert db.get(Application,1).profile['monthly_debt']==0
        assert db.get(Product,1).criteria==[rule]
        assert db.get(Document,8).extraction['entities'][0]['quote']=='Monthly income: 50000'
        assert db.scalar(select(func.count()).select_from(IncomeRecord))==1
        assert db.scalar(select(func.count()).select_from(Liability))==1
        assert db.scalar(select(func.count()).select_from(DocumentPage))==2
        assert db.scalar(select(func.count()).select_from(EligibilityCriterion))==1
    inspector=inspect(engine)
    assert 'profile' not in [c['name'] for c in inspector.get_columns('loan_applications')]
    assert 'criteria' not in [c['name'] for c in inspector.get_columns('loan_products')]
    assert 'pages' not in [c['name'] for c in inspector.get_columns('financial_documents')]
    engine.dispose()
