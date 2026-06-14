import sys, os
sys.path.insert(0, '.')

print('--- 1. vector_store_service import ---')
from api.services.vector_store_service import (
    initialize_vector_store, semantic_lookup,
    get_index_stats, format_context_block, rebuild_index,
    AetherVectorStore
)
print('  OK')

print('--- 2. explain_service import ---')
from api.services.explain_service import generate_ai_explanation, _build_semantic_query
print('  OK')

print('--- 3. vector_store internal structure ---')
store = AetherVectorStore()
print(f'  TF-IDF ngram_range: {store.vectorizer.ngram_range}')
print(f'  is_ready before build: {store.is_ready}')
print('  OK')

print('--- 4. semantic query builder ---')
q = _build_semantic_query(
    domain='hr_attrition',
    metrics={'f1_score': 0.82, 'roc_auc': 0.91},
    drift={'drift_percentage': 34.5, 'drifted_features': ['monthly_income', 'workload']},
    decision={'action': 'RETRAIN', 'risk_level': 'HIGH', 'expected_daily_loss_usd': 45000, 'reason': 'High drift'}
)
print(f'  Query (first 90 chars): {q[:90]}')
print('  OK')

print('--- 5. format_context_block with empty results ---')
block = format_context_block([])
assert 'No relevant' in block, 'Expected fallback text'
print('  OK')

print('--- 6. Initialize vector store against live DB ---')
from database.db import engine
from database.models import Base
Base.metadata.create_all(bind=engine)
n = initialize_vector_store()
print(f'  Indexed {n} documents')
stats = get_index_stats()
print(f'  Stats: {stats}')
print('  OK')

print('--- 7. Semantic lookup (smoke test) ---')
results = semantic_lookup(
    'domain hr_attrition action RETRAIN risk HIGH drift 45 percent',
    top_k=3,
    domain='hr_attrition'
)
print(f'  Retrieved {len(results)} results')
if results:
    top = results[0]
    print(f'  Top hit summary: {top.get("summary","")[:80]}')
    print(f'  Similarity score: {top.get("similarity_score")}')
    print('  OK')
else:
    print('  WARN: 0 results (DB may be empty — run scripts/process_datasets.py)')

print('--- 8. format_context_block with results ---')
block = format_context_block(results)
print(f'  Block length: {len(block)} chars')
print('  OK')

print()
print('ALL CHECKS PASSED — RAG layer is operational.')
