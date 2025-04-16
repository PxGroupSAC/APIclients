from fastapi import APIRouter, Request, HTTPException, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
import httpx

from app.database import SessionLocal
from app.models import Client, Api, UsageStat, User, ClientApiKey
from app.token_manager import get_bearer_token
from app.utils import generate_api_key, hash_api_key, hash_password, verify_password
from fastapi.responses import StreamingResponse
import csv
import io



# Clave maestra de administración
MASTER_KEY = "superadmin-secret-key"  # ← para producción, usar os.getenv()

def verify_master_key(x_admin_key: str = Header(...)):
    if x_admin_key != MASTER_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")



router = APIRouter()

# ===================
# MODELOS
# ===================

class ClientCreateRequest(BaseModel):
    name: str
    environment: str
    allowed_apis: List[str]

class ClientResponse(BaseModel):
    client_id: str
    api_key: str

# ===================
# DB DEPENDENCY
# ===================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# TEMP
@router.post("/debug-json")
async def debug_json(request: Request):
    body = await request.json()
    print("📦 JSON recibido en debug-json:", body)
    return {"received": body}

@router.get("/")
def healthcheck():
    print("✅ Backend levantado")
    return {"status": "ok"}


# ===================
# CREATE CLIENT
# ===================

@router.post("/clients", response_model=ClientResponse)
def create_client(request: ClientCreateRequest, db: Session = Depends(get_db)):
    from uuid import uuid4

    client_id = str(uuid4())
    api_key = generate_api_key()
    api_key_hash = hash_api_key(api_key)

    new_client = Client(
        id=client_id,
        name=request.name,
        api_key_hash=api_key_hash,
        environment=request.environment,
        allowed_apis=request.allowed_apis
    )

    db.add(new_client)
    db.commit()

    return ClientResponse(client_id=client_id, api_key=api_key)

# ===================
# PROXY
# ===================

@router.post("/register")
def register_user(email: str, password: str, db: Session = Depends(get_db)):
    # Crear el usuario
    hashed = hash_password(password)
    new_user = User(email=email, password_hash=hashed)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Crear el cliente asociado
    from uuid import uuid4
    client = Client(
        id=str(uuid4()),
        name=email.split("@")[0],
        environment="prod",
        allowed_apis=[],
        api_key_hash="",  # o generás una por defecto
        user_id=new_user.id
    )
    db.add(client)
    db.commit()

    return {
        "client_id": client.id,
        "message": "Cuenta creada con éxito"
    }

class LoginRequest(BaseModel):
    email: str
    password: str

@router.post("/login")
async def login_user(payload: LoginRequest, db: Session = Depends(get_db)):
    print("📥 Login request:", payload.email, payload.password)

    user = db.query(User).filter_by(email=payload.email).first()
    if not user:
        print("❌ Usuario no encontrado")
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    print("🔐 Stored hash:", user.password_hash)
    print("🔐 Provided hash:", hash_password(payload.password))

    if not verify_password(payload.password, user.password_hash):
        print("❌ Contraseña incorrecta")
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")

    client = db.query(Client).filter_by(user_id=user.id).first()
    if not client:
        print("❌ Cliente no encontrado")
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    print("✅ Login exitoso")
    return {
        "client_id": client.id,
        "name": client.name,
        "allowed_apis": client.allowed_apis
    }






@router.put("/clients/{client_id}/limit")
def update_client_limit(
    client_id: str,
    new_limit: int,
    db: Session = Depends(get_db),
    _: None = Depends(verify_master_key)
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    client.request_limit_per_day = new_limit
    db.commit()
    
    return {"message": "Limit updated", "client_id": client.id, "new_limit": new_limit}

@router.get("/clients/me/api-keys")
def get_client_api_keys(request: Request, db: Session = Depends(get_db)):
    client = getattr(request.state, "client", None)
    if not client:
        raise HTTPException(status_code=401, detail="Unauthorized")

    keys = db.query(ClientApiKey).filter_by(client_id=client.id).all()
    return [
        {"api_name": key.api_name, "api_key": key.api_key, "created_at": key.created_at}
        for key in keys
    ]


@router.get("/clients/all")
def get_all_clients(format: str = "json", db: Session = Depends(get_db),_: None = Depends(verify_master_key)):
    clients = db.query(Client).all()

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "name", "environment", "allowed_apis", "created_at"])
        for client in clients:
            writer.writerow([
                client.id,
                client.name,
                client.environment,
                ",".join(client.allowed_apis),
                client.created_at
            ])
        output.seek(0)
        return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=clients.csv"})

    return [
        {
            "id": client.id,
            "name": client.name,
            "environment": client.environment,
            "allowed_apis": client.allowed_apis,
            "created_at": client.created_at
        }
        for client in clients
    ]


@router.get("/usage")
def get_usage(format: str = "json", db: Session = Depends(get_db),_: None = Depends(verify_master_key)):
    from sqlalchemy import func
    usage = (
        db.query(
            UsageStat.client_id,
            UsageStat.endpoint,
            func.count().label("count")
        )
        .group_by(UsageStat.client_id, UsageStat.endpoint)
        .all()
    )

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["client_id", "endpoint", "count"])
        for row in usage:
            writer.writerow([row.client_id, row.endpoint, row.count])
        output.seek(0)
        return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=usage.csv"})

    # Default JSON
    return [
        {
            "client_id": row.client_id,
            "endpoint": row.endpoint,
            "count": row.count
        }
        for row in usage
    ]

@router.post("/clients/{client_id}/apis/{api_name}/activate")
def activate_api_for_client(client_id: str, api_name: str, db: Session = Depends(get_db)):
    client = db.query(Client).filter_by(id=client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    existing = db.query(ClientApiKey).filter_by(client_id=client_id, api_name=api_name).first()
    if existing:
        return {"message": "API already activated", "api_key": existing.api_key}

    new_key = generate_api_key()
    api_key = ClientApiKey(client_id=client_id, api_name=api_name, api_key=new_key)
    db.add(api_key)
    db.commit()

    return {"message": "API activated", "api_key": new_key}


@router.get("/apis")
def get_visible_apis(
    request: Request,
    db: Session = Depends(get_db),
    admin_key: str = Header(None)
):
    # Modo admin
    if admin_key == MASTER_KEY:
        apis = db.query(Api).all()
    else:
        # Modo cliente (desde middleware)
        client = getattr(request.state, "client", None)
        if not client:
            raise HTTPException(status_code=401, detail="Missing authentication")

        apis = db.query(Api).filter(Api.name.in_(client.allowed_apis)).all()

    return [
        {
            "name": api.name,
            "base_url": api.base_url,
            "enabled": bool(api.enabled),
            "allowed_methods": api.allowed_methods
        }
        for api in apis
    ]

@router.get("/clients/me")
def get_authenticated_client(request: Request):
    client = getattr(request.state, "client", None)
    if not client:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    return {
        "id": client.id,
        "name": client.name,
        "environment": client.environment,
        "allowed_apis": client.allowed_apis,
        "request_limit_per_day": client.request_limit_per_day,
        "created_at": client.created_at,
    }

@router.get("/clients/me/api-keys")
def get_client_api_keys(request: Request, db: Session = Depends(get_db)):
    client = getattr(request.state, "client", None)
    if not client:
        raise HTTPException(status_code=401, detail="Unauthorized")

    keys = db.query(ClientApiKey).filter_by(client_id=client.id).all()
    return [
        {
            "api_name": key.api_name,
            "api_key": key.api_key,
            "created_at": key.created_at
        }
        for key in keys
    ]


@router.post("/apis/{name}/regenerate-key")
def regenerate_api_key(name: str, _: None = Depends(verify_master_key)):
    db = SessionLocal()
    try:
        api = db.query(Api).filter_by(name=name).first()
        if not api:
            raise HTTPException(status_code=404, detail="API not found")

        new_key = generate_api_key()
        api.api_key = hash_api_key(new_key)
        db.commit()

        return {"name": api.name, "new_api_key": new_key}
    finally:
        db.close()

@router.api_route("/proxy/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_handler(full_path: str, request: Request):
    client = request.state.client  # Middleware auth
    db = SessionLocal()

    try:
        path_parts = full_path.split("/")
        if not path_parts or len(path_parts) < 1:
            raise HTTPException(status_code=400, detail="Invalid path")

        api_name = path_parts[0]

        if api_name not in client.allowed_apis:
            raise HTTPException(status_code=403, detail="Access to API not allowed")

        api = db.query(Api).filter_by(name=api_name, enabled=True).first()
        if not api:
            raise HTTPException(status_code=404, detail="API not found")

        bearer_token = get_bearer_token()

        headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "User-Agent": "px-proxy/1.0"
        }


        async with httpx.AsyncClient() as client_http:
            proxy_url = f"{api.base_url}/{full_path}"
            method = request.method
            body = await request.body()

            #import json
            #try:
               # print("Request Body (parsed):", json.loads(body))
            #except Exception:
               # print("Could not parse body.")


            #print(f"Forwarding to: {proxy_url}")
            #print(f"Headers: {headers}")
            #print(f"Method: {method}")
            #print(f"Body size: {len(body)} bytes")


            json_data = await request.json()
            #print("JSON parsed:", json_data)

            proxy_response = await client_http.request(
                method=method,
                url=proxy_url,
                json=json_data,
                headers=headers
            )

        try:
            return JSONResponse(
                status_code=proxy_response.status_code,
                content=proxy_response.json()
            )
        except Exception:
            return Response(
                status_code=proxy_response.status_code,
                content=proxy_response.content,
                media_type=proxy_response.headers.get("content-type", "application/octet-stream")
            )


    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Proxy request failed: {e}")

    finally:
        db.close()
