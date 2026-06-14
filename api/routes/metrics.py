from fastapi import APIRouter, Query
from api.services.model_service import compute_metrics

router = APIRouter()

@router.get("/")
def metrics(domain: str = Query("hr_attrition", description="The business domain to query")):
    return compute_metrics(domain)