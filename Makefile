.DEFAULT_GOAL := help
PY := uv run

help:  ## list targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n",$$1,$$2}'

install:            ## sync all deps (python + node)
	uv sync --all-packages --all-extras
	cd origo-platform && npm ci

proto:              ## regenerate StellarStation stubs from vendored .proto
	$(PY) python origo-info-adapter/scripts/gen_proto.py

proto-origo:        ## regenerate Origo Terrestrial stubs
	$(PY) python origo-station-agent/scripts/gen_proto.py

lint:               ## ruff + mypy + eslint
	$(PY) ruff format --check .
	$(PY) ruff check .
	$(PY) mypy origo-edge/src origo-info-adapter/src
	cd origo-platform && npm run lint && npx tsc --noEmit

fmt:                ## autofix
	$(PY) ruff format . && $(PY) ruff check --fix .
	cd origo-platform && npm run fmt

test:               ## unit tests (no network, no creds)
	$(PY) pytest origo-info-adapter origo-edge -m "not integration"

test-int:           ## integration tests (needs STELLARSTATION_API_KEY_PATH)
	$(PY) pytest -m integration

migrate:            ## apply migrations
	cd origo-edge && $(PY) alembic upgrade head

revision:           ## m="msg" make revision
	cd origo-edge && $(PY) alembic revision --autogenerate -m "$(m)"

openapi:            ## regenerate docs/openapi.json + frontend types
	$(PY) python origo-edge/scripts/export_openapi.py > docs/openapi.json
	cd origo-platform && npx openapi-typescript ../docs/openapi.json -o src/shared/api/schema.d.ts

contracts:          ## CI gate: schema must match committed artifact
	$(PY) python origo-edge/scripts/export_openapi.py | diff -u docs/openapi.json - \
	  || (echo "OpenAPI drift — run 'make openapi' and commit"; exit 1)

up:                 ## local infra
	docker compose up -d
dev-edge:
	cd origo-edge && $(PY) uvicorn origo_edge.main:app --reload --port 8000
dev-worker:
	cd origo-edge && $(PY) arq origo_edge.workers.settings.WorkerSettings
dev-ui:
	cd origo-platform && npm run dev