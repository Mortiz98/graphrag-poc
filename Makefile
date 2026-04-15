.PHONY: run run-api run-ui stop clean test seed init

DOCKER_UP := docker compose up -d
DOCKER_DOWN := docker compose down
API_CMD := uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
UI_CMD := PYTHONPATH=. uv run streamlit run ui/app.py --server.port 8501 --server.headless true

run: ## Start everything (Docker + API + Streamlit)
	@$(DOCKER_UP)
	@echo "Waiting for Docker services..."
	@sleep 3
	@echo "Initializing NebulaGraph schema (if needed)..."
	@PYTHONPATH=. uv run python -c "from scripts.init_nebula import init_schema; init_schema()" 2>/dev/null || echo "Schema init skipped (may already exist)"
	@echo "Starting API server..."
	@PYTHONPATH=. $(API_CMD) &
	@API_PID=$$!; \
	echo "API running (PID $$API_PID)"; \
	echo "Starting Streamlit UI..."; \
	$(UI_CMD); \
	kill $$API_PID 2>/dev/null

run-api: ## Start only the FastAPI server
	@$(DOCKER_UP)
	@PYTHONPATH=. $(API_CMD)

run-ui: ## Start only the Streamlit UI (API must be running)
	@$(UI_CMD)

stop: ## Stop Docker services
	@$(DOCKER_DOWN)
	@echo "Services stopped."

clean: ## Full reset — removes Docker volumes and caches
	@$(DOCKER_DOWN) -v
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned."

test: ## Run lint + format + unit tests
	@PYTHONPATH=. uv run ruff check app/ tests/ && uv run ruff format app/ tests/ && PYTHONPATH=. uv run pytest tests/ -v

seed: ## Load sample data into the system
	@PYTHONPATH=. uv run python -c "from scripts.seed import seed; seed()"

init: ## Initialize NebulaGraph schema
	@PYTHONPATH=. uv run python -c "from scripts.init_nebula import init_schema; init_schema()"

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'
