import os

def database_url() -> str:
    return os.environ.get("DATABASE_URL", "sqlite:///./orders.db")

def grpc_port() -> int:
    return int(os.environ.get("GRPC_PORT", "50051"))
