.PHONY: up down logs ps build restart clean test smoke

up: ## Build and start the stack (frontend :3000, backend :8000)
	docker compose up -d --build
	@echo "Frontend: http://localhost:3000"
	@echo "Backend:  http://localhost:8000/health"

down: ## Stop the stack (keeps the SQLite volume)
	docker compose down

build:
	docker compose build

restart: down up

logs:
	docker compose logs -f

ps:
	docker compose ps

clean: ## Stop the stack AND delete the SQLite volume
	docker compose down -v

test: ## Run backend unit tests in the local venv
	cd backend && python -m pytest -q

smoke: ## Real-provider smoke test against BASE_URL (default http://localhost:8000)
	cd backend && python scripts/smoke_live.py $(or $(BASE_URL),http://localhost:8000)
