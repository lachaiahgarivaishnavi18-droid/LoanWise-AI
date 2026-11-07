"""Downloads public model weights, then tests local inference on synthetic policies only."""
import os
from pathlib import Path
import sys
import json
import time
import importlib.metadata

ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT/'backend');sys.path.insert(0,str(ROOT/'backend'))
os.environ.setdefault('HF_HUB_DISABLE_XET','1')
os.environ.setdefault('HF_HOME',str(ROOT/'backend/runtime/huggingface'))


def main():
    from app.config import settings
    from app.database import SessionLocal
    from ai.retrieval import retrieve
    settings.retrieval_mode='neural'
    started=time.perf_counter()
    with SessionLocal() as db:
        evidence=retrieve(db,'minimum monthly income requirements',product_id=1,role='admin')
        assert evidence,'No source retrieved for a known synthetic policy requirement'
        assert all(e['retrieval_strategy']=='neural' and e['reranker_score'] is not None for e in evidence)
        assert all(e['synthetic'] for e in evidence),'This benchmark accepts synthetic policies only'
        cached=retrieve(db,'minimum monthly income requirements',product_id=1,role='admin')
        assert [e['chunk_id'] for e in cached]==[e['chunk_id'] for e in evidence]
        from sqlalchemy import select
        from app.models import Application,User
        from ai.orchestration import run_assessment
        from ai.evaluation import evaluate_retrieval
        application=db.get(Application,2)
        assert application and application.synthetic,'A synthetic demo application #2 is required'
        user=db.scalar(select(User).where(User.role=='admin'))
        result=run_assessment(db,application,user)
        assert result['agent_count']==12 and result['evidence']
        assert result['eligibility']['human_review_required']
        benchmark=evaluate_retrieval(db)
        unknown=retrieve(db,'extraterrestrial quantum zebra nebula',role='admin')
    files=list(Path(settings.runtime_dir,'vectors').glob('*.faiss'))
    assert files,'FAISS index did not persist'
    assert not unknown,'Unknown synthetic benchmark query did not abstain'
    report={'passed':True,'source_ids':[e['chunk_id'] for e in evidence],'semantic_scores':[e['semantic_score'] for e in evidence],'reranker_scores':[e['reranker_score'] for e in evidence],'unknown_query_abstained':True,'persisted_faiss_files':len(files),'duration_seconds':round(time.perf_counter()-started,2),'versions':{name:importlib.metadata.version(name) for name in ['sentence-transformers','faiss-cpu','torch']},'limitations':'Small synthetic smoke check; not a real-world retrieval quality validation.'}
    report.update(agent_count=result['agent_count'],assessment_id=result['assessment_id'],benchmark=benchmark)
    output=ROOT/'runtime/verification/neural.json';output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
