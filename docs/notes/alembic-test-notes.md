# Alembic Migration Test - How It Works & How Not to Break It

> Last updated: 2026-07-25
> Status: 108/108 backend tests passing

---

## 1. What the test does

`test_alembic_downgrade_and_upgrade_roundtrip` verifies that the **latest**
Alembic migration chain is fully reversible. It runs three steps against the
real PostgreSQL database:

1. `command.upgrade(config, "head")`   → applies all migrations
2. `command.downgrade(config, "base")` → rolls everything back to empty
3. `command.upgrade(config, "head")`   → re-applies all migrations

If any of these steps raises (e.g. `DuplicateTableError`, `UndefinedColumn`,
`DependencyError`), the test fails - meaning a migration is **not reversible**.

---

## 2. Why `_drop_all_tables()` exists (the trap to remember)

The session-scoped `configure_test_database` fixture in
`src/backend/tests/conftest.py` creates every table via
`Base.metadata.create_all(...)` **without stamping the `alembic_version`
table**. The result:

```
tables:   [alembic_version, users, devices, sessions, vaults]
alembic_version rows: []   ← EMPTY
```

With an empty `alembic_version`, Alembic thinks the database is at `base`
(no current revision), so `command.downgrade(config, "base")` becomes a
**no-op** - it has nothing to downgrade from. The tables created by the
fixture stay in place, and the subsequent `command.upgrade(config, "head")`
then fails with:

```
DuplicateTableError: relation "users" already exists
```

### The fix

Before the roundtrip, `_drop_all_tables(database_url)` connects directly
via `asyncpg` and runs:

```sql
DROP TABLE IF EXISTS "<tablename>" CASCADE
```

for **every** table in the `public` schema - including `alembic_version`.
This guarantees a truly clean slate so the upgrade→downgrade→upgrade
sequence is exercised against an empty database, exactly as Alembic would
see it in production.

---

## 3. Rules for future developers - DO NOT break this test

### DO
- **Add a `downgrade()` to every new migration.** It must undo everything
  `upgrade()` does, in reverse order. Drop indexes before columns, drop
  columns before tables, drop extensions last.
- **Test reversibility locally** before pushing:
  ```bash
  RUN_INTEGRATION=1 \
  DATABASE_URL="postgresql+asyncpg://easypassword_user:dev_password@localhost:5432/easypassword" \
  REDIS_URL="redis://localhost:6379/0" \
  SECRET_KEY="test-secret-key" \
  WEBAUTHN_RP_ID="localhost" \
  WEBAUTHN_ORIGIN="http://localhost:8000" \
  python -m pytest tests/integration/test_alembic_downgrade.py -x -s
  ```
- **Keep `down_revision` chained correctly.** Each migration must point to
  the previous one (`down_revision = "0001_initial_schema"`, etc.).
- **Use `op.f()` for constraint/index names** so downgrade can reference
  them reliably.

### DON'T
- **Don't rely on `Base.metadata.create_all` for migration tests.** That
  path bypasses Alembic entirely and leaves `alembic_version` empty - the
  root cause of the original failure.
- **Don't remove `_drop_all_tables()`** from the test. Without it, the
  fixture-created tables will collide with the upgrade step.
- **Don't run `command.upgrade` without a clean database first.** The test
  assumes it starts from an empty schema.
- **Don't add `op.create_table` for a table that already exists** in an
  earlier migration - extend the existing one with `op.add_column` /
  `op.alter_column` instead.
- **Don't forget to drop what you create.** If `upgrade()` adds a column,
  `downgrade()` must `op.drop_column` it. If `upgrade()` creates an index,
  `downgrade()` must `op.drop_index` it.

---

## 4. How to add a new migration (safe checklist)

1. `cd src/backend && alembic revision -m "describe_change"` - this
   generates `alembic/versions/000N_*.py` with `down_revision` already set.
2. Implement `upgrade()` **and** `downgrade()` symmetrically.
3. Run the roundtrip test locally (command in section 3).
4. Run the full suite to confirm 108+ still pass:
   ```bash
   RUN_INTEGRATION=1 DATABASE_URL="..." REDIS_URL="..." \
   SECRET_KEY="..." WEBAUTHN_RP_ID="localhost" WEBAUTHN_ORIGIN="http://localhost:8000" \
   python -m pytest tests/ -q
   ```
5. Commit the migration **and** any model changes together.

---

## 5. Current migration chain (as of this note)

```
base
 └─ 0001_initial_schema          (users, devices, sessions, vaults + pgcrypto)
     └─ 0002_device_metadata_single_dev   (device_metadata JSONB + partial unique index)
         └─ head
```

When you add `0003_*`, set `down_revision = "0002_device_metadata_single_dev"`
and make sure `downgrade()` removes whatever `0003` introduced.

---

## 6. Quick troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `DuplicateTableError: relation "users" already exists` | `_drop_all_tables` removed, or fixture tables still present | Restore `_drop_all_tables()` call before the roundtrip |
| `command.downgrade` does nothing | `alembic_version` table is empty | Ensure the test starts from a clean DB (drop all tables first) |
| `UndefinedColumn` on downgrade | `downgrade()` doesn't drop what `upgrade()` added | Make `downgrade()` symmetric to `upgrade()` |
| `NoRevisionMatch` / `RevisionId` errors | `down_revision` chain broken | Verify each migration's `down_revision` points to the previous revision id |
