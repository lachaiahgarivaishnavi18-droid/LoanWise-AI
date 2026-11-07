# Verification — 7 November 2026

Observed on Windows with Python 3.12, Node.js 24 and synthetic data. These results apply to this checkout and are not production certification.

| Check | Observed result |
|---|---|
| SQLite backend suite | 38 passed |
| PostgreSQL 16.15 backend suite | 38 passed using an isolated SCRAM-authenticated loopback cluster; server stopped afterward |
| Frontend | 6 tests passed; TypeScript check and Vite production build passed |
| Database migrations | Fresh and populated legacy upgrades passed; failed SQLite backfill rolled back without partial schema changes |
| Development database | Upgraded after backup; 48 domain tables, 500 applicants/applications/profiles, 6,000 repayment records; no foreign-key violations |
| OCR | Real local CPU OCR on generated PNG and image-only PDF; extracted income/debt candidates; disabled/pixel-budget cases tested |
| Normalized records | Multi-source finance preservation, correction history, exact policy revision provenance and stored prediction history tested |
| Security | Ownership, role/source permissions and revocation, prompt injection quarantine, reviewed-source verification boundaries and stale review prevention tested |
| Agents | 12 typed agent contracts; retry failure withholds final assessment |
| Models | Five synthetic models trained; split diagnostics, registered versions/evaluations, real SHAP and additivity checks passed |
| Feature governance | Service inference uses configured jurisdiction allowlists; excluded features withhold model estimates |
| Neural retrieval | Real CPU embedding and cross-encoder weights, persisted FAISS, unknown-query abstention and 12-agent assessment passed |
| Provider adapters | Four HTTP contract tests passed using MockTransport; external paid services were not called |
| Dependencies | pip check passed; core dependency constraints recorded separately from optional neural dependencies |
| Docker Compose | Official standalone CLI checksum and configuration validated |
| Docker execution | BLOCKED: no Docker engine pipe on this computer; images/build/runtime not verified |
| CI | PostgreSQL and container jobs prepared; remote workflow not run from this chat |

The neural benchmark passed nine product-scoped synthetic cases: Precision@5 0.2, Recall@5 1.0, MRR 1.0 and NDCG 1.0. Each policy fixture has one relevant chunk, explaining Precision@5. Citation coverage and exact-quote unsupported-claim checks passed; these structural checks are not independent LLM faithfulness evaluation or evidence of general retrieval quality.

Synthetic random-cohort fairness diagnostics were computed. Real demographic fairness remains NOT_EVALUATED. Models are research artifacts, not calibrated real-world credit assessments. Source OCR recognition scores never establish financial verification.

Local machine-readable reports are in ignored `runtime/verification/`: `postgres.json`, `docker.json`, `neural.json` and `local-database.json`. Development SQLite backup is in `backend/runtime/backups/`. The test suites use separate databases, credentials, model and data directories.

Reproduce backend checks from the project root:

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m pytest -q
Pop-Location
.\scripts\test-postgres.ps1 -PgBin .\runtime\tools\pg16\pgsql\bin
.\.venv\Scripts\python.exe scripts/test-neural.py
.\.venv\Scripts\python.exe scripts/test-containers.py
```

PostgreSQL binaries and neural weights must be available locally. The last command requires a running Docker engine and tests a uniquely named disposable stack, including PostgreSQL, migrations, OCR, SHAP, citations and frontend serving. It cleans up only that stack. It has not completed locally because the engine is absent. No Windows virtualization settings were changed.

Previous browser checks covered login, dashboard responsiveness, assessments, SHAP and policy citations. The new frontend changes were checked by tests/typecheck/build; this turn did not repeat visual browser inspection.

Remaining operational work includes institution-approved data/model validation, lawful feature and fairness governance, external provider validation, malware scanning, distributed workers/rate limits, SSO/recovery, derived-record retention and broader load/accessibility testing. Human decisions remain separate from AI assessments and trigger no lending action.

## Live Vercel / Neon result

On 7 November 2026 the full deployed check passed at https://loanwise-ai-eta.vercel.app. Both frontend and Python API production deployments reached READY. The final API deployment is `dpl_8TNmXEtG7J5YSNw6R3hT368X1CYE`; frontend is `dpl_ExRgYhy6Qwyvmb7y84hVa24S6nSV`.

Observed through the frontend's same-origin API proxy: secure-cookie login, 500 applications from Neon, twelve-agent assessment with five SHAP contributions, a cited policy answer, real image OCR, persistent original-byte download, and SPA deep-link serving. The small synthetic end-to-end check took 5.95 seconds on a warm deployment; this is a smoke check, not a load benchmark. Its machine-readable result is `runtime/verification/vercel.json`.

The dedicated serverless parser path additionally passed all four local OCR tests. The default SQLite and PostgreSQL suites passed 38 tests each; frontend tests/typecheck/build also passed. The clean cloud rebuild removed an obsolete desktop OpenCV artifact from the earlier build cache. The API uses Vercel's large-function beta for its scientific/OCR dependencies. See [deployment operations](DEPLOYMENT.md) for cloud limits and reproducibility.
