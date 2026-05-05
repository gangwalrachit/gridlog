export type PriceRow = {
  valid_time: string;
  value: number;
};

export type RevisionRow = {
  valid_time: string;
  knowledge_time: string;
  value: number;
};

const API_BASE = "http://127.0.0.1:8000";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}: ${await r.text()}`);
  return r.json() as Promise<T>;
}

function qs(params: Record<string, string>): string {
  return "?" + new URLSearchParams(params).toString();
}

export function fetchLatest(zone: string, start: string, end: string): Promise<PriceRow[]> {
  return get<PriceRow[]>("/prices/latest" + qs({ zone, start, end }));
}

export function fetchAsOf(
  zone: string,
  start: string,
  end: string,
  as_of: string,
): Promise<PriceRow[]> {
  return get<PriceRow[]>("/prices/as-of" + qs({ zone, start, end, as_of }));
}

export function fetchRevisions(zone: string, start: string, end: string): Promise<RevisionRow[]> {
  return get<RevisionRow[]>("/prices/revisions" + qs({ zone, start, end }));
}
