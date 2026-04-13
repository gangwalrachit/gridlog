# GridLog — Prompting Journal

Documents the AI-assisted development process for GridLog.
Logs key prompts, decisions, corrections, and reasoning.

> Intention: Plan before implement.

---

## Prompt 1 — Project Kickoff

**Date:** 10 April 2026
**Tool:** Claude Code

**Prompt:** Initial project brief — context, stack, working contract, first
planning task (no code).

**What I wanted to achieve:** Set up a working contract with AI — plan first,
no code until approved, architecture documented, AI as collaborator not
autocomplete.

**Key decisions from this prompt:**

1. **FakeEntsoeClient first** — real API token requested but pending. Build a
   fake client that replays saved XML fixtures so dev isn't blocked. Keep it as
   a potential fallback even after the real client works.

2. **Knowledge-time semantics** — use ENTSO-E's `createdDateTime` (publication
   timestamp) as `knowledge_time`, fall back to `datetime.utcnow()` when
   missing. Log which branch was taken per row.

3. **Bidding zone** — start with SE3 (Swedish, aligns with Rebase being a
   Swedish company). Schema is series-keyed so expanding is trivial.

4. **Day-ahead hourly first** — simpler, fully covered by ENTSO-E's Price
   Document endpoint. Intraday continuous is a stretch goal.

5. **TimeDB is viable** — README confirms first-class `knowledge_time`,
   `overlapping=True` for revision history, VERSIONED data shape. No need for
   a raw SQL fallback.

6. **Query-time `argMax`** — not materialized views. MV in ClickHouse is a
   write-time trigger, and our `as_of` parameter is a query-time input that
   can't be pre-materialized. Query-time is the only correct option.

7. **UTC everywhere** — Sweden observes DST (CET/CEST). Store everything as
   UTC, convert only at API/display boundary.

8. **Unit tests + light integration** — fast unit tests on query logic, small
   integration suite against dockerized Postgres + ClickHouse.

9. **Retention: `short`** — 6-month TTL in ClickHouse. Plenty for a portfolio
   demo.

10. **Transient ingest failures are OK** — WARN and skip cycle. ENTSO-E
    accumulates revisions server-side; next fetch picks them up. Never skip
    *revisions* though — that's the whole point.

---

## Prompt 2 — Data Model Review

**Date:** 10 April 2026
**Tool:** Claude Code

**Prompt:** Reviewed TimeDB source (models.py, SQL schemas, TimeDataModel) to
determine exact Postgres and ClickHouse schemas. Proposed data model for user
review.

**What I wanted to achieve:** Nail down the data model on paper before writing
any code, so every design choice is defensible in an interview.

**Key decisions from this prompt:**

1. **We don't write raw SQL** — TimeDB manages schema creation via `td.create()`
   and `td.create_series()`. We understand the underlying tables but don't
   create them ourselves.

2. **Postgres is the dimension table** — series metadata only (name, unit,
   labels, overlapping flag). No price values.

3. **ClickHouse is the fact table** — `overlapping_short` table with sort key
   `(series_id, valid_time, knowledge_time, change_time)`. Sort key matches
   the as-of query access pattern.

4. **VERSIONED shape** — `knowledge_time` + `valid_time` + `value`. TimeDB's
   insert pipeline accepts this natively.

5. **Labels as JSONB** — `{"zone": "SE3", "resolution": "PT1H"}`. Flexible
   dimensions, no schema migration to add zones later.

6. **Error taxonomy documented** — clear rules for WARN-and-skip vs ERROR-and-halt.

7. **ARCHITECTURE.md created** — living design doc with full data model,
   as-of query, error taxonomy, and infrastructure overview.

8. **Future plans noted** — user wants to add frontend and gRPC integration.
   To be discussed before implementation begins.

---

## Prompt 3 — Phase 2 Architecture + Docker Compose

**Date:** 12 April 2026
**Tool:** Claude Code

**Prompt:** User approved Phase 1 architecture. Added dual-interface
architecture (gRPC + FastAPI gateway), folder structure for all phases, and
implemented Docker Compose as first Phase 1 deliverable.

**What I wanted to achieve:** Get Postgres + ClickHouse running locally before
touching any Python. Also ensure fresh clones can rebuild gRPC generated code.

**Key decisions from this prompt:**

1. **Docker Compose implemented** — Postgres 16 + ClickHouse 24.8, named
   volumes, health checks, shared network (`gridlog-net`), env var defaults
   so `docker compose up` works without `.env`.

2. **ClickHouse passwordless for local dev** — `users.xml` override sets empty
   password for `default` user with `access_management=1` (needed for
   `td.create()` to create tables).

3. **ClickHouse init script** — single `CREATE DATABASE IF NOT EXISTS gridlog`
   in `docker-entrypoint-initdb.d/`. TimeDB creates tables, we create the DB.

4. **`scripts/gen_proto.sh`** — one-command protobuf regeneration. Resolves
   repo root from script location, creates `__init__.py` in generated dir.
   Anyone cloning the repo can rebuild generated code.

5. **`gridlog/grpc_service/generated/` gitignored** — standard practice,
   rebuilt via `gen_proto.sh`.

6. **Dual-interface architecture documented** — gRPC is the real service
   (Phase 2), FastAPI narrows to thin HTTP→gRPC gateway. Both expose
   `GetLatestPrices` + `GetPricesAsOf`. ASCII request-flow diagram in
   ARCHITECTURE.md.

7. **Folder structure locked for all phases** — `proto/`, `grpc_service/`,
   `frontend/`, `fixtures/` all reserved now to avoid restructuring later.
   `query/` is the shared heart — pure logic, no framework deps.

---

## Prompt 4 — TimeDB Reality Check

**Date:** 13 April 2026
**Tool:** Claude Code

**Prompt:** First end-to-end test of `scripts/init_db.py` against the running
docker stack. `td.create()` raised `TypeError: unexpected keyword argument
'pg_connection_string'`. Paused to read the actual TimeDB source instead of
patching blindly.

**What I wanted to achieve:** Find out what TimeDB actually does, not what I
assumed it did, before writing any more code on top of a wrong mental model.

**What I found (by reading `.venv/lib/python3.13/site-packages/timedb/`):**

1. **TimeDB is a TimescaleDB wrapper, not a Postgres+ClickHouse wrapper.**
   `timedb/db/create.py` reads `sql/pg_create_table_timescaledb.sql` and runs
   it against a single Postgres connection. First SQL line:
   `CREATE EXTENSION IF NOT EXISTS timescaledb;`. Zero references to
   ClickHouse in the entire package.

2. **`TimeDataClient` takes one `conninfo` string**, resolved from
   `TIMEDB_DSN` or `DATABASE_URL` env var. There are no separate Postgres and
   ClickHouse arguments because there is no ClickHouse.

3. **`overlapping_short/medium/long` are TimescaleDB hypertables** partitioned
   on `valid_time`, not ClickHouse MergeTree tables. A view
   `all_overlapping_raw` unions them for reads.

4. **The as-of query is `DISTINCT ON (valid_time) ... ORDER BY valid_time,
   knowledge_time DESC`** — pure PostgreSQL, no `argMax`. TimeDB exposes it as
   `read_overlapping_latest(series_id, end_known=as_of)`. Passing `end_known`
   turns the same function into either "latest" or "as-of" — elegant.

5. **`td.get_series('da_price')` returns a lazy `SeriesCollection`** even for
   missing series — so our try/except idempotency pattern was broken (first
   run "succeeded" silently with zero rows inserted). The correct idempotency
   hook is `create_series()` itself, which raises `ValueError` on the
   `(name, labels)` unique constraint. Confirmed by running `init_db.py`
   twice and verifying a single row in `series_table`.

**Key corrections:**

1. **Stack collapsed to one service.** `docker-compose.yml` now runs only
   `timescale/timescaledb:latest-pg16`. Dropped `clickhouse` service,
   `docker/clickhouse/` config dir, `chdata` volume. Also wiped the old
   `pgdata` volume so the new image initializes cleanly with the TimescaleDB
   extension.

2. **Config simplified.** `gridlog/config.py` dropped all `CLICKHOUSE_*`
   settings. Added a `timedb_dsn` property and a one-liner
   `os.environ.setdefault("TIMEDB_DSN", settings.timedb_dsn)` at import
   time — so any module that imports `gridlog.config` gets a ready-to-use
   TimeDB client without having to pass connection args.

3. **`gridlog/store/series.py` rewritten.** `init_store()` is now
   `td.create(retention_short="6 months")` — no kwargs for connection.
   `ensure_series()` catches `ValueError` on `create_series()` for
   idempotency.

4. **ARCHITECTURE.md rewritten.** Stack table, data model, as-of query SQL,
   infrastructure, and folder structure all now reflect the TimescaleDB
   reality. Prior entries in PROMPTS.md (Prompts 1–3) are left untouched —
   they are the honest record of what I believed at each point. This prompt
   is the correction.

**Why this is actually a better outcome:**

- TimescaleDB *is* part of Rebase's stack via TimeDB itself, so the
  "mirrors Rebase's real tooling" interview angle is fully intact.
- Simpler ops: one service, one DSN, one SQL dialect.
- Defensible story: "I assumed Postgres+ClickHouse from the project name,
  then read the TimeDB source during the first test run, found my assumption
  was wrong, and corrected the design in a single commit pair." That's a
  stronger interview signal than any answer where everything worked on the
  first try.

**Lesson saved for next time:** Before committing to an architecture decision
based on *how I think a third-party library works*, run a 30-second
introspection pass (`inspect.signature`, `grep`, read the SQL files). Would
have caught this on day one.

---
