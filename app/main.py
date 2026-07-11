from fastapi import FastAPI

from app.api.products import router as products_router
from app.api.scripts import router as scripts_router

app = FastAPI(title="couparvi", version="0.1.0")
app.include_router(products_router)
app.include_router(scripts_router)


@app.get("/health")
def health():
    return {"status": "ok"}
