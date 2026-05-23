.PHONY: dev down logs

dev:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f api db