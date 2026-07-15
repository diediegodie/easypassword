# Backend Tests

This file describes how to run the backend test suite in all supported environments.

## 1. Prerequisites

- Python 3.12
- `venv` or a virtual environment activated
- Dependencies installed in `src/backend` via `pip install -r requirements.txt`
- If you will run integration tests, Docker Compose must be running for PostgreSQL and Redis

## 2. Running locally (host)

### 2.1 Run only unit tests

```bash
cd /home/diediegodie/documentos/github/projetos/easypassword/src/backend
pytest tests/unit/ -v --tb=short
```

### 2.2 Run integration and the full suite

```bash
cd /home/diediegodie/documentos/github/projetos/easypassword/src/backend
RUN_INTEGRATION=1 pytest -v --tb=short
```

### 2.3 Run only integration tests

```bash
cd /home/diediegodie/documentos/github/projetos/easypassword/src/backend
RUN_INTEGRATION=1 pytest tests/integration/ -v --tb=short
```

> Important: without `RUN_INTEGRATION=1`, tests marked with `integration` or tests that use database/Redis fixtures will be skipped.

## 3. Running with Docker Compose

### 3.1 Start the required services

```bash
cd /home/diediegodie/documentos/github/projetos/easypassword/src/infra/docker
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d
sleep 5
```

### 3.2 Run the tests on the host with Docker services active

```bash
cd /home/diediegodie/documentos/github/projetos/easypassword/src/backend
RUN_INTEGRATION=1 pytest -v --tb=short
```

### 3.3 Stop the Docker services

```bash
cd /home/diediegodie/documentos/github/projetos/easypassword/src/infra/docker
docker compose -f docker-compose.yml -f docker-compose.override.yml down
```

## 4. Running inside the backend container

If you already have the `easypassword_backend` container running, open a shell inside it:

```bash
docker exec -it easypassword_backend sh
```

Then run:

```bash
cd /app
export RUN_INTEGRATION=1
pytest -v --tb=short
```

## 5. Recommended CI commands

In CI, always use:

```bash
cd /home/diediegodie/documentos/github/projetos/easypassword/src/backend
RUN_INTEGRATION=1 pytest -v --tb=short
```

If the CI needs to run only integration tests:

```bash
cd /home/diediegodie/documentos/github/projetos/easypassword/src/backend
RUN_INTEGRATION=1 pytest tests/integration/ -v --tb=short
```

## 6. Quick tips

- `RUN_INTEGRATION=1` is required to avoid `skip` on integration/DB tests.
- If the containers are running, the backend uses `postgres` and `redis` as external services.
- To tear down and recreate, use `docker-compose down` followed by `docker-compose up -d`.
