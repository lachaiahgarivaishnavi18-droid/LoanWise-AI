"""Authorization precedes indexing/scoring. Local mode is TF-IDF + BM25, not neural embeddings."""
from datetime import date
import re
import hashlib
import os
import secrets
from pathlib import Path
from functools import lru_cache
import numpy as np
from sqlalchemy import select
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from app.models import Chunk, Document, Product
from app.config import settings


def tokens(text):
    return re.findall(r'\w+', text.lower())


@lru_cache(maxsize=1)
def neural_models():
    from sentence_transformers import SentenceTransformer, CrossEncoder
    import torch
    torch.set_num_threads(2)
    cache=Path(settings.runtime_dir,'huggingface');cache.mkdir(parents=True,exist_ok=True)
    return SentenceTransformer(settings.embedding_model,cache_folder=str(cache),device='cpu',trust_remote_code=False), CrossEncoder(settings.reranker_model,cache_folder=str(cache),device='cpu',trust_remote_code=False)


def retrieve(db, question, product_id=None, k=5, version=None,role='analyst'):
    query = select(Chunk, Document).join(Document, Chunk.document_id == Document.id).where(Document.kind == 'policy', Document.reviewed == True, Chunk.active == True)
    from app.normalized_models import KnowledgeSource
    query=query.where(Document.id.in_(select(KnowledgeSource.document_id).where(KnowledgeSource.authorized==True)))
    if role!='admin':
        from app.normalized_models import DocumentPermission
        allowed=select(DocumentPermission.document_id).where(DocumentPermission.role_name==role)
        query=query.where(Document.id.in_(allowed))
    if product_id is not None:
        query = query.where(Document.product_id == product_id)
    current_versions = {p.id: p.policy_version for p in db.scalars(select(Product)).all()}
    rows = [(c, d) for c, d in db.execute(query).all() if not d.extraction.get('quarantined') and d.effective_date and d.effective_date <= date.today().isoformat() and d.version == (version or current_versions.get(d.product_id))]
    if not rows:
        return []
    corpus = [c.text for c, _ in rows]
    keyword = BM25Okapi([tokens(t) for t in corpus]).get_scores(tokens(question))
    if settings.retrieval_mode == 'neural':
        import faiss
        encoder, reranker = neural_models()
        identity = hashlib.sha256((settings.embedding_model + '\n' + '\n'.join(f'{c.id}:{c.text}' for c, _ in rows)).encode()).hexdigest()
        directory = Path(settings.runtime_dir, 'vectors'); directory.mkdir(parents=True, exist_ok=True)
        index_path = directory / f'{identity}.faiss'
        if index_path.exists():
            index = faiss.read_index(str(index_path))
        else:
            vectors = encoder.encode(corpus, normalize_embeddings=True).astype('float32')
            index = faiss.IndexFlatIP(vectors.shape[1])
            index.add(vectors)
            temporary = directory / f'{identity}.{secrets.token_hex(4)}.tmp'
            faiss.write_index(index, str(temporary))
            os.replace(temporary, index_path)
        values, indices = index.search(encoder.encode([question], normalize_embeddings=True).astype('float32'), len(rows))
        semantic = np.zeros(len(rows))
        semantic[indices[0]] = values[0]
    else:
        vectorizer = TfidfVectorizer(ngram_range=(1, 2))
        matrix = vectorizer.fit_transform(corpus + [question])
        semantic = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
    # Reciprocal rank fusion avoids mixing incomparable raw score scales.
    scores = np.zeros(len(rows))
    for values in (keyword, semantic):
        for rank, idx in enumerate(np.argsort(-values)):
            if values[idx] > 0:
                scores[idx] += 1 / (60 + rank + 1)
    minimum=settings.neural_min_similarity if settings.retrieval_mode=='neural' else .035
    candidates = [int(i) for i in np.argsort(-scores) if semantic[i] > minimum][:max(k * 3, 10)]
    reranker_scores={}
    if settings.retrieval_mode == 'neural' and candidates:
        ranking = reranker.predict([(question, corpus[i]) for i in candidates])
        reranker_scores={index:float(value) for index,value in zip(candidates,ranking)}
        candidates = [candidates[i] for i in np.argsort(-ranking)]
    result = []
    for i in candidates[:k]:
        c, d = rows[i]
        result.append({'chunk_id': c.id, 'document_id': d.id, 'title': d.title, 'page': c.page, 'section': c.section, 'version': d.version, 'effective_date': d.effective_date, 'uploaded_at': d.created_at, 'source_type': d.kind, 'permission': 'authorized staff policy', 'text': c.text, 'score': round(float(scores[i]), 6), 'synthetic': d.synthetic,'retrieval_strategy':settings.retrieval_mode,'semantic_score':float(semantic[i]),'keyword_score':float(keyword[i]),'reranker_score':reranker_scores.get(i)})
    return result


def grounded_answer(question, evidence):
    if not evidence:
        return {'answer': 'Insufficient evidence in the authorized knowledge base. Ask an administrator to add a current, reviewed policy.', 'evidence': [], 'citations': [], 'mode': 'local extractive', 'unsupported_claims': 0}
    return {'answer': '\n\n'.join(f"[{i + 1}] {e['text']}" for i, e in enumerate(evidence)), 'evidence': evidence, 'citations': [e['chunk_id'] for e in evidence], 'mode': 'local extractive — source passages, not personalized financial advice', 'unsupported_claims': 0}
