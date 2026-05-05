import { useMemo, useState } from "react";
import { fetchLatest, fetchAsOf, fetchRevisions } from "./api";
import type { PriceRow, RevisionRow } from "./api";
import { PriceChart, ALPHA_MIN, ALPHA_MAX } from "./PriceChart";

const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function fmtKt(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

type Endpoint = "latest" | "as-of" | "revisions";
type QueryResult =
  | { type: "latest" | "as-of"; data: PriceRow[] }
  | { type: "revisions"; data: RevisionRow[] };

const ENDPOINTS: { id: Endpoint; label: string; hint: string }[] = [
  { id: "latest",    label: "Latest",    hint: "Most recent price per delivery slot" },
  { id: "as-of",     label: "As Of",     hint: "Prices known at a specific cutoff time" },
  { id: "revisions", label: "Revisions", hint: "All historical snapshots — the time-of-knowledge view" },
];

function defaultDates() {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  const fmt = (d: Date) =>
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}Z`;

  // SE3 delivery days run 22:00 UTC→22:00 UTC (CET midnight→midnight).
  // Nord Pool auction clears ~13:00 CET: after that, tomorrow's prices are live;
  // before that, today's prices (yesterday's auction) are the freshest available.
  const month = now.getUTCMonth() + 1;
  const cetOffset = month >= 4 && month <= 10 ? 2 : 1; // CEST vs CET
  const cetHour = (now.getUTCHours() + cetOffset) % 24;

  const startUtc = new Date(now);
  startUtc.setUTCHours(22, 0, 0, 0);
  if (cetHour >= 13) {
    if (now.getUTCHours() >= 22) startUtc.setUTCDate(startUtc.getUTCDate() + 1);
  } else {
    if (now.getUTCHours() < 22) startUtc.setUTCDate(startUtc.getUTCDate() - 1);
  }
  const endUtc = new Date(startUtc.getTime() + 24 * 60 * 60 * 1000);

  return {
    start: fmt(startUtc),
    end:   fmt(endUtc),
    asOf:  fmt(now),
  };
}

export default function App() {
  const defaults = useMemo(defaultDates, []);

  const [endpoint, setEndpoint] = useState<Endpoint>("revisions");
  const [zone,     setZone]     = useState("SE3");
  const [start,    setStart]    = useState(defaults.start);
  const [end,      setEnd]      = useState(defaults.end);
  const [asOf,     setAsOf]     = useState(defaults.asOf);
  const [result,   setResult]   = useState<QueryResult | null>(null);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);

  function switchEndpoint(ep: Endpoint) {
    setEndpoint(ep);
    setResult(null);
    setError(null);
  }

  async function handleGet() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      if (endpoint === "latest") {
        const data = await fetchLatest(zone, start, end);
        setResult({ type: "latest", data });
      } else if (endpoint === "as-of") {
        const data = await fetchAsOf(zone, start, end, asOf);
        setResult({ type: "as-of", data });
      } else {
        const data = await fetchRevisions(zone, start, end);
        setResult({ type: "revisions", data });
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  const revisionChips = useMemo(() => {
    if (!result || result.type !== "revisions") return null;
    const kts = [...new Set(result.data.map(r => r.knowledge_time))].sort();
    const n = kts.length;
    return kts.map((kt, i) => ({
      kt,
      alpha: n === 1 ? ALPHA_MAX : ALPHA_MIN + (ALPHA_MAX - ALPHA_MIN) * (i / (n - 1)),
      isLatest: i === n - 1,
      label: fmtKt(kt),
    }));
  }, [result]);

  function chartSummary() {
    if (!result) return "";
    const base = `${zone} · ${result.data.length} row${result.data.length !== 1 ? "s" : ""}`;
    if (result.type !== "revisions") return base;
    const kts = new Set(result.data.map(r => r.knowledge_time));
    return `${base} · ${kts.size} snapshot${kts.size !== 1 ? "s" : ""}`;
  }

  const isAsOf = endpoint === "as-of";

  return (
    <div className="layout">
      {/* ── Header ── */}
      <header className="top-bar">
        <div className="brand">
          <span className="brand-dot" aria-hidden="true">●</span>
          <span className="wordmark">GridLog</span>
        </div>
        <span className="tagline">time-of-knowledge price explorer</span>
      </header>

      {/* ── Query panel ── */}
      <div className="query-card">
        <div className="tabs" role="tablist">
          {ENDPOINTS.map(({ id, label, hint }) => (
            <button
              key={id}
              role="tab"
              aria-selected={endpoint === id}
              className={`tab-btn${endpoint === id ? " tab-btn--active" : ""}`}
              onClick={() => switchEndpoint(id)}
              title={hint}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="controls-row">
          <div className="field field--zone">
            <label className="field-label" htmlFor="inp-zone">Zone</label>
            <input
              id="inp-zone"
              className="field-input"
              value={zone}
              onChange={e => setZone(e.target.value.toUpperCase())}
              placeholder="SE3"
              spellCheck={false}
            />
          </div>

          <div className="field field--date">
            <label className="field-label" htmlFor="inp-start">Start</label>
            <input
              id="inp-start"
              className="field-input"
              value={start}
              onChange={e => setStart(e.target.value)}
              placeholder="YYYY-MM-DDTHH:MMZ"
              spellCheck={false}
            />
          </div>

          <div className="field field--date">
            <label className="field-label" htmlFor="inp-end">End</label>
            <input
              id="inp-end"
              className="field-input"
              value={end}
              onChange={e => setEnd(e.target.value)}
              placeholder="YYYY-MM-DDTHH:MMZ"
              spellCheck={false}
            />
          </div>

          {/* as-of greyed out unless "As Of" tab is active */}
          <div className={`field field--date${!isAsOf ? " field--inactive" : ""}`}>
            <label className="field-label" htmlFor="inp-asof">As Of</label>
            <input
              id="inp-asof"
              className="field-input"
              value={asOf}
              onChange={e => setAsOf(e.target.value)}
              placeholder="YYYY-MM-DDTHH:MMZ"
              disabled={!isAsOf}
              spellCheck={false}
            />
          </div>

          <button
            className={`get-btn${loading ? " get-btn--busy" : ""}`}
            onClick={handleGet}
            disabled={loading}
          >
            {loading ? "···" : "GET"}
          </button>
        </div>
      </div>

      {/* ── Chart area ── */}
      <div className="chart-area">
        {error ? (
          <div className="chart-state">
            <p className="state-error-msg">{error}</p>
          </div>

        ) : !result ? (
          <div className="chart-state">
            <div className="empty-icon" aria-hidden="true">◈</div>
            <p className="empty-headline">No data yet</p>
            <p className="empty-sub">Select an endpoint above and press GET</p>
          </div>

        ) : result.data.length === 0 ? (
          <div className="chart-state">
            <div className="empty-icon" aria-hidden="true">◈</div>
            <p className="empty-headline">Empty response</p>
            <p className="empty-sub">
              No data for this window. Try a wider range or run the ingest script first.
            </p>
          </div>

        ) : (
          <div className="chart-inner">
            <div className="chart-header">
              <div className="chart-header-left">
                <span className="endpoint-badge">{result.type}</span>
                <span className="chart-summary">{chartSummary()}</span>
              </div>
            </div>

            {revisionChips && (
              <div className="revision-legend-row">
                {revisionChips.map(({ kt, alpha, isLatest, label }) => (
                  <div key={kt} className={`legend-chip${isLatest ? " legend-chip--latest" : ""}`}>
                    <span
                      className="legend-swatch"
                      style={{ background: `rgba(0,217,146,${alpha.toFixed(2)})` }}
                    />
                    <span className="legend-kt">{label}</span>
                    {isLatest && <span className="legend-badge">latest</span>}
                  </div>
                ))}
              </div>
            )}

            {result.type === "revisions" ? (
              <PriceChart mode="revisions" data={result.data} />
            ) : (
              <PriceChart mode="single" data={result.data} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
