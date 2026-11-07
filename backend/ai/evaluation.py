"""A small deterministic synthetic retrieval benchmark. Not a real-world quality estimate."""
import json
import math
from pathlib import Path
from sqlalchemy import select
from app.database import SessionLocal
from app.models import Product
from .retrieval import retrieve, grounded_answer


def ranking_metrics(retrieved, relevant, k=5):
    hits = [1 if i in relevant else 0 for i in retrieved[:k]]
    recall = len(set(retrieved[:k]) & set(relevant)) / len(relevant) if relevant else 0
    reciprocal = next((1 / (i + 1) for i, hit in enumerate(hits) if hit), 0)
    dcg = sum(hit / math.log2(i + 2) for i, hit in enumerate(hits))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(relevant))))
    return {'precision_at_k': sum(hits) / k, 'recall_at_k': recall, 'mrr': reciprocal, 'ndcg': dcg / ideal if ideal else 0}


def evaluate_retrieval(db,role='analyst'):
    from app.models import Chunk, Document
    results = []
    for product in db.scalars(select(Product).where(Product.synthetic==True)).all():
        if not product.criteria:
            continue
        for question in ['minimum monthly income', 'maximum debt-to-income', 'employment duration']:
            evidence = retrieve(db, question, product.id, version=product.policy_version,role=role)
            relevant_query=select(Chunk.id).join(Document,Chunk.document_id==Document.id).where(Document.product_id==product.id,Document.reviewed==True,Document.version==product.policy_version,Chunk.active==True)
            if role!='admin':
                from app.normalized_models import DocumentPermission
                relevant_query=relevant_query.where(Document.id.in_(select(DocumentPermission.document_id).where(DocumentPermission.role_name==role)))
            relevant = db.scalars(relevant_query).all()
            ranking = ranking_metrics([e['chunk_id'] for e in evidence], relevant)
            answer = grounded_answer(question, evidence)
            valid = all(any(e['chunk_id'] == ref for e in evidence) for ref in answer['citations'])
            results.append({'product_id': product.id, 'question': question, **ranking, 'citation_accuracy': float(valid), 'evidence_coverage': 1.0 if evidence else 0.0, 'unsupported_claim_rate': 0.0 if answer['mode'].startswith('local extractive') else None})
    absent = retrieve(db, 'extraterrestrial quantum zebra nebula',role=role)
    from app.config import settings
    return {'synthetic': True,'strategy':settings.retrieval_mode, 'cases': results, 'mean': {key: sum(r[key] for r in results) / len(results) if results else None for key in ['precision_at_k', 'recall_at_k', 'mrr', 'ndcg', 'citation_accuracy', 'evidence_coverage', 'unsupported_claim_rate']}, 'correct_abstention_on_unknown': not absent, 'limitations': ['Small synthetic benchmark; relevant documents are product-matched demo policies.', 'Local answers are exact quotations, so unsupported-claim rate is structural, not an independent LLM faithfulness evaluation.', 'Precision denominator remains K even when fewer chunks exist.', 'Results for one retrieval strategy do not validate another strategy or real-world corpora.']}


if __name__ == '__main__':
    with SessionLocal() as db:
        report = evaluate_retrieval(db)
    path = Path('runtime/evaluation'); path.mkdir(parents=True, exist_ok=True)
    (path / 'retrieval.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
