.PHONY: up down build migrate test seed logs shell reset

up:
	docker compose up -d
	docker compose exec ollama ollama pull llama3.2:3b

down:
	docker compose down

build:
	docker compose build

migrate:
	docker compose exec backend alembic upgrade head

test:
	docker compose exec backend pytest tests/ -v

seed:
	@echo "Usage: make seed PROJECT_ID=<uuid> FOLDER=./docs TOKEN=<jwt>"
	docker compose exec backend python scripts/bulk_ingest.py \
	  --project-id $(PROJECT_ID) --folder $(FOLDER) --token $(TOKEN)

logs:
	docker compose logs -f backend worker

shell:
	docker compose exec backend bash

reset:
	docker compose down -v && docker compose up -d
