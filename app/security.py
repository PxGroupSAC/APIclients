from starlette.middleware.base import RequestResponseEndpoint
from fastapi import Request, Response
from app.utils import hash_api_key
from app.database import SessionLocal
from app.models import Client, UsageStat
from sqlalchemy import func
from datetime import datetime

async def api_key_auth_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    PUBLIC_PATHS = ["/clients", "/usage"]

    if any(request.url.path.startswith(p) for p in PUBLIC_PATHS):
        return await call_next(request)

    api_key = request.headers.get("x-api-key")
    client_id = request.headers.get("x-client-id")

    db = SessionLocal()
    try:
        client = None

        if api_key:
            api_key_hash = hash_api_key(api_key)
            client = db.query(Client).filter(Client.api_key_hash == api_key_hash).first()
        elif client_id:
            client = db.query(Client).filter(Client.id == client_id).first()

        if not client:
            return Response("Invalid authentication", status_code=403)

        # Limite diario (solo para clientes autenticados con API key)
        if api_key:
            today = datetime.utcnow().date()
            today_usage_count = (
                db.query(func.count())
                .filter(
                    UsageStat.client_id == client.id,
                    func.date(UsageStat.timestamp) == today
                )
                .scalar()
            )

            if today_usage_count >= client.request_limit_per_day:
                return Response("Daily request limit exceeded", status_code=429)

            # Tracking solo si es API key
            usage = UsageStat(
                client_id=client.id,
                endpoint=request.url.path
            )
            db.add(usage)

        request.state.client = client
        response = await call_next(request)

        if api_key:
            db.commit()

        return response

    finally:
        db.close()
