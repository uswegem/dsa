from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin, auth, commission, exceptions_view, reports, uploads

app = FastAPI(title="DSA/DTL Commission Calculation App")

app.include_router(auth.router)
app.include_router(uploads.router)
app.include_router(commission.router)
app.include_router(exceptions_view.router)
app.include_router(reports.router)
app.include_router(admin.router)

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")


@app.get("/")
def index():
    return FileResponse("frontend/static/index.html")


@app.get("/api/health")
def health():
    return {"status": "ok"}
