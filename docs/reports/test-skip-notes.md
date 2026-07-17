# Test Skip Notes

During validation, backend unit tests were executed and all tests in `src/backend/tests/unit` were skipped (20 skipped). These tests are marked skipped because they require external services or specific environment variables (Postgres, Redis, or AWS-like secrets) that are not available in this automated validation run.

Recommended next steps:

- Run the skipped tests locally or in CI with the required services available (Docker Compose or test containers).
- Ensure the test environment provides the expected environment variables (DB URL, Redis URL, salt/keys) or update tests to use local in-memory fixtures.
- If some skipped tests are intentionally out-of-scope for CI, add explanatory markers and document the acceptance criteria.
