from fastapi import FastAPI
from api.routes import metrics, explain, adapt, drift

app = FastAPI(title="Self-Evolving AI System")

app.include_router(metrics.router, prefix="/metrics")
app.include_router(explain.router, prefix="/explain")
app.include_router(adapt.router, prefix="/adapt")
app.include_router(adapt.router, prefix="/drift")


@app.get("/")
def home():
    return {"message": "Self-Evolving AI Backend Running"}