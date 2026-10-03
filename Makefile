.PHONY: install test frontend-build frontend-test validate evaluate check

install:
	python -m pip install -r backend/requirements.txt
	cd frontend && npm install --no-fund --no-audit

test:
	python -m pytest -q backend/tests

frontend-build:
	cd frontend && npm run build

frontend-test:
	cd frontend && npm test -- --run

validate:
	python backend/scripts/validate_catalog.py sample/messy_catalog.csv

evaluate:
	python backend/scripts/evaluate_queries.py sample/demo_queries.json

check: test frontend-build frontend-test validate evaluate
