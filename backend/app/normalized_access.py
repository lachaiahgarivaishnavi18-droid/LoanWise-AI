"""Compatibility DTO accessors. Source records remain independently queryable and constrained."""
from sqlalchemy.orm import object_session
from sqlalchemy import select


def profile_get(self):
    p = self.profile_record
    if p is None:
        return {k: None for k in ['monthly_income','monthly_debt','monthly_expenses','employment_months','credit_score','credit_utilization','missed_payments','asset_value']} | {'income_verified':False,'credit_verified':False,'income_conflict':False,'asset_verified':False}
    factors={'MONTHLY':1,'ANNUAL':1/12,'WEEKLY':52/12,'FORTNIGHTLY':26/12}
    credit=p.credit_accounts[0] if p.credit_accounts else None
    scores={c.reliable_score for c in p.credit_accounts if c.reliable_score is not None}
    missed=[c.reported_missed_payments for c in p.credit_accounts]
    return {'monthly_income':round(sum(i.amount*factors[i.frequency or 'MONTHLY'] for i in p.incomes),2) if p.incomes else None, 'income_verified':bool(p.incomes and all(i.verified for i in p.incomes)), 'monthly_debt':round(sum(i.monthly_payment for i in p.liabilities),2) if p.liabilities else None, 'monthly_expenses':round(sum(i.monthly_amount for i in p.expenses),2) if p.expenses else None, 'employment_months':max((i.duration_months for i in p.employment),default=None), 'credit_score':next(iter(scores)) if len(scores)==1 else None, 'credit_utilization':credit.utilization_percent if len(p.credit_accounts)==1 else None, 'missed_payments':sum(missed) if missed and all(v is not None for v in missed) else None, 'credit_verified':bool(p.credit_accounts and all(c.verified for c in p.credit_accounts) and len(scores)<=1), 'asset_value':p.asset_value, 'asset_verified':bool(p.asset_verified), 'income_conflict':bool(p.income_conflict)}


def profile_set(self, values):
    from .normalized_models import ApplicantProfile, IncomeRecord, ExpenseRecord, Liability, EmploymentRecord, CreditAccount
    p=self.profile_record
    current=profile_get(self)
    if p is None:
        p=ApplicantProfile(currency='INR'); self.profile_record=p
    p.asset_value=values.get('asset_value');p.asset_verified=values.get('asset_verified',False);p.income_conflict=values.get('income_conflict',False)
    # A full profile PUT explicitly replaces current declarations. Document observations are separate.
    if values.get('monthly_income')!=current['monthly_income'] or values.get('income_verified',False)!=current['income_verified']:
        if len(p.incomes)>1:
            raise ValueError('Edit individual income sources through the financial records endpoint')
        p.incomes=[] if values.get('monthly_income') is None else [IncomeRecord(amount=values['monthly_income'],frequency='MONTHLY',verified=values.get('income_verified',False))]
    if values.get('monthly_expenses')!=current['monthly_expenses']:
        p.expenses=[] if values.get('monthly_expenses') is None else [ExpenseRecord(monthly_amount=values['monthly_expenses'])]
    if values.get('monthly_debt')!=current['monthly_debt']:
        if len(p.liabilities)>1:
            raise ValueError('Edit individual liabilities through the financial records endpoint')
        p.liabilities=[] if values.get('monthly_debt') is None else [Liability(monthly_payment=values['monthly_debt'])]
    if values.get('employment_months')!=current['employment_months']:
        p.employment=[] if values.get('employment_months') is None else [EmploymentRecord(duration_months=values['employment_months'])]
    credit_changed=any(values.get(key,False if key=='credit_verified' else None)!=current[key] for key in ['credit_score','credit_utilization','missed_payments','credit_verified'])
    if credit_changed:
        if len(p.credit_accounts)>1:
            raise ValueError('Edit individual credit accounts through the financial records endpoint')
        credit=p.credit_accounts[0] if p.credit_accounts else CreditAccount()
        credit.reliable_score=values.get('credit_score');credit.utilization_percent=values.get('credit_utilization');credit.reported_missed_payments=values.get('missed_payments');credit.verified=values.get('credit_verified',False)
        if not p.credit_accounts:
            p.credit_accounts=[credit]


def policy_name_get(self):
    return self.active_version.version if self.active_version else ''


def policy_name_set(self, value):
    from .normalized_models import PolicyVersion
    if self.active_version and self.active_version.version==value:
        return
    candidates=[v for v in self.versions if v.version==value]
    if candidates:
        self.active_version=max(candidates,key=lambda v:v.revision or 1)
    else:
        version=PolicyVersion(version=value,revision=1,jurisdiction='SYNTHETIC DEMO')
        self.versions.append(version);self.active_version=version


def jurisdiction_get(self):
    return self.active_version.jurisdiction if self.active_version else 'UNCONFIGURED'


def jurisdiction_set(self, value):
    if self.active_version:
        self.active_version.jurisdiction=value


def criteria_get(self):
    if not self.active_version:
        return []
    return [{'key':r.key,'label':r.label,'operator':r.operator,'threshold':r.threshold,'document_id':r.source_page.document_id,'page':r.source_page.page_number,'quote':r.quote} for r in self.active_version.criteria]


def criteria_set(self, values):
    from .normalized_models import PolicyVersion, EligibilityCriterion, DocumentPage
    if not self.active_version:
        raise ValueError('Set a policy version before configuring its criteria')
    if self.criteria==values:
        return
    if self.active_version.criteria:
        old=self.active_version
        revision=max((v.revision or 1 for v in self.versions if v.version==old.version),default=0)+1
        version=PolicyVersion(version=old.version,revision=revision,jurisdiction=old.jurisdiction)
        self.versions.append(version);self.active_version=version
    db=object_session(self)
    if values and db is None:
        raise ValueError('Attach product to a session before configuring policy sources')
    rows=[]
    for value in values:
        page=db.scalar(select(DocumentPage).where(DocumentPage.document_id==value['document_id'],DocumentPage.page_number==value['page'],DocumentPage.active==True))
        if page is None:
            raise ValueError('A persisted document page is required for each criterion')
        rows.append(EligibilityCriterion(key=value['key'],label=value['label'],operator=value['operator'],threshold=value['threshold'],source_page=page,quote=value['quote']))
    self.active_version.criteria=rows


def pages_get(self):
    return [{'page':p.page_number,'text':p.text,'method':p.extraction_method or 'text','ocr_confidence':p.ocr_confidence} for p in sorted(self.page_records,key=lambda p:p.page_number) if p.active]


def pages_set(self, values):
    from .normalized_models import DocumentPage
    current={p.page_number:p for p in self.page_records if p.active}
    keep=set()
    for value in values:
        number=value['page'];keep.add(number);prior=current.get(number)
        method=value.get('method','text')
        if prior and prior.text==value['text'] and prior.extraction_method==method:
            prior.ocr_confidence=value.get('ocr_confidence');continue
        if prior:
            prior.active=False
        revision=max((p.revision or 1 for p in self.page_records if p.page_number==number),default=0)+1
        self.page_records.append(DocumentPage(page_number=number,revision=revision,active=True,text=value['text'],extraction_method=method,ocr_confidence=value.get('ocr_confidence')))
    for number,prior in current.items():
        if number not in keep:
            prior.active=False


def extraction_get(self):
    entities=[]
    for e in self.entity_records:
        if not e.active or not e.page.active:
            continue
        value={'field':e.field,'value':e.value,'page':e.page.page_number,'quote':e.quote,'verified':bool(e.verified)}
        if e.corrections:
            value['correction_history']=[{'previous_value':c.previous_value,'corrected_value':c.corrected_value,'reason':c.reason,'reviewer_id':c.reviewer_id,'timestamp':c.created_at} for c in e.corrections]
        entities.append(value)
    return {'entities':entities,'warnings':[w.message for w in self.warning_records],'method':self.extraction_method or 'text extraction','confidence':self.extraction_confidence,'verified':bool(self.extraction_verified),'quarantined':bool(self.quarantined)}


def extraction_set(self, values):
    from .normalized_models import ExtractedFinancialEntity, ExtractionCorrection, DocumentWarning
    self.extraction_method=values.get('method','text extraction');self.extraction_confidence=values.get('confidence');self.extraction_verified=values.get('verified',False);self.quarantined=values.get('quarantined',False)
    self.warning_records=[DocumentWarning(message=w) for w in values.get('warnings',[])]
    existing={e.ordinal:e for e in self.entity_records if e.active and e.page.active}
    for e in existing.values():
        e.active=False
    for ordinal,value in enumerate(values.get('entities',[])):
        page=next((p for p in self.page_records if p.page_number==value['page'] and p.active),None)
        if page is None:
            raise ValueError('Extracted entity has no matching source page')
        entity=existing.get(ordinal)
        if entity is None or entity.page is not page or entity.quote!=value['quote'] or entity.field!=value['field']:
            entity=ExtractedFinancialEntity(ordinal=ordinal,field=value['field'],quote=value['quote'],active=True)
            page.entities.append(entity)
        entity.active=True;entity.value=value['value'];entity.verified=value.get('verified',False)
        for correction in value.get('correction_history',[])[len(entity.corrections):]:
            entity.corrections.append(ExtractionCorrection(previous_value=correction['previous_value'],corrected_value=correction['corrected_value'],reason=correction['reason'],reviewer_id=correction['reviewer_id'],created_at=correction['timestamp']))
