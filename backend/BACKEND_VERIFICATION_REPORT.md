# DRISHYAM Backend MVP — Verification Report

**Date:** 22 August 2026  
**Repository:** `/home/ubuntu/drishyam-backend/`  
**Scope statement:** This backend was implemented as an independent Python repository. The existing `/home/ubuntu/nyaytrace/` frontend was not imported, mounted, modified, or connected during this implementation.

> **Verification conclusion:** The standalone MVP has been exercised end to end with only generated, explicitly fictional evidence. Files traveled through the API upload path, private storage, SHA-256 integrity receipt, parser/OCR extraction, normalized database records, transaction and graph projection, rule-based alerts, human review, and dynamic PDF generation. The output is framed as reviewable leads, not a finding of guilt.

## 1. Executed environment

| Component | Validation result |
|---|---|
| Runtime | Python 3.12.3 with FastAPI, SQLAlchemy, Alembic, Celery, ReportLab, PyMuPDF, pandas, NetworkX, Pillow, and pytesseract installed. |
| Database | Local PostgreSQL 16 database `drishyam` created and used for actual migrations, API data, demo records, and test records. |
| Queue | Local Redis responded to `PING`; Celery was run eagerly in deterministic automated tests and demo execution. |
| OCR | Tesseract 5.3 was installed and exercised on a generated UPI receipt image. |
| Migration state | Alembic upgraded to revision `2b44d632b1b2` after applying the initial relational schema and JWT-revocation migration. |
| Container configuration | `Dockerfile` and backend-only `docker-compose.yml` were created for API, worker, PostgreSQL, and Redis. The Docker CLI was unavailable in this validation environment, so compose runtime execution was not claimed. |

## 2. Actual synthetic evidence run

The command `bash scripts/run_checks.sh` applied migrations, ran automated tests, generated evidence, and executed the public FastAPI workflow. The final execution created case `DRI-20260822-091838658820` and generated a new report snapshot. No direct database fixture was used for the demo path.

| Evidence artifact | Ingest path exercised | Result |
|---|---|---|
| `whatsapp_chat_synthetic.txt` | Text parser → event and indicator extraction | Completed with integrity receipt. |
| `phishing_offer_synthetic.eml` | RFC-style email parser → URL, email, phone, and amount extraction | Completed with integrity receipt. |
| `bank_statement_synthetic.csv` | CSV parser → normalized transaction records | Completed with integrity receipt. |
| `call_log_synthetic.csv` | CSV parser → call-log events and identifier extraction | Completed with integrity receipt. |
| `upi_receipt_synthetic.png` | Tesseract OCR → event and payment indicator extraction | Completed with integrity receipt. |
| `complaint_statement_synthetic.pdf` | PyMuPDF text extraction → complaint events and indicators | Completed with integrity receipt. |

| Derived result | Actual final count |
|---|---:|
| Evidence files | 6 |
| Distinct normalized entities | 26 |
| Timeline events | 36 |
| Transactions | 8 |
| Reviewable alerts | 9 |
| NetworkX graph nodes | 76 |
| NetworkX graph edges | 108 |
| Generated reports | 1 |

The generated report is located at [`generated_reports/demo_report_latest.pdf`](generated_reports/demo_report_latest.pdf). `pdfinfo` verified a **3-page**, **7,946-byte**, PDF 1.4 document. Its file SHA-256 was `c87bb8073e9a4bb37bfc1206b4957e898a09f6745168c9bf9b602b8d4d988fc0` at validation time. The data snapshot and individual evidence receipts are retained in [`demo_run.json`](demo_run.json).

## 3. Automated test evidence

The command below completed successfully against PostgreSQL with **6 passed** tests.

```bash
cd /home/ubuntu/drishyam-backend
DATABASE_URL='postgresql+psycopg://drishyam:drishyam@localhost:5432/drishyam' pytest
```

| Test coverage | Verified behavior |
|---|---|
| API end-to-end workflow | Six generated files reached completed state; the API returned at least 10 timeline events, 3 transactions, 3 alerts, a graph above 12 nodes, a review decision, and a valid PDF. |
| Authentication and authorization | Missing bearer credentials were rejected; an unrelated verified investigator received `403` for a case they did not own. |
| Upload validation | Unsupported `.exe` evidence was rejected with `415`; configured size limits returned `413`. |
| Integrity and idempotency | Re-uploading the same byte stream into one case was rejected with `409` because its SHA-256 already existed. |
| Worker failure persistence | Corrupt PDF, malformed CSV, and blank-image OCR cases were accepted as records then finished in explicit `failed` state with retained failure metadata. |
| Report failure behavior | A missing report identifier raised an error rather than fabricating a report document. |

The complete validation log is retained in [`validation_run.log`](validation_run.log).

## 4. Backend surface and preview

The independently running API health check returned:

```json
{"status":"ok","service":"drishyam-backend","environment":"development"}
```

Swagger was also rendered successfully and exposed versioned account, cases, evidence, analysis, review/report, and backend-preview operations. The runtime preview links are intentionally separate from the existing frontend.

| Surface | Status | Purpose |
|---|---|---|
| `/health` | Verified | Service liveness and identity. |
| `/docs` | Verified | Interactive Swagger OpenAPI 3.1 documentation. |
| `/openapi.json` | Available | Machine-readable API contract. |
| `/api/v1/preview/cases/{case_id}` | Implemented, authenticated | Backend-only HTML view of case counts and evidence SHA-256 receipts. |
| `/api/v1/cases/{case_id}/timeline` | Implemented, authenticated | Canonical event chronology. |
| `/api/v1/cases/{case_id}/graph` | Implemented, authenticated | NetworkX-derived node and edge projection. |
| `/api/v1/cases/{case_id}/transactions` | Implemented, authenticated | Derived transaction trail. |
| `/api/v1/cases/{case_id}/alerts` | Implemented, authenticated | Rule explanations and review state. |

## 5. Frontend-ready contract, without integration

No frontend code was changed. A future client can use the bearer-token endpoints below without any backend design change.

| User flow | Contract sequence |
|---|---|
| Verified sign-in | `POST /api/v1/auth/signup` → `POST /verify` → `POST /login` → bearer token. |
| Case workspace | `GET /api/v1/cases` → `GET /api/v1/cases/{case_id}`. |
| Evidence journey | Multipart `POST /api/v1/cases/{case_id}/evidence` → poll evidence status → read timeline, graph, transactions, and alerts. |
| Investigator review | `POST /api/v1/cases/{case_id}/review/{subject_type}/{subject_id}`. |
| Report workflow | `POST /api/v1/cases/{case_id}/reports` → poll `/reports` → download `/reports/{report_id}/download`. |

## 6. Security posture and known MVP limits

Case object authorization is enforced before case, evidence, analysis, review, report, original-download, and preview access. Originals live outside the served web root; evidence upload is streamed, extension/signature checked, size limited, stored with generated object keys, and accompanied by SHA-256. Account credentials and OTPs are not logged, and sensitive actions create audit entries. These controls align with the documented FastAPI security patterns, Celery task handling guidance, and OWASP file-upload recommendations. [1] [2] [3]

The deployment configuration is intentionally MVP-grade. Development OTPs are written only to the ignored local mailbox; the approved local prototype can use `EMAIL_PROVIDER=gmail_smtp` plus a Gmail address and Google App Password held only in the protected runtime env file. A production deployment should replace Gmail SMTP with a dedicated transactional provider, HTTPS, a secret manager, secure S3-compatible object storage, encrypted backup/retention policies, observability, and operational queue monitoring. Deterministic parsing, regex extraction, and Tesseract OCR provide reproducible leads but require human verification. Docker definitions were authored but not executed here because the Docker CLI was absent; this is the only unvalidated infrastructure item.

## References

[1]: https://fastapi.tiangolo.com/tutorial/security/ "FastAPI Security"
[2]: https://docs.celeryq.dev/en/stable/userguide/tasks.html "Celery Tasks"
[3]: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html "OWASP File Upload Cheat Sheet"
