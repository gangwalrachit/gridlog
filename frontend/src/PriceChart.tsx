import { useEffect, useRef, useState } from "react";
import * as Plot from "@observablehq/plot";
import type { PriceRow, RevisionRow } from "./api";

type SingleProps    = { mode: "single";    data: PriceRow[] };
type RevisionsProps = { mode: "revisions"; data: RevisionRow[] };
export type ChartProps = SingleProps | RevisionsProps;

const ACCENT  = "#00d992";
const MUTED   = "#8b949e";
const SURFACE = "#101010";
const GRID    = "#3d3a39";

const MONO = "'SFMono-Regular','SF Mono',Menlo,monospace";
const MONTHS_SHORT = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

// Alpha range for revision snapshots: oldest is dim but visible, latest is full.
export const ALPHA_MIN = 0.25;
export const ALPHA_MAX = 0.93;

function xTickFmt(d: Date): string {
  // Show "Mon D" at UTC midnight (day boundary), "HH:MM" otherwise.
  if (d.getUTCHours() === 0 && d.getUTCMinutes() === 0) {
    return `${MONTHS_SHORT[d.getUTCMonth()]} ${d.getUTCDate()}`;
  }
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}

function basePlotOpts(width: number, height: number) {
  return {
    width,
    height,
    marginLeft:   62,
    marginBottom: 44,
    marginTop:    20,
    marginRight:  20,
    style: `background:transparent;color:${MUTED};font-family:${MONO};font-size:11px;--plot-background:${SURFACE}`,
    x: {
      type:        "time" as const,
      label:       null,
      tickFormat:  xTickFmt,
      ticks:       8,
      tickSize:    0,
      tickPadding: 10,
    },
    y: {
      label:       "EUR / MWh",
      grid:        true,
      nice:        true,
      tickSize:    0,
      tickPadding: 8,
    },
  };
}

function injectGradient(plot: Element) {
  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  defs.innerHTML = `
    <linearGradient id="area-grad" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0%"   stop-color="${ACCENT}" stop-opacity="0.22"/>
      <stop offset="100%" stop-color="${ACCENT}" stop-opacity="0.01"/>
    </linearGradient>
  `;
  // plot is the SVGSVGElement — prepend so url(#area-grad) resolves
  plot.prepend(defs);
}

function buildSingle(data: PriceRow[], width: number, height: number): Element {
  const pts = data.map(d => ({ t: new Date(d.valid_time), v: d.value }));

  const plot = Plot.plot({
    ...basePlotOpts(width, height),
    marks: [
      Plot.areaY(pts, {
        x: "t", y: "v",
        fill: "url(#area-grad)",
        curve: "step",
      }),
      Plot.lineY(pts, {
        x: "t", y: "v",
        stroke: ACCENT,
        strokeWidth: 2,
        curve: "step",
      }),
      Plot.dot(pts, {
        x: "t", y: "v",
        r: 2.5,
        fill: ACCENT,
      }),
      Plot.tip(pts, Plot.pointerX({
        x: "t", y: "v",
        title: (d: { t: Date; v: number }) =>
          `${d.t.toISOString().slice(0, 16).replace("T", "  ")} UTC\n${d.v.toFixed(2)} EUR/MWh`,
      })),
    ],
  });

  injectGradient(plot);
  return plot;
}

function buildRevisions(data: RevisionRow[], width: number, height: number): Element {
  const kts = [...new Set(data.map(d => d.knowledge_time))].sort();
  const n   = kts.length;

  const parsed = data.map(d => ({
    t:  new Date(d.valid_time),
    kt: d.knowledge_time,
    v:  d.value,
  }));

  // One step-line per knowledge_time. Oldest = dim but visible, newest = full emerald.
  const lineMarks = kts.map((kt, i) => {
    const rows  = parsed.filter(d => d.kt === kt);
    const frac  = n === 1 ? 1 : i / (n - 1);
    const alpha = (ALPHA_MIN + (ALPHA_MAX - ALPHA_MIN) * frac).toFixed(2);

    return Plot.lineY(rows, {
      x: "t", y: "v",
      stroke:      `rgba(0,217,146,${alpha})`,
      strokeWidth: i === n - 1 ? 2.5 : 1,
      curve: "step",
    });
  });

  const latestRows = parsed.filter(d => d.kt === kts[n - 1]);

  const dotMark = Plot.dot(latestRows, {
    x: "t", y: "v",
    r: 2, fill: ACCENT,
  });

  const tipMark = Plot.tip(latestRows, Plot.pointerX({
    x: "t", y: "v",
    title: (d: { t: Date; kt: string; v: number }) =>
      `${d.t.toISOString().slice(0, 16).replace("T", "  ")} UTC\n${d.v.toFixed(2)} EUR/MWh`,
  }));

  return Plot.plot({
    ...basePlotOpts(width, height),
    marks: [...lineMarks, dotMark, tipMark],
  });
}

export function PriceChart(props: ChartProps) {
  const ref  = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ width: 640, height: 380 });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0)
        setDims({ width: Math.floor(width), height: Math.floor(height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const plot =
      props.mode === "single"
        ? buildSingle(props.data, dims.width, dims.height)
        : buildRevisions(props.data, dims.width, dims.height);

    el.innerHTML = "";
    el.appendChild(plot);
    return () => { try { el.removeChild(plot); } catch { /* already removed */ } };
  }, [props, dims]);

  return (
    <div
      ref={ref}
      className="chart-canvas"
      style={{ "--grid-color": GRID } as React.CSSProperties}
    />
  );
}
