from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine
from app.models.base import Base
from app.core.config import get_settings
from app.routers.auth import router as auth_router
import app.models

settings = get_settings()

app = FastAPI(title= "LegalRAG API")
app.add_middleware(
    CORSMiddleware,
    allow_origins= settings.cors_origin_list,
    allow_credentials= True,
    allow_methods=["*"],
    allow_headers= ["*"],
)

Base.metadata.create_all(bind = engine)

@app.get("/")
def root():
    return {"message": "Hello LegalRag"}

app.include_router(auth_router)