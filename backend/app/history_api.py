from pathlib import Path
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from .database import get_db
from .models import Assessment
from .normalized_models import ModelPrediction,ModelVersion,MLModel,PredictionFeature,ShapExplanation,ShapContribution
from .security import current_user,application_access,evidence_access
from ml.pipeline import LIMITATIONS

router=APIRouter(prefix='/api')


@router.get('/credit-risk/{application_id}/history')
def prediction_history(application_id:int,db=Depends(get_db),user=Depends(current_user)):
    application_access(db,user,application_id)
    rows=db.scalars(select(ModelPrediction).where(ModelPrediction.application_id==application_id).order_by(ModelPrediction.id.desc()).limit(100)).all()
    result=[]
    for row in rows:
        version=db.get(ModelVersion,row.model_version_id) if row.model_version_id else None
        model=db.get(MLModel,version.model_id) if version else None
        features=db.scalars(select(PredictionFeature).where(PredictionFeature.prediction_id==row.id)).all()
        explanation=db.scalar(select(ShapExplanation).where(ShapExplanation.prediction_id==row.id))
        contributions=[]
        if explanation:
            values=db.scalars(select(ShapContribution).where(ShapContribution.explanation_id==explanation.id)).all()
            by_id={feature.id:feature for feature in features}
            contributions=[{'feature':by_id[value.prediction_feature_id].name,'value':by_id[value.prediction_feature_id].value,'contribution':value.value,'direction':'raises model score' if value.value>0 else 'lowers model score'} for value in values]
        result.append({'prediction_id':row.id,'assessment_id':row.assessment_id,'timestamp':row.created_at,'model_name':model.name if model else 'Unavailable','version':version.version if version else 'unavailable','score':row.score,'category':row.category,'synthetic_model':row.synthetic_model,'features':{feature.name:feature.value for feature in features},'missing_features':[feature.name for feature in features if feature.missing],'contributions':contributions,'baseline':explanation.baseline if explanation else None,'explanation_units':explanation.units if explanation else None,'limitations':LIMITATIONS})
    return result


@router.get('/models/versions')
def model_versions(db=Depends(get_db),user=Depends(current_user)):
    return [{'id':version.id,'model_name':model.name,'version':version.version,'synthetic':version.synthetic,'created_at':version.created_at,'artifact_available':bool(version.artifact_path and Path(version.artifact_path).is_file())} for version,model in db.execute(select(ModelVersion,MLModel).join(MLModel)).all()]


@router.get('/eligibility/{application_id}/history')
def assessment_history(application_id:int,db=Depends(get_db),user=Depends(current_user)):
    application=application_access(db,user,application_id)
    from ai.provenance import input_fingerprint
    fingerprint=input_fingerprint(db,application)
    result=[]
    for row in db.scalars(select(Assessment).where(Assessment.application_id==application_id).order_by(Assessment.id.desc()).limit(100)).all():
        try:
            evidence_access(db,user,row.result)
            status=row.result['eligibility']['overall_status']
        except HTTPException:
            status='RESTRICTED SOURCE ACCESS'
        result.append({'assessment_id':row.id,'created_at':row.created_at,'status':status,'current_inputs':row.result.get('input_fingerprint')==fingerprint})
    return result


@router.get('/assessments/{identifier}')
def historical_assessment(identifier:int,db=Depends(get_db),user=Depends(current_user)):
    row=db.get(Assessment,identifier)
    if not row:
        raise HTTPException(404,'Assessment not found')
    application_access(db,user,row.application_id)
    evidence_access(db,user,row.result)
    return row.result
