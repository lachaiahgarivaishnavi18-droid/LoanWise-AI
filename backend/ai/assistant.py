"""Deterministic applicant context; no policy or applicant facts are invented by an LLM."""
from sqlalchemy import select
from app.models import Assessment,Document
from app.security import evidence_access
from .financial import financial_features
from .provenance import input_fingerprint


def application_answer(db,user,application,question,answer):
    financial=financial_features(application)
    lines=[f"Selected application #{application.id} ({'synthetic' if application.synthetic else 'user-entered'}). Values below come from its authorized declared financial records, not independent bank verification."]
    text=question.lower()
    assessment_evidence=[]
    if any(key in text for key in ['dti','debt','income','emi','installment','instalment','financial','ratio']):
        for name,label,unit in [('monthly_income','Reviewed gross monthly income','INR'),('monthly_debt','Existing monthly debt','INR'),('dti','DTI','%'),('lti','Loan-to-income','times annual gross income'),('emi','Estimated EMI at the supplied illustration rate','INR')]:
            value=financial[name]
            lines.append(f"{label}: {value if value is not None else 'UNKNOWN'}{(' '+unit) if value is not None else ''}.")
        lines.append('DTI = existing monthly debt / reviewed gross monthly income × 100. Missing, unverified, conflicting or zero income produces an unknown ratio.')
    latest=db.scalar(select(Assessment).where(Assessment.application_id==application.id).order_by(Assessment.id.desc()))
    current=bool(latest and latest.result.get('input_fingerprint')==input_fingerprint(db,application))
    if any(key in text for key in ['why','flag','review','satisfied','eligible','eligibility','missing','requirement','risk','model','explain']):
        if current:
            evidence_access(db,user,latest.result)
            result=latest.result
            assessment_evidence=result.get('evidence',[])
            lines.append('Current assessment: '+result['eligibility']['overall_status']+'.')
            for criterion in result['eligibility']['criteria']:
                if criterion['status']!='SATISFIED':
                    lines.append(f"{criterion['label']}: {criterion['status']}; observed value {criterion['value'] if criterion['value'] is not None else 'UNKNOWN'}. Configured policy interpretation; inspect its quoted source in the assessment.")
            if any(key in text for key in ['risk','model','explain']):
                risk=result['risk']
                lines.append(f"Synthetic model indicator: {risk['category']}; uncalibrated score {risk.get('score') if risk.get('score') is not None else 'unavailable'}. This is not an individual default probability.")
                for contribution in sorted(risk.get('contributions',[]),key=lambda c:abs(c['contribution']),reverse=True)[:3]:
                    lines.append(f"{contribution['feature']}: {contribution['direction']}, SHAP contribution {contribution['contribution']:.3f} log-odds. Model behavior is not proof of causation.")
        else:
            lines.append('No current assessment is available. Run or refresh the assessment before relying on criterion or model outcomes.')
    if any(key in text for key in ['document','missing','review','flag']):
        documents=db.scalars(select(Document).where(Document.application_id==application.id)).all()
        lines.append(f"Financial documents awaiting review: {sum(not d.reviewed for d in documents)}. Document type requirements must come from reviewed product policy evidence; none are inferred from missing records.")
    lines.append('Final lending decisions require an authorized human reviewer.')
    if assessment_evidence:
        from .retrieval import grounded_answer
        combined={e['chunk_id']:e for e in answer['evidence']+assessment_evidence}
        answer=grounded_answer(question,list(combined.values()))
    return {**answer,'answer':'\n'.join(lines)+'\n\nAuthorized policy passages:\n'+answer['answer'],'application_context':{'application_id':application.id,'synthetic':application.synthetic,'financial':financial,'assessment_current':current},'mode':'local deterministic financial context + extractive policy evidence'}
