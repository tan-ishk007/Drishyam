# Container Operations

The included `docker-compose.yml` runs only four backend services: PostgreSQL, Redis, FastAPI API, and Celery worker. It neither copies nor references the separate DRISHYAM frontend project.

Use `cp .env.example .env`, set production secrets and an external email provider, then run `docker compose up --build`. Apply schema changes with `docker compose exec api alembic upgrade head`. The API will be exposed at `http://localhost:8000` and Swagger at `http://localhost:8000/docs`.

