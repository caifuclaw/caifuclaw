from fastapi import FastAPI

from .api.routes.connectors import router as connectors_router


app = FastAPI(title="CaifuClaw Connector Runtime", version="0.1.0")
app.include_router(connectors_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "connector_runtime"}
