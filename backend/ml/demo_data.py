"""Export deliberately synthetic source records, never inferred real credit histories."""
import json
import random
from pathlib import Path


def export_details(applicants, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    records=[]
    for index, applicant in enumerate(applicants):
        profile=applicant['profile']
        rng=random.Random(1000+index)
        missed=set(rng.sample(range(12), min(profile.get('missed_payments') or 0,12)))
        records.append({'applicant_reference':applicant['reference'], 'synthetic':True, 'employment_records':[{'duration_months':profile.get('employment_months'),'source':'synthetic generator','synthetic':True}], 'income_records':[{'gross_monthly_income':profile.get('monthly_income'),'verified_in_demo':profile.get('income_verified',False),'synthetic':True}], 'liabilities':[{'monthly_obligation':profile.get('monthly_debt'),'type':'synthetic aggregate obligation','synthetic':True}], 'repayment_records':[{'period':f'2025-{month+1:02}','missed':month in missed,'source':'synthetic generator; not a credit bureau','synthetic':True} for month in range(12)]})
    (directory/'financial_records.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    samples=directory.parent/'sample_documents';samples.mkdir(parents=True,exist_ok=True)
    for index in [0,1,17,29,49]:
        applicant=applicants[index];p=applicant['profile']
        text=f"SYNTHETIC FINANCIAL DOCUMENT\nApplicant reference: {applicant['reference']}\nMonthly income: {p.get('monthly_income') if p.get('monthly_income') is not None else 'UNKNOWN'}\nMonthly debt: {p.get('monthly_debt')}\nEmployment months: {p.get('employment_months')}\nIncome conflict scenario: {p.get('income_conflict')}\nNot a real customer, bank record or verification.\n"
        (samples/f"{applicant['reference']}.txt").write_text(text,encoding='utf-8')


if __name__=='__main__':
    from app.config import settings
    directory=Path(settings.data_dir,'synthetic')
    export_details(json.loads((directory/'applicants.json').read_text(encoding='utf-8')),directory)
    print('Exported 500 synthetic financial profiles and demonstration repayment histories.')
