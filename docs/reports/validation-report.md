# Validation Report

Summary of validation steps performed:

- Backend linters: `ruff check .` — All checks passed.
- Backend formatting: `black --check .` — Passed.
- Backend unit tests: `pytest -q src/backend/tests/unit` — 20 tests were skipped (environment-dependent).
- OpenAPI spec: generated and saved to `docs/api-contracts-v1.json`.
- Frontend lint/format: `npm run lint` and `prettier --write .` — Passed.
- Frontend unit tests: `npm test` — All tests passed (14 tests).
- Frontend audit: captured summary in `docs/npm-audit-frontend.json` (55 vulnerabilities; many fixes require major upgrades).

Next recommended actions:

1. Run integration tests with Docker Compose:

```bash
cd src/infra/docker
docker-compose up --build
# then, in another shell
pytest -q
```

2. Review `docs/npm-audit-frontend.json` and plan Angular/tooling upgrades; these are breaking and should be scheduled.

3. Re-run backend integration tests after ensuring Postgres/Redis are available and Alembic migrations applied:

```bash
cd src/backend
alembic upgrade head
pytest -q
```
