from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.mysql import JSON
from datetime import datetime
from app.database import Base
from datetime import datetime

class Client(Base):
    __tablename__ = "clients"

    id = Column(String(36), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    api_key_hash = Column(Text, nullable=False)
    environment = Column(String(50), nullable=False)
    allowed_apis = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    request_limit_per_day = Column(Integer, default=1000)

class UsageStat(Base):
    __tablename__ = "usage_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(String(36), ForeignKey("clients.id"), index=True)
    endpoint = Column(String(255), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    count = Column(Integer, default=1)

    client = relationship("Client", backref="usages")

class Api(Base):
    __tablename__ = "apis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    base_url = Column(String(255), nullable=False)
    enabled = Column(Integer, default=1)
    allowed_methods = Column(JSON, default=["POST"])
    api_key = Column(Text, nullable=True)  # hash de la API key

class ClientApiKey(Base):
    __tablename__ = "client_api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(String(36), ForeignKey("clients.id"))
    api_name = Column(String(100))
    api_key = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


