declare global {
	interface Window { __API_URL__?: string; }
}

const BASE = (typeof window !== 'undefined' && window.__API_URL__)
	? window.__API_URL__
	: (import.meta.env.DEV ? 'http://localhost:8000' : '');

async function get<T>(path: string): Promise<T> {
	const res = await fetch(`${BASE}${path}`);
	if (!res.ok) throw new Error(`API error: ${res.status}`);
	return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
	const res = await fetch(`${BASE}${path}`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(body)
	});
	if (!res.ok) throw new Error(`API error: ${res.status}`);
	return res.json();
}

export const api = {
	status: () => get<any>('/api/status'),
	ticker: (pair: string) => get<any>(`/api/ticker/${pair}`),
	ohlc: (pair: string) => get<any>(`/api/ohlc/${pair}`),
	paperBalance: () => get<any>('/api/paper/balance'),
	paperPositions: () => get<any>('/api/paper/positions'),
	paperHistory: () => get<any>('/api/paper/history'),
	runAgent: (message: string) => post<any>('/api/agent/run', { message }),
	runPipeline: (query: string) => post<any>('/api/pipeline/run', { query }),
	getHistory: (opts?: { limit?: number; from_ts?: number; to_ts?: number }) => {
		const p = new URLSearchParams();
		const limit = opts?.limit ?? 200;
		p.set('limit', String(limit));
		if (opts?.from_ts != null) p.set('from_ts', String(opts.from_ts));
		if (opts?.to_ts != null) p.set('to_ts', String(opts.to_ts));
		return get<any>(`/api/history?${p}`);
	},
	getHistoryRun: (id: string) => get<any>(`/api/history/${id}`),
	portfolio: () => get<any>('/api/metrics/portfolio'),
	performance: () => get<any>('/api/metrics/performance'),
	onchain: () => get<any>('/api/metrics/onchain'),
};
