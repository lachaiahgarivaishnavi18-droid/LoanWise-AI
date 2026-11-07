from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field,model_validator,ConfigDict
from sqlalchemy import select,inspect
from .database import get_db
from .models import Document,Product
from .normalized_models import ApplicantProfile,IncomeRecord,ExpenseRecord,Liability,EmploymentRecord,CreditAccount,RepaymentRecord,DocumentPermission,ApplicationFeedback
from .security import current_user,roles,application_access,audit

router=APIRouter(prefix='/api')


class SourceInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source_document_id:int|None=None
    source_type:Literal['USER_PROVIDED','DOCUMENT','SYNTHETIC_GENERATOR']='USER_PROVIDED'


class IncomeInput(SourceInput):
    amount:float=Field(ge=0,le=1e12)
    frequency:Literal['MONTHLY','ANNUAL','WEEKLY','FORTNIGHTLY']='MONTHLY'
    verified:bool=False


class ExpenseInput(SourceInput):
    monthly_amount:float=Field(ge=0,le=1e12)
    category:str=Field(default='DECLARED_TOTAL',max_length=100)


class LiabilityInput(SourceInput):
    monthly_payment:float=Field(ge=0,le=1e12)
    outstanding_balance:float|None=Field(default=None,ge=0,le=1e12)


class EmploymentInput(SourceInput):
    duration_months:int=Field(ge=0,le=900)


class RepaymentInput(BaseModel):
    period:str=Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    status:Literal['PAID','MISSED','UNKNOWN']
    source_document_id:int|None=None


class CreditInput(SourceInput):
    reliable_score:int|None=Field(default=None,ge=300,le=900)
    utilization_percent:float|None=Field(default=None,ge=0,le=100)
    reported_missed_payments:int|None=Field(default=None,ge=0,le=100)
    verified:bool=False
    repayments:list[RepaymentInput]=Field(default_factory=list,max_length=600)

    @model_validator(mode='after')
    def unique_periods(self):
        if len({r.period for r in self.repayments})!=len(self.repayments):
            raise ValueError('Repayment periods must be unique within an account')
        return self


class LedgerInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    asset_value:float|None=Field(default=None,gt=0,le=1e12)
    asset_verified:bool=False
    income_conflict:bool=False
    incomes:list[IncomeInput]=Field(default_factory=list,max_length=100)
    expenses:list[ExpenseInput]=Field(default_factory=list,max_length=100)
    liabilities:list[LiabilityInput]=Field(default_factory=list,max_length=100)
    employment:list[EmploymentInput]=Field(default_factory=list,max_length=100)
    credit_accounts:list[CreditInput]=Field(default_factory=list,max_length=100)


def row_view(row,synthetic):
    return {**{column.key:getattr(row,column.key) for column in inspect(type(row)).column_attrs},'synthetic':synthetic}


@router.get('/applications/{identifier}/financial-records')
def financial_records(identifier:int,db=Depends(get_db),user=Depends(current_user)):
    application=application_access(db,user,identifier)
    profile=application.profile_record
    result={'application_id':identifier,'synthetic':application.synthetic,'profile':application.profile}
    for name in ['incomes','expenses','liabilities','employment','credit_accounts']:
        result[name]=[row_view(row,application.synthetic) for row in getattr(profile,name,[])]
    for value,account in zip(result['credit_accounts'],profile.credit_accounts if profile else []):
        value['repayments']=[row_view(row,application.synthetic) for row in account.repayments]
    return result


@router.put('/applications/{identifier}/financial-records')
def update_financial_records(identifier:int,body:LedgerInput,db=Depends(get_db),user=Depends(current_user)):
    application=application_access(db,user,identifier)
    sources=[record for collection in ['incomes','expenses','liabilities','employment','credit_accounts'] for record in getattr(body,collection)]
    sources.extend(repayment for account in body.credit_accounts for repayment in account.repayments)
    for source in sources:
        if getattr(source,'source_type',None)=='SYNTHETIC_GENERATOR' and not application.synthetic:
            raise HTTPException(422,'Synthetic provenance cannot be assigned to a real application')
        document_id=source.source_document_id
        if getattr(source,'source_type',None)=='DOCUMENT' and document_id is None:
            raise HTTPException(422,'Document-derived records require a source document')
        if document_id is not None:
            document=db.get(Document,document_id)
            if not document or document.application_id!=identifier or document.kind!='financial':
                raise HTTPException(422,'Source documents must belong to this application')
            if getattr(source,'verified',False) and not document.reviewed:
                raise HTTPException(422,'A document-derived value cannot be marked verified before source review')
    profile=application.profile_record
    if profile is None:
        profile=ApplicantProfile(currency='INR');application.profile_record=profile
    profile.asset_value=body.asset_value;profile.asset_verified=body.asset_verified;profile.income_conflict=body.income_conflict
    for name,model in [('incomes',IncomeRecord),('expenses',ExpenseRecord),('liabilities',Liability),('employment',EmploymentRecord)]:
        setattr(profile,name,[model(**value.model_dump()) for value in getattr(body,name)])
    accounts=[]
    for value in body.credit_accounts:
        account=CreditAccount(**value.model_dump(exclude={'repayments'}))
        account.repayments=[RepaymentRecord(**record.model_dump()) for record in value.repayments]
        accounts.append(account)
    profile.credit_accounts=accounts
    application.status='Updated — reassessment required'
    audit(db,user,'replace_financial_ledger',identifier);db.commit()
    return financial_records(identifier,db,user)


class PermissionInput(BaseModel):
    roles:list[Literal['admin','analyst','reviewer']]=Field(min_length=1,max_length=3)


@router.put('/documents/{identifier}/permissions')
def set_permissions(identifier:int,body:PermissionInput,db=Depends(get_db),user=Depends(roles('admin'))):
    document=db.get(Document,identifier)
    if not document or document.kind!='policy':
        raise HTTPException(404,'Policy document not found')
    desired=set(body.roles)|{'admin'}
    document.permission_records=[r for r in document.permission_records if r.role_name in desired]
    present={r.role_name for r in document.permission_records}
    document.permission_records.extend(DocumentPermission(role_name=role) for role in desired-present)
    audit(db,user,'configure_document_permissions',identifier);db.commit()
    return {'document_id':identifier,'roles':sorted(desired)}


class ProductInput(BaseModel):
    name:str=Field(min_length=2,max_length=100)
    description:str=Field(min_length=5,max_length=1000)
    policy_version:str=Field(min_length=1,max_length=100)
    jurisdiction:str=Field(min_length=2,max_length=100)


@router.post('/products',status_code=201)
def create_product(body:ProductInput,db=Depends(get_db),user=Depends(roles('admin'))):
    if db.scalar(select(Product).where(Product.name==body.name)):
        raise HTTPException(409,'Product name already exists')
    from .config import settings
    product=Product(**body.model_dump(),criteria=[],synthetic=settings.demo_mode)
    db.add(product);db.flush();audit(db,user,'create_product',product.id);db.commit()
    from .main import product_view
    return product_view(product)


class FeedbackInput(BaseModel):
    text:str=Field(min_length=5,max_length=5000)


@router.post('/applications/{identifier}/feedback',status_code=201)
def feedback(identifier:int,body:FeedbackInput,db=Depends(get_db),user=Depends(current_user)):
    application=application_access(db,user,identifier)
    record=ApplicationFeedback(application_id=identifier,author_id=user.id,text=body.text)
    db.add(record);db.flush();audit(db,user,'application_feedback',identifier);db.commit()
    return row_view(record,application.synthetic)
