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
