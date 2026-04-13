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

3. **Bidding zone** — start with SE3 (Swedish bidding zone, straightforward
   data availability via ENTSO-E). Schema is series-keyed so expanding is
   trivial.

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

9. **Retention: `short`** — 6-month TTL in ClickHouse. Plenty for this
   project.

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
any code, so every design choice is defensible.

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

- TimescaleDB is exactly what TimeDB is built for, so the "uses an
  idiomatic TimescaleDB stack" angle is fully intact.
- Simpler ops: one service, one DSN, one SQL dialect.
- Defensible story: "I assumed Postgres+ClickHouse from the project name,
  then read the TimeDB source during the first test run, found my assumption
  was wrong, and corrected the design in a single commit pair." That's a
  stronger story than one where everything worked on the first try.

**Lesson saved for next time:** Before committing to an architecture decision
based on *how I think a third-party library works*, run a 30-second
introspection pass (`inspect.signature`, `grep`, read the SQL files). Would
have caught this on day one.

---

## Prompt 5 — Drop FakeEntsoeClient, Keep Fixtures as Test Data

**Date:** 13 April 2026
**Tool:** Claude Code

**Prompt:** With the ENTSO-E API token live and verified, do we still need
the `FakeEntsoeClient` runtime abstraction planned in Prompt 1?

**What I wanted to achieve:** Shed an abstraction that was only a hedge
against the token never arriving, without losing the testing benefits that
saved XML fixtures give us.

**Key decisions from this prompt:**

1. **`FakeEntsoeClient` dropped.** Prompt 1 decision #1 ("FakeEntsoeClient
   first") is superseded. Rationale: the hedge has served its purpose; the
   token works; the fake was never intended to outlive the real client.
   Keeping both would invite fake/real drift (the classic "tests pass
   against the mock but prod breaks because the real API behaves
   differently" failure mode).

2. **`fixtures/` stays, role changes.** Previously planned as a dual-use
   directory (runtime-replay source for the fake client + test data).
   Now it is purely captured real ENTSO-E XML responses used by unit tests
   on `gridlog/entsoe/parser.py`. The parser is a pure function (bytes →
   DataFrame), so fixture-driven unit tests give full coverage without
   touching the network.

3. **Test strategy made explicit:**
   - **Unit tests** (`tests/unit/`) — parse fixture XML, assert on the
     resulting DataFrame. Deterministic, fast, no network.
   - **Integration tests** (`tests/integration/`) — hit the real ENTSO-E
     API with the live token. Marked `@pytest.mark.slow` (or similar) so
     they're opt-in, not part of the default run. Covers the "does the
     real API still match what we think it does" question.

4. **`gridlog/entsoe/` shape finalized:**
   - `client.py` — the only HTTP client (no `real_client.py` / `fake.py`
     split)
   - `parser.py` — pure function, bytes → DataFrame
   - No `fake.py`. No `__init__.py` re-export gymnastics.

5. **One small capture helper will live in `scripts/`** (e.g.
   `scripts/capture_fixture.py`) — run manually when we need to record a
   new fixture. Not part of the runtime package. Keeps the `gridlog/`
   package clean.

**Why this is the right call now:**

- Single code path from fetch to store. Less surface area, fewer lies
  possible in the tests.
- Real-response fixtures are a stronger testing pattern than hand-written
  mocks: the tests exercise the parser against bytes that have actually
  been on the wire, caught in the wild.
- Less code to explain and defend. The `FakeEntsoeClient` abstraction was
  always going to be a footnote; now it's a non-entity.

---

## Prompt 6 — `gridlog/entsoe/` Module Design

**Date:** 13 April 2026
**Tool:** Claude Code

**Prompt:** Flesh out the design of the `entsoe/` module before
implementation — HTTP client shape, parser contract, time-window signature,
and DataFrame output shape.

**What I wanted to achieve:** Lock the design on paper so next session is a
straight implementation pass with no open questions.

**Key decisions from this prompt:**

1. **Class `EntsoeClient`, not a module function.** Carries the `httpx.Client`
   and token across calls (cleaner lifecycle when embedded in the FastAPI
   lifespan in Phase 2), constructor-injected token keeps the method itself
   free of hidden settings reads. Single public method:
   `fetch_day_ahead(zone_eic, start, end) -> bytes`.

2. **Sync `httpx.Client`.** Async is unnecessary for a periodic ingest loop.
   Revisit only if Phase 2 actually needs concurrent fetches.

3. **Time window signature: `(start: datetime, end: datetime)`.** Maps 1:1
   to ENTSO-E's `periodStart` / `periodEnd` request params, supports multi-day
   backfills in a single call, and stays stable when we eventually add
   intraday 15-min resolution (same signature, different resolution in the
   response). A `(day: date)` signature would have forced a rewrite for
   every new use case.

4. **Constants live in the client module.** `BASE_URL`,
   `DOCUMENT_TYPE_DAY_AHEAD = "A44"`, `SE3_EIC = "10Y1001A1001A46L"`.
   API-specific, not user-configurable — no reason to pollute
   `gridlog/config.py`. When additional zones arrive, `SE3_EIC` graduates to
   a dict of EIC codes keyed by zone name, still in the client module.

5. **Parser is a pure function:** `parse_day_ahead(raw: bytes) -> pd.DataFrame`.
   Pure function means it's trivially unit-testable against saved XML, with
   no mocks, no fixtures-as-runtime nonsense.

6. **Stdlib `xml.etree.ElementTree`, not `lxml`.** ENTSO-E documents are
   well-formed and modest in size; stdlib handles them without the
   compile-heavy native dependency. Zero downside.

7. **DataFrame output is three columns: `knowledge_time`, `valid_time`,
   `value`.** Both times tz-aware UTC (`datetime64[ns, UTC]`), value as
   `float64`. This is the VERSIONED shape TimeDB expects on the insert path.
   Batch metadata stays out of the row columns — it rides along via TimeDB's
   insert kwargs (into `batches_table`), not as a payload column.

8. **One `knowledge_time` per document, shared by every row.** Taken from
   `<createdDateTime>` in the document header — this is the
   publication-time semantics we want. Fallback to `datetime.now(UTC)` if
   missing, logged INFO per the error taxonomy in ARCHITECTURE.md.

9. **Empty document → empty DataFrame** (same 3 columns, zero rows). Ingest
   pipeline logs WARN and moves on. No exception — an empty auction result
   is a valid operational state, not an error.

10. **YAGNI on fixtures.** Capture one real ENTSO-E response for SE3
    day-ahead and write parser unit tests against it. Edge-case fixtures
    (DST boundary, empty day, multi-TimeSeries doc) only when we hit a real
    bug that needs them.

**Deferred to the implementation session:**
- Exact TimeDB insert call shape — will verify against `SeriesCollection.insert()`
  when wiring `ingest/`
- Whether the ingest pipeline passes `batch_params` through to TimeDB for the
  audit trail in `batches_table`
- Location of the fixture capture helper — likely `scripts/capture_fixture.py`,
  single-shot, not part of the runtime package

**Implementation order for next session:**
1. `gridlog/entsoe/client.py` — `EntsoeClient` class
2. `gridlog/entsoe/parser.py` — `parse_day_ahead` function
3. `gridlog/entsoe/__init__.py` — re-exports
4. `scripts/capture_fixture.py` — one-shot helper, run manually
5. Capture one SE3 day-ahead fixture → `fixtures/se3_da_<date>.xml`
6. `tests/unit/test_parser.py` — fixture-driven unit tests
7. Round-trip smoke: client → parser → print DataFrame head against live API

---
