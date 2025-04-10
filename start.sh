#!/bin/bash
alembic upgrade head
uvicorn src.api:app --reload &
python -m src.slack_bot &
celery -A src.lib.tasks worker --loglevel=info &
wait
