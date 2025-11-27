# Repository Guidelines

## Project Structure & Module Organization
- `app/` contains the FastAPI entry (`main.py`), routers (`api/`), Celery workers (`tasks/`), agents, shared services, and SQLAlchemy models; configure shared settings in `app/core`.
- The admin UI is implemented in `frontend/settings2` (Next.js); legacy Jinja templates were removed, but static assets still live in `app/static`. Docs, datasets, and prompt rules live in `docs/`, `training/`, and `data/`.
- Alembic tracks schemas under `migrations/`. Automated tests live in `test/`, and webhook simulators (`test_webhook.py`, `generate_test_data.sh`) reside at the repo root.

## Build, Test, and Development Commands
- `python -m venv venv && source venv/bin/activate` followed by `pip install -r requirements.txt`.
- `alembic upgrade head` keeps PostgreSQL aligned with the models.
- `uvicorn app.main:app --reload --host 0.0.0.0 --port 8444` for the API, plus `celery -A app.tasks.worker worker -l info -Q emails,ocr,processing,tagging`.
- `docker-compose up -d` launches API, Celery, RabbitMQ, Postgres, and Flower locally.
- `pytest`, `./test_webhook.py --template 2`, and `./generate_test_data.sh --count 10` cover automated and manual validation paths.
- UI work: `cd frontend/settings2 && npm install && npm run dev` to serve the modern `/settings2` experience on port 3000 (or the next free port).

## Coding Style & Naming Conventions
- Python 3.11, four-space indentation, and ~100-character lines; prefer type hints and Pydantic schemas for all request/response payloads.
- Use snake_case filenames and keep routers under versioned packages (`app/api/api_v1`). Co-locate Celery tasks with the service logic they orchestrate.
- Log with `loguru`, isolate constants/config in `app/core`, and run `black app test` plus `isort .` before opening a PR.

## Testing Guidelines
- Mirror the folder you modify, e.g., edits to `app/services/pdf_strikethrough_service.py` should yield `test/test_pdf_strikethrough_service.py`.
- Mock FrontApp/OpenAI calls, rely on parametrized pytest cases for classification branches, and keep the CLI scripts described in `TESTING.md` passing.

## Commit & Pull Request Guidelines
- Match the existing history: imperative subject lines with optional wrap-up bodies, grouping code, migrations, and docs by feature.
- PR descriptions should state purpose, list verification commands (pytest, Celery worker logs, webhook scripts), flag config/migration changes, and include screenshots for template updates. Link the relevant ticket or issue where possible.

## Security & Configuration Tips
- Copy `.env.example`, keep secrets outside version control, and store certificates in `certs/` (generate with `./generate_ssl_cert.sh`; inject production keys at deploy time).
- Update `app/core/config.py` when introducing new toggles, reuse `app/api/api_v1/endpoints/webhooks.py` signature helpers, and always pair schema changes with Alembic migrations documented in your PR.
