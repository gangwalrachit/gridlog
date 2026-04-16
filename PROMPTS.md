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

## Prompt 7 — `EntsoeClient` Implementation + Live Smoke Test

**Date:** 14 April 2026
**Tool:** Claude Code

**Prompt:** Implement `gridlog/entsoe/client.py` per Prompt 6, smoke-test
against the live ENTSO-E API for SE3 day-ahead, and commit.

**What I wanted to achieve:** First byte-of-real-data moment — prove the
client actually reaches ENTSO-E and comes back with a usable XML document
before writing the parser on top of it.

**Key decisions from this prompt:**

1. **Defensive UTC normalization at the API boundary.** `_require_utc()`
   raises on naive datetimes and coerces tz-aware to UTC before formatting
   the `periodStart` / `periodEnd` params. ENTSO-E docs say the API takes
   UTC, but "we trust it's UTC" is the kind of assumption that breaks on
   DST transitions. Verified against the published ENTSO-E API guide — both
   request params and response timestamps are UTC. The helper means a
   caller can never accidentally send a local-time window.

2. **Retry strategy deferred.** Skipping backoff / retry for now — Prompt 1
   already decided transient failures are WARN-and-skip (ENTSO-E
   accumulates revisions server-side, next cycle picks them up). Revisit
   only if a stress test shows meaningful loss. Added to the running
   "things to decide later" list.

3. **`base_url` dropped from `httpx.Client` after a 404 on the first live
   call.** Root cause: `httpx.Client(base_url="…/api").get("")` joins to
   `…/api/` with a trailing slash, and ENTSO-E 404s on `/api/` (it only
   answers on `/api`). Fix is to construct the client without `base_url`
   and pass the full URL to `.get()`. One-line comment in the source
   explains *why* the base_url was intentionally removed, so a future
   refactor doesn't silently re-introduce the bug.

4. **Smoke test window.** Picked a closed historical day
   (`2026-04-12 22:00 UTC → 2026-04-13 22:00 UTC`, SE3's April 13 delivery
   day in local time) rather than tomorrow's publication window — avoids
   flakiness around the ~12:45 CET day-ahead publication cutoff. Returned
   14,829 bytes of valid XML with `<TimeSeries>` and `<Point>` elements —
   exactly what the parser will consume next.

**Deferred to later prompts:**
- Retry / backoff strategy — revisit after a stress test shapes the real
  failure modes.
- Multi-zone support — the client already accepts `zone_eic` as a
  parameter; `SE3_EIC` stays as a convenience constant until a second zone
  actually lands.

---

## Prompt 8 — Fixture Capture Surfaces Two Stale Assumptions

**Date:** 14 April 2026
**Tool:** Claude Code

**Prompt:** Capture one live SE3 day-ahead fixture to `fixtures/` to drive
parser unit tests.

**What I wanted to achieve:** A real byte payload on disk so the parser can
be written and tested without the network.

**What the fixture revealed (before a single line of parser was written):**

1. **SE3 day-ahead is now `PT15M`, not `PT1H`.** The document carries 96
   `<Point>` elements under `<resolution>PT15M</resolution>` — one price
   per 15 minutes, 96 prices per delivery day. This is the EU Market Time
   Unit (MTU) reform that landed on 2025-10-01 for most day-ahead markets:
   auctions now clear in 15-minute slots so flexibility assets (batteries,
   demand response) can arbitrage intra-hour renewable swings that an
   hourly block hid. Prompt 1's assumption that day-ahead means "24 rows
   per day" was true in 2024, no longer true in 2026.

2. **`<createdDateTime>` is API-response time, not auction-publication
   time.** The fixture's `createdDateTime` = `2026-04-14T17:22:07Z` — but
   the delivery day is 2026-04-13, and the real SE3 day-ahead auction
   cleared around 2026-04-12 12:45 CET. ENTSO-E re-stamps the document
   when the API generates it for a response, which means the field tells
   you "when was this XML minted for me" not "when did the market first
   know this price." Prompt 1 decision #2 (use `<createdDateTime>` as
   `knowledge_time`) is therefore semantically off.

**Key decisions from this prompt:**

1. **Series label updated to `PT15M`.** `gridlog/store/series.py`:
   `labels={"zone": "SE3", "resolution": "PT15M"}`. One-line change —
   TimeDB's VERSIONED shape is resolution-agnostic, the label is purely
   metadata on the series row. Row volume goes from 24/day to 96/day,
   nothing else moves.

2. **Stale `PT1H` series row wiped.** `(name, labels)` is TimeDB's
   uniqueness key, so simply re-running `init_db.py` would leave the old
   `PT1H` row in place and create a second `PT15M` row — the ingest
   pipeline wouldn't know which to target. Dev DB has zero price data so
   the safe move is `docker compose down -v && up -d && init_db.py`.

3. **`knowledge_time = datetime.now(UTC)` at fetch time,** not
   `<createdDateTime>`. Prompt 1 decision #2 is superseded. Rationale:
   ENTSO-E doesn't expose the original auction-publication time via the
   public API — `<createdDateTime>` is just the document-generation time.
   Using fetch time is honest about what we actually know: "GridLog
   learned this price at T." It also gives a cleaner revision story in the
   demo — every re-fetch produces a new `knowledge_time` for the same
   `valid_time`, which is exactly the time-of-knowledge story we want to
   show. The `<createdDateTime>` field is still parsed and captured in
   batch metadata for audit purposes, but doesn't drive storage.

4. **Window signature paid off.** Prompt 6 decision #3 chose
   `(start, end)` over `(day: date)` with the explicit prediction "stays
   stable when we eventually add intraday 15-min resolution." That
   prediction cashed in the first time we saw a real document — zero
   changes to `fetch_day_ahead()` needed for PT15M. A `(day: date)`
   signature would have meant a breaking API change right here.

**Why this is a better outcome:**

- Honest semantics. "Knowledge time = when GridLog learned it" is
  defensible; "knowledge time = when the market published it" was always
  going to be a white lie given what ENTSO-E exposes.
- Richer demo. 96 rows/day vs 24 rows/day gives the as-of-query viz 4×
  more points to plot, which makes the time-of-knowledge animation
  noticeably smoother.
- One more datapoint for the "read the real data before committing to a
  mental model" lesson from Prompt 4. Capture-first would have caught the
  PT15M and `createdDateTime` assumptions on day one.

---

## Prompt 9 — A03 Curves Compress Consecutive Equal Prices

**Date:** 15 April 2026
**Tool:** Claude Code

**Prompt:** Round-trip smoke test of `client → parser` against a second live
SE3 day-ahead fetch, to close out the `entsoe/` module before moving to
ingest.

**What I wanted to achieve:** Final confidence that the client and parser
compose cleanly on real data — not just on the single captured fixture —
before declaring the module done.

**What broke on the first live fetch:**

The parser raised `non-contiguous Point positions: [1, 2, 3, 4, 5]` on a
perfectly valid ENTSO-E document. The `<TimeSeries>` carried 95 `<Point>`
elements with positions `1..28, 30..96` — position 29 was missing, and
positions 28 and 30 had **different** prices (95.0 and 98.22). The
yesterday fixture had all 96 positions intact and worked fine.

**Root cause — A03 curveType is run-length compressed:**

ENTSO-E's A03 "sequential fixed size block" curve type has a compression
rule I missed on first read: *when consecutive slots share the same price,
only the first slot emits an explicit `<Point>`; the rest are omitted and
inherit the most recent explicit value by forward-fill.* In yesterday's
fixture, every consecutive pair of prices happened to differ, so all 96
Points were emitted and my wrong "positions must be 1..N" invariant
silently held. In today's fetch, position 28 and 29 both had price 95.0,
so ENTSO-E dropped position 29 from the document. This is standard
compression for A03, documented in the ENTSO-E Implementation Guide —
discovered on the first compressed document we fetched.

My explanation of A03 in Prompt 6 / Prompt 8 ("positions are 1..N with no
holes, a gap is a data error") was wrong. Corrected semantic: *missing
positions are not errors; they are duplicates of the last explicit value.*

**Key decisions from this prompt:**

1. **Parser rewritten to forward-fill.** Computes expected slot count
   `slots = (period.end - period.start) / resolution`, walks `1..slots`,
   carries the last explicit price forward whenever a position is missing.
   Output DataFrame always has `slots` rows regardless of how many
   explicit `<Point>` elements the source document carried.

2. **Fail-loud invariants preserved, just on the right things now.**
   - Position 1 missing → `ValueError` (nothing to forward-fill from).
   - `max(position) > slots` → `ValueError` (malformed document, points
     off the end of the declared Period).
   - Unknown resolution → `ValueError` (as before).

3. **Second fixture captured.** `fixtures/se3_da_2026-04-14.xml` is the
   today-fetch document with the missing position 29. Kept as a
   regression fixture for the compression path — the yesterday fixture
   exercises the "all positions present" path, the today fixture
   exercises the "forward-fill" path. Both paths now have a real-world
   test.

4. **Unit test added** (`test_a03_compression_forward_fills_missing_positions`).
   Asserts: 96 output rows from 95 input points, index 28 (position 29)
   equals index 27 (position 28) at 95.0, index 29 (position 30) resumes
   with its own value 98.22, cadence still 15 minutes end-to-end.

5. **Round-trip retry after fix:** 96 rows, single `knowledge_time`,
   monotonic 15-minute cadence, prices match the raw XML spot-checks.
   `entsoe/` module is now done.

**Why this is a better outcome:**

- The round-trip smoke test caught a real correctness bug that the unit
  tests on the first fixture could not have caught — the first fixture
  had no consecutive-equal-price runs, so it exercised zero compression.
  One fixture was not enough; two are the minimum.
- The fix is structural (always emit `slots` rows) rather than
  opportunistic (patch this one case), which means any future compression
  pattern — runs of length 3, 4, or longer — works without further
  changes. There's no `len(positions) == slots - 1` special case.
- Honest mental model correction logged in the decision log. Prompt 6 and
  Prompt 8 said A03 is contiguous; Prompt 9 says A03 is contiguous-or-
  compressed. Future-me reading this log doesn't have to re-discover it.

**Lesson saved for next time:** One fixture is a smoke test, not a test
suite. Before declaring an XML/JSON parser "done" on fixture data, capture
at least two documents from the same source and diff them — any
discrepancy is either compression, optional fields, or a schema version
bump, and all three are things the parser needs to handle.

---

## Prompt 10 — Ingest Pipeline: Time-of-Knowledge Becomes Observable

**Date:** 16 April 2026
**Tool:** Claude Code

**Prompt:** Wire `client → parser → TimeDB.insert` into a single
`fetch_and_store()` entry point. First real write to TimeDB on real
ENTSO-E data.

**What I wanted to achieve:** Turn the two sides of the system — the
HTTP/parser side and the storage side — into one orchestrated call that
materialises the time-of-knowledge story on disk. Up to this prompt,
nothing had ever been written to TimeDB with a real `knowledge_time`.

**Key decisions from this prompt:**

1. **Error taxonomy split: WARN-and-skip vs. raise.** Transient fetch
   failures (`httpx.HTTPError`) log at WARNING and return `None` — the
   next scheduled run will pick up the revision anyway, and ENTSO-E
   accumulates its own publication history server-side. Parse failures
   and insert failures raise loudly — if the document shape drifts or
   TimeDB rejects a batch, silently skipping would erode the audit story
   (Prompt 1 decision #10: "never skip revisions"). The rule of thumb:
   *network hiccups are expected and recoverable; schema drift and
   storage errors are not, and the operator needs to know now.*

2. **`knowledge_time = datetime.now(UTC)` set at fetch start, not insert
   time.** Matters when an insert is retried or delayed — the moment
   GridLog *learned* the prices is when it asked for them, not when it
   successfully flushed them. Prompt 8 decision #3 settled on fetch-time
   semantics; this prompt operationalises it by capturing `now(UTC)`
   once, up front, and threading it through to both `parse_day_ahead()`
   and `series.insert(knowledge_time=…)`.

3. **`batch_params` as JSONB audit envelope.** Every insert carries the
   source tag (`entsoe_transparency_api`), document type (`A44`), zone
   EIC, and UTC window as a dict into TimeDB's batch metadata. Costs
   nothing at write time, gives us "how did this row get here?"
   answerable by a single `SELECT batch_params FROM batches_table` query
   forever. YAGNI said "skip it"; experience said "past-me always
   regrets missing provenance." Experience won.

4. **httpx INFO logging silenced to protect the ENTSO-E token.** httpx
   logs `HTTP Request: GET …` at INFO level, which includes the full
   query string — and ENTSO-E auth is via a `securityToken` query
   parameter, not a header. One line in `run_ingest.py`:
   `logging.getLogger("httpx").setLevel(logging.WARNING)`. Without it,
   the token leaks to stdout on every run and into any log aggregator
   that collects it. Noticed during the first end-to-end dry run — the
   token showed up in the terminal transcript. Fixed before the first
   real insert.

5. **`SERIES_NAME` hoisted to `store/series.py` as a module constant.**
   Ingest and query both need the series name string; defining it once
   in the module that owns series initialisation keeps `store → ingest
   → query` as a clean dependency chain with no string duplication.

**Milestone:** After this prompt, three real SE3 batches exist in
`overlapping_short` with distinct `knowledge_time`s. For the first time
in the project, "what did GridLog know at time T?" is an answerable
question against stored data rather than a design sketch.

**Deferred to later prompts:**
- Scheduler (cron / APScheduler) to drive `fetch_and_store` on a cadence.
  For now we invoke via `scripts/run_ingest.py` manually.
- Multi-zone fan-out — `fetch_and_store(zone_name, zone_eic, …)` is
  already parameterised; adding a second zone is a loop, not a rewrite.

---

## Prompt 11 — Query Module and Integration Testing

**Date:** 16 April 2026
**Tool:** Claude Code

**Prompt:** Wrap TimeDB's `SeriesCollection.read` behind a thin query
module with three named operations, and write integration tests that
run against a real TimeDB instance.

**What I wanted to achieve:** A query surface that makes the three
time-of-knowledge reads — latest, as-of, and full revision history —
feel first-class rather than raw `.read(...)` calls sprinkled through
demos and the future API.

**Key decisions from this prompt:**

1. **Three pure functions, no class.** `get_latest_prices`,
   `get_prices_as_of`, `get_price_revisions`. Each is a 2–4 line wrapper
   around `SeriesCollection.read` with a docstring that names the
   time-of-knowledge semantic it implements. No query builder, no
   fluent API, no repository pattern — the whole point is to make the
   three canonical reads discoverable by name and trivially testable.
   Anything more elaborate is YAGNI until a fourth read appears.

2. **Integration tests opt-in via `pytest -m integration`.** The unit
   tests run in milliseconds with no TimeDB. The integration tests need
   a running Postgres + TimescaleDB and take seconds. Splitting them
   keeps `pytest` (unit only by default) fast enough to run on every
   save while still letting `pytest -m integration` exercise the real
   storage contract in CI and before commits.

3. **Test isolation by random far-future anchor, not teardown.**
   `timedb.delete()` wipes the entire schema — too blunt a hammer for
   test cleanup. Workaround: each test-module run picks a random
   1-hour anchor in a 100-year window starting at 2100-01-01 UTC. The
   probability of two runs colliding is negligible, and production data
   is in the past so it's effectively unreachable from the test path.
   `zone="TEST1"` on the series label gives a second isolation
   dimension. Not destructive to shared state, and re-runnable locally
   without `docker compose down -v`.

4. **Module-scoped `seeded` fixture, not function-scoped.** First
   attempt used `@pytest.fixture` (function scope), which re-seeded four
   times across four tests at near-identical wall-clock times — the
   random-anchor windows still differed, but the assertion `len(df) ==
   8` failed because four seedings had landed in the module. Module
   scope: seed once, all four tests read the same batches, row counts
   match the math.

5. **Inclusive-vs-exclusive is library-level, callers shouldn't care.**
   The integration test for the "cutoff between batches" case passes a
   cutoff strictly between `kt1` and `kt2` and expects batch 1 — a test
   that would *still* pass even with TimeDB's exclusive `end_known`
   semantics. The test for `as_of=kt1` is the one that pins down
   inclusivity: at `kt1`, you should see batch 1. Prompt 12 makes this
   work inside `get_prices_as_of`.

---

## Prompt 12 — Demo Script, Cutoff Inclusivity, and a 45-second ENTSO-E Call

**Date:** 16 April 2026
**Tool:** Claude Code

**Prompt:** Build a readable command-line demo of the time-of-knowledge
story. Side quest: a live ENTSO-E call took 45.6 seconds and timed out
against our 30s default.

**What I wanted to achieve:** A script a reviewer can run in 5 seconds
and see, in plain text, that GridLog stores revisions and that as-of
queries return the right batch for a given cutoff — without needing to
read the code or the tests.

**Key decisions from this prompt:**

1. **Demo is a pure reader, not an ingest-plus-visualise script.** Two
   files: `run_ingest.py` (writes) and `demo_diff.py` (reads).
   Separation means you can run ingest in the morning, again at night,
   and then run the demo any time in between to see whatever
   accumulated naturally — no synthetic perturbations needed to
   produce a revision story. The demo script has zero side effects on
   TimeDB, which makes it safe to run against production data.

2. **Inclusive `as_of` cutoff — option B (offset inside the wrapper).**
   TimeDB's `SeriesCollection.read(end_known=T)` is strictly exclusive
   of T, so `get_prices_as_of(…, as_of=kt1)` was returning empty at
   the exact moment `kt1` itself. Two options considered:
   - **A:** document the exclusivity in the docstring and let callers
     add their own offset. Pushes the surprise onto every caller and
     every future test.
   - **B:** add `timedelta(microseconds=1)` inside
     `get_prices_as_of` and document the offset in the source comment.
     Makes the public contract what callers naturally expect — "as of T
     means at or before T" — and localises the workaround to one place.

   Chose B. The workaround is a single line with a comment; the
   alternative was a foot-gun in every consumer. Upstream contribution
   idea logged outside the repo (user's private memory) so we can PR it
   back to TimeDB once GridLog is done — the right long-term fix is to
   either flip TimeDB's default to inclusive or add an explicit
   `as_of=` parameter with inclusive semantics, but that's a TimeDB
   decision not a GridLog decision.

3. **Demo output: revision ledger + as-of comparison table with a
   `DIFF?` column.** The ledger lists each `knowledge_time` with its
   row count and number of unique values — enough to see "we have three
   snapshots, they're not identical." The as-of table then walks the
   first five `valid_time` slots and shows the price under each
   snapshot side-by-side, with `yes/no` for whether the prices across
   snapshots differ. A reviewer looking at "yes" rows immediately sees
   *which* slots got revised and by how much. Plain text, copy-pasteable
   into a README.

4. **30s → 60s default timeout in `EntsoeClient`.** One real fetch
   took 45.6 seconds. ENTSO-E's Transparency API is cold-cache sensitive
   for historical windows — our demo windows aren't today's. Bumping
   the default is the simplest fix; an exponential retry with a smaller
   timeout would be strictly better but falls under "transient failures
   are WARN-and-skip" from Prompt 1, so it's not worth the complexity
   yet. Noted for the retry-strategy revisit on the backlog.

**Why this is a better outcome:**

- The "ingest morning, ingest night, demo in between" workflow mirrors
  the real production story of a time-of-knowledge system: prices drift
  over the day, and the revision ledger should grow organically. A
  synthetic perturbation script would have been a faster demo to write
  and a worse demo to show.
- Option B on the `as_of` cutoff means every future consumer of
  `get_prices_as_of` — the FastAPI endpoint, the eventual gRPC handler,
  and any notebook a reviewer writes — gets the intuitive semantic for
  free. The one-line workaround is a cheap price for removing a
  foot-gun from every call site.
- The 60s timeout fix is the kind of change that's invisible until it
  isn't. Documenting the 45.6s observation in the commit message and
  here means future-me (or future-you) reading `timeout: float = 60.0`
  and wondering "why not 30?" gets the answer without spelunking.

**Deferred to later prompts:**
- Retry / backoff for ENTSO-E — still deferred from Prompt 7. The 60s
  bump buys headroom; it doesn't replace a real strategy.
- Upstream PR to TimeDB for the `end_known` inclusivity question —
  noted privately, to revisit once GridLog's frontend + gRPC phases are
  done.

---
