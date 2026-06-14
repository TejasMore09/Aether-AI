from fastapi import APIRouter
from api.services.adaptation_service import adaptive_check

router = APIRouter()

@router.get("/")
def adapt():
    return adaptive_check()