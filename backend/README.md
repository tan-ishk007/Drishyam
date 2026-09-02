# DRISHYAM Backend MVP

This repository is a **separate, independently runnable Python backend** for NyayTrace / DRISHYAM. It is intentionally isolated from the existing frontend: it does not mount, import, modify, or otherwise connect to that project. The MVP follows one real path for fictional evidence: **authenticated investigator → case authorization → upload → streamed SHA-256 receipt → private object storage → Celery processing → parser/OCR extraction → canonical events/entities → timeline, graph, transactions, and alerts → human review → dynamic PDF**.

> **Safety boundary.** All files under `generated_evidence/` are explicitly fictional training artifacts. Derived records are reviewable investigative leads, not claims of guilt.

| Component | MVP implementation | Production consideration |
|---|---|---|
| API and validation | FastAPI with OpenAPI/Swagger | Run behind TLS and a managed reverse proxy. |
| Persistence | PostgreSQL with SQLAlchemy and Alembic | Back up encrypted storage and database separately. |
| Jobs | Celery and Redis queues | Monitor queue health and task failures. |
| Evidence | Private filesystem abstraction, streamed hash receipts | Swap the abstraction for S3-compatible encrypted object storage. |
| Extraction | TXT/EML/CSV/XLSX/PDF, PyMuPDF, Tesseract OCR, regex normalization | Add model-based extraction only with evaluation and human-review controls. |
| Reporting | ReportLab PDF generated from current case records | Apply jurisdictional redaction and retention policy. |

## Run locally with PostgreSQL and Redis

The application does **not** run `create_all()` at startup. Initialize schema from Alembic migrations.

```bash
cd /home/ubuntu/drishyam-backend
cp .env.example .env
# Set DATABASE_URL, SECRET_KEY, OTP_PEPPER, and production email settings in .env.
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Run the worker in another terminal.

```bash
cd /home/ubuntu/drishyam-backend
celery -A app.workers.celery_app.celery_app worker --loglevel=INFO --queues=evidence_fast,evidence_ocr,evidence_parse,evidence_enrich,reports
```

Open `http://localhost:8000/docs` for Swagger, `http://localhost:8000/redoc` for ReDoc, and `/api/v1/preview/cases/{case_id}` for the protected backend-only HTML view. Exact endpoint contracts are summarized in [`docs/OPENAPI.md`](docs/OPENAPI.md).

## Run with Docker Compose

```bash
cd /home/ubuntu/drishyam-backend
cp .env.example .env
# For Docker, set DATABASE_URL=postgresql+psycopg://drishyam:drishyam@db:5432/drishyam
# and REDIS_URL=redis://redis:6379/0 in .env.
docker compose up --build
```

The compose file contains **only** `db`, `redis`, `api`, and `worker`. It intentionally contains no frontend service. See [`docker/README.md`](docker/README.md).

## Generate and process fictional demo evidence

```bash
cd /home/ubuntu/drishyam-backend
python3 scripts/generate_synthetic_evidence.py
python3 scripts/run_demo.py
```

The second command uses FastAPI’s HTTP surface rather than direct fixture inserts. It creates a verified synthetic account, uploads six actual generated files, processes them eagerly for local reproducibility, records review decisions, creates a PDF, and writes `demo_run.json`. The latest PDF copy is written to `generated_reports/demo_report_latest.pdf`.

## Tests

The integration tests expect local PostgreSQL and Redis availability and use the isolated `drishyam` database configured in `tests/conftest.py`.

```bash
cd /home/ubuntu/drishyam-backend
alembic upgrade head
pytest
```

The suite verifies end-to-end generated evidence, authentication, case object authorization, invalid file type rejection, duplicate-hash rejection, malformed CSV failure, corrupt-PDF worker failure persistence, and report failure behavior.

## Security and operational notes

The service requires verified accounts, bearer JWT sessions, server-side logout revocation, owner or membership checks for every case resource, private original storage, SHA-256 integrity receipts, and audit records for account, case, evidence, review, and report actions. Development OTP delivery writes only to an ignored local mailbox. For this local prototype, configure `EMAIL_PROVIDER=gmail_smtp`, `GMAIL_SMTP_EMAIL`, and a Google App Password only in the protected runtime env file; never place the App Password in source, frontend settings, Git, or an archive. Gmail SMTP is a prototype delivery route, not a production transactional-email architecture. Do not use development defaults or generated evidence in a real investigation.

References: [FastAPI security documentation](https://fastapi.tiangolo.com/tutorial/security/), [Celery task documentation](https://docs.celeryq.dev/en/stable/userguide/tasks.html), and the [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).
