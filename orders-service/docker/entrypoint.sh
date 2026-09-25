#!/bin/sh
set -e
alembic upgrade head
python -m orders_service.seed
python -m orders_service.grpc_server &
exec uvicorn orders_service.rest:create_app --factory --host 0.0.0.0 --port 8000
