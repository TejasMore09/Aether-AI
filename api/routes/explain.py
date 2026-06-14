from fastapi import APIRouter
from api.services.model_service import compute_metrics
from api.services.explain_service import generate_ai_explanation

router = APIRouter()

@router.get("/")
def explain():

    metrics = compute_metrics()
    explanation = generate_ai_explanation(metrics)

    metrics["ai_explanation"] = explanation

    return metrics