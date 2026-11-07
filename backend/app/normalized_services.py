from sqlalchemy import select, event
from sqlalchemy.orm import Session
from .models import Document, Product, RagQuery, Review, Application
from .normalized_models import *


def initialize_roles(db):
    grants={'analyst':['applications.manage','documents.review','policies.read'], 'reviewer':['applications.manage','documents.review','policies.read','assessments.review','decisions.record'], 'admin':['applications.manage','documents.review','policies.read','assessments.review','decisions.record','policies.manage','users.manage','audit.read']}
    for permission in sorted({p for values in grants.values() for p in values}):
        if db.get(Permission,permission) is None:
            db.add(Permission(name=permission,description=permission.replace('.',' ')))
    for role,permissions in grants.items():
        if db.get(Role,role) is None:
            db.add(Role(name=role,description=role.title()))
    db.flush()
    for role,permissions in grants.items():
        for permission in permissions:
            if db.get(RolePermission,(role,permission)) is None:
                db.add(RolePermission(role_name=role,permission_name=permission))
    db.flush()


def catalog_document(db,document):
    if document.source_record is None:
        document.source_record=KnowledgeSource(source_type=document.kind,authorized=True)
    if document.kind=='policy':
        product=db.get(Product,document.product_id)
        if product is None:
            raise ValueError('Policy product does not exist')
        versions=[v for v in product.versions if v.version==document.version]
        if versions:
            version=max(versions,key=lambda v:v.revision or 1)
        else:
            version=PolicyVersion(version=document.version,revision=1,jurisdiction=product.jurisdiction)
            product.versions.append(version)
        if document.policy_record is None:
            document.policy_record=PolicyDocument(version=version,source=document.source_record)
            document.permission_records=[DocumentPermission(role_name=role) for role in ['admin','analyst','reviewer']]


def configure_product(product,version,jurisdiction,criteria):
    if product.policy_version==version and product.jurisdiction==jurisdiction and product.criteria==criteria:
        return
    drafts=[v for v in product.versions if v.version==version and not v.criteria]
    if drafts:
        target=max(drafts,key=lambda v:v.revision or 1)
    else:
        revision=max((v.revision or 1 for v in product.versions if v.version==version),default=0)+1
        target=PolicyVersion(version=version,revision=revision,jurisdiction=jurisdiction)
        product.versions.append(target)
    target.jurisdiction=jurisdiction
    product.active_version=target
    product.criteria=criteria


@event.listens_for(Session,'before_flush')
def normalize_new_records(db,context,instances):
    for obj in list(db.new):
        if isinstance(obj,Document):
            catalog_document(db,obj)
        elif isinstance(obj,RagQuery):
            response=obj.response
            obj.generated_record=GeneratedResponse(text=response['answer'],mode=response['mode'],unsupported_claims=response.get('unsupported_claims',0))
            obj.evidence_records=[RetrievedEvidence(chunk_id=e['chunk_id'],rank=i+1,score=e['score']) for i,e in enumerate(response.get('evidence',[]))]
        elif isinstance(obj,Review):
            obj.comment_records.append(ReviewerComment(reviewer_id=obj.reviewer_id,text=obj.comment))
    for obj in list(db.dirty):
        if isinstance(obj,Review) and obj.comment and (not obj.comment_records or obj.comment_records[-1].text!=obj.comment):
            obj.comment_records.append(ReviewerComment(reviewer_id=obj.reviewer_id,text=obj.comment))


def model_version(db,name,version):
    model=db.scalar(select(MLModel).where(MLModel.name==name))
    if model is None:
        model=MLModel(name=name);db.add(model);db.flush()
    record=db.scalar(select(ModelVersion).where(ModelVersion.model_id==model.id,ModelVersion.version==version))
    if record is None:
        record=ModelVersion(model_id=model.id,version=version,synthetic=True);db.add(record);db.flush()
    return record


def persist_prediction(db,application_id,risk,assessment_id=None):
    version=model_version(db,risk['model_name'],risk['version'])
    prediction=ModelPrediction(application_id=application_id,assessment_id=assessment_id,model_version_id=version.id,score=risk.get('score'),category=risk['category'],synthetic_model=risk.get('synthetic_model',True),created_at=risk.get('timestamp',now()))
    db.add(prediction);db.flush()
    features={}
    for name,value in risk.get('features',{}).items():
        row=PredictionFeature(prediction_id=prediction.id,name=name,value=value,missing=value is None)
        db.add(row);features[name]=row
    db.flush()
    if risk.get('baseline') is not None:
        explanation=ShapExplanation(prediction_id=prediction.id,baseline=risk['baseline'],units=risk.get('explanation_units','log-odds'))
        db.add(explanation);db.flush()
        for contribution in risk.get('contributions',[]):
            db.add(ShapContribution(explanation_id=explanation.id,prediction_feature_id=features[contribution['feature']].id,value=contribution['contribution']))
    return prediction


def persist_assessment(db,record,strict=True):
    result=record.result
    app=db.get(Application,record.application_id)
    product=db.get(Product,app.product_id)
    selected_version=next((version for version in product.versions if version.id==result.get('policy_version_id')),product.active_version)
    versions=[selected_version]+[version for version in product.versions if version is not selected_version]
    for rule in result['eligibility']['criteria']:
        criterion=next((c for version in versions for c in version.criteria if c.key==rule['key'] and c.quote==rule['quote'] and c.threshold==rule['threshold']),None)
        if criterion is None:
            if strict:
                raise ValueError('Assessment criterion has no normalized policy source')
            db.add(MigrationIssue(entity_type='assessment',entity_id=record.id,message='Legacy criterion lacks a recoverable policy source: '+rule['key']))
            continue
        db.add(EligibilityCriterionResult(assessment_id=record.id,criterion_id=criterion.id,observed_value=rule.get('value'),status=rule['status'],evidence_valid=rule.get('evidence_valid',False)))
    for name,value in result.get('financial',{}).items():
        if value is None or (isinstance(value,(int,float)) and not isinstance(value,bool)):
            db.add(FinancialFeature(assessment_id=record.id,name=name,value=value,unit='percent' if name in ['dti','ltv','repayment_burden'] else 'ratio' if name=='lti' else 'INR'))
    prediction=persist_prediction(db,app.id,result['risk'],record.id)
    for i,evidence in enumerate(result.get('evidence',[])):
        if db.get(Chunk,evidence['chunk_id']) is not None:
            db.add(RetrievedEvidence(assessment_id=record.id,chunk_id=evidence['chunk_id'],rank=i+1,score=evidence['score']))
        elif not strict:
            db.add(MigrationIssue(entity_type='assessment',entity_id=record.id,message='Legacy citation references a removed chunk; original snapshot preserved.'))
    return prediction


def persist_model_evaluation(db,report):
    from sqlalchemy import delete
    for name,metrics in report['models'].items():
        version=model_version(db,name,report['version'])
        from pathlib import Path
        from .config import settings
        basename='credit' if name==report['selected_model'] else name.lower().replace(' ','-')
        version.artifact_path=str(Path(settings.model_dir)/f"{basename}-{report['version']}.joblib")
        db.execute(delete(ModelEvaluation).where(ModelEvaluation.model_version_id==version.id))
        db.execute(delete(CalibrationBin).where(CalibrationBin.model_version_id==version.id))
        if name==report['selected_model'] and report.get('synthetic_fairness'):
            db.execute(delete(FairnessEvaluation).where(FairnessEvaluation.model_version_id==version.id,FairnessEvaluation.governance_reference=='SYNTHETIC_DEVELOPMENT_ONLY'))
            diagnostics=report['synthetic_fairness']
            for metric in ['demographic_parity_difference','equal_opportunity_difference','equalized_odds_difference']:
                db.add(FairnessEvaluation(model_version_id=version.id,dataset_reference='synthetic-held-out-test',governance_reference='SYNTHETIC_DEVELOPMENT_ONLY',metric=metric,group_reference=None,value=diagnostics[metric],limitations=diagnostics['governance']))
            for group,group_metrics in diagnostics['groups'].items():
                for metric,value in group_metrics.items():
                    db.add(FairnessEvaluation(model_version_id=version.id,dataset_reference='synthetic-held-out-test',governance_reference='SYNTHETIC_DEVELOPMENT_ONLY',metric=metric,group_reference=group,value=value,limitations=diagnostics['governance']))
        for split,values in metrics.items():
            for metric,value in values.items():
                if isinstance(value,(int,float)):
                    db.add(ModelEvaluation(model_version_id=version.id,split=split,metric=metric,value=value))
                elif metric=='confusion_matrix':
                    for actual,row in enumerate(value):
                        for predicted,count in enumerate(row):
                            db.add(ModelEvaluation(model_version_id=version.id,split=split,metric=f'confusion_{actual}_{predicted}',value=count))
                elif metric=='calibration':
                    for ordinal,(predicted,observed) in enumerate(zip(value['predicted'],value['observed'])):
                        db.add(CalibrationBin(model_version_id=version.id,split=split,ordinal=ordinal,predicted=predicted,observed=observed))


def import_synthetic_repayments(db,path):
    import json
    from .models import Applicant
    records=json.loads(path.read_text(encoding='utf-8'))
    imported=0
    for record in records:
        if record.get('synthetic') is not True:
            raise ValueError('This command accepts only explicitly synthetic source records')
        application=db.scalar(select(Application).join(Applicant).where(Applicant.reference==record['applicant_reference']))
        if not application or not application.synthetic:
            raise ValueError('Synthetic source does not match a synthetic application')
        accounts=application.profile_record.credit_accounts
        if not accounts:
            raise ValueError('A declared credit account is required; no credit score will be inferred')
        account=accounts[0]
        existing={r.period:r for r in account.repayments}
        for repayment in record['repayment_records']:
            if repayment.get('synthetic') is not True:
                raise ValueError('Synthetic repayment marker is required')
            status='MISSED' if repayment['missed'] else 'PAID'
            if repayment['period'] in existing:
                if existing[repayment['period']].status!=status:
                    raise ValueError('Conflicting synthetic repayment source; import withheld')
                continue
            account.repayments.append(RepaymentRecord(period=repayment['period'],status=status))
            imported+=1
    return imported
