# Origo Platform

This workspace contains three components:

- `origo-platform`: React + TypeScript frontend for the Groundlink platform.
- `origo-edge`: Python + FastAPI backend exposing Origo APIs and integrating with the adapter.
- `origo-info-adapter`: Python adapter layer mapping Origo jobs and payloads to Infostellar StellarStation API shapes.

## Run locally

1. Start the backend:
   - `cd origo-edge`
   - `python -m pip install -r requirements.txt` or use `pyproject.toml`
   - Set `STELLARSTATION_SERVICE_ACCOUNT_FILE` to your downloaded StellarStation service account JSON key if you want the adapter to connect to the real API.
   - Optionally set `STELLARSTATION_ENDPOINT` and `STELLARSTATION_AUDIENCE` if your environment differs from the public StellarStation API.
   - `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

2. Start the frontend:
   - `cd origo-platform`
   - `npm install`
   - `npm run dev`

The frontend expects the backend at `http://localhost:8000/api`.

The platform now models StellarStation's actual pass reservation flow: the backend returns available passes with `reservation_token`, and the frontend submits that token to the adapter. The adapter uses `ReservePassRequest` when the real StellarStation client is configured.
