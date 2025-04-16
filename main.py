from fastapi import FastAPI
from app.routes import router as client_router
from app.security import api_key_auth_middleware

app = FastAPI()

# Middleware para validar API Key
app.middleware("http")(api_key_auth_middleware)

# Rutas principales
app.include_router(client_router)

