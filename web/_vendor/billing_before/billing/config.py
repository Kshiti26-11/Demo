import os


def orders_rest_url() -> str:
    return os.environ.get("ORDERS_REST_URL", "http://localhost:8000")


def orders_grpc_addr() -> str:
    return os.environ.get("ORDERS_GRPC_ADDR", "localhost:50051")


def reports_db_url() -> str:
    return os.environ.get("REPORTS_DB_URL", "sqlite:///./orders_replica.db")
