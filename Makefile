.PHONY: pitch-demo pitch-demo-no-browser backend frontend install test build health

# One-command pitch demo — i5 / 16GB / No GPU / Venue internet = Yes
# Starts backend (CPU-only, waits for /health is_real) + frontend (5173) + browser
pitch-demo:
	@bash scripts/pitch-demo.sh

pitch-demo-no-browser:
	@bash scripts/pitch-demo.sh --no-browser

# Granular targets (for debugging)
backend:
	uvicorn backend.main:app --host 0.0.0.0 --port 8000

frontend:
	npm --prefix frontend run dev -- --host 0.0.0.0 --port 5173

health:
	curl -s http://localhost:8000/health | jq 2>/dev/null || curl -s http://localhost:8000/health
	@echo "---"
	curl -s http://localhost:8000/api/health | jq 2>/dev/null || curl -s http://localhost:8000/api/health

install:
	pip install -r requirements.txt --index-url https://download.pytorch.org/whl/cpu
	npm --prefix frontend install

test:
	pytest tests/ -v

build:
	npm --prefix frontend run build
