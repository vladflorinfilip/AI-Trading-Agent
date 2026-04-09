export function stageIcon(name: string): string {
	if (name.includes('Analyst')) return '📊';
	if (name.includes('Trader')) return '💹';
	if (name.includes('Risk')) return '🛡️';
	return '🤖';
}

export function decisionColor(d: string): string {
	if (d === 'BUY') return '#10b981';
	if (d === 'SELL') return '#ef4444';
	if (d === 'MULTI') return '#8b5cf6';
	return '#64748b';
}

export function formatTime(iso: string): string {
	return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function formatTimestamp(ts: number): string {
	return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function formatDate(ts: number): string {
	return new Date(ts * 1000).toLocaleDateString([], { month: 'short', day: 'numeric' });
}

export function formatDateTime(iso: string): string {
	const d = new Date(iso);
	return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) +
		' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function truncateResult(result: unknown, maxLen: number): string {
	const s = JSON.stringify(result);
	return s.length <= maxLen ? s : s.slice(0, maxLen) + '…';
}

export function fmt$(v: number): string {
	return '$' + Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function fmtPct(v: number): string {
	return (v >= 0 ? '+' : '') + v.toFixed(2) + '%';
}

export function fmtPnl(v: number): string {
	return (v >= 0 ? '+$' : '-$') + Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function parseUnixTs(v: unknown): number {
	if (typeof v === 'number') return v > 1e12 ? v / 1000 : v;
	if (typeof v === 'string') {
		const n = Number(v);
		if (!isNaN(n) && /^\d+(\.\d+)?$/.test(v.trim()))
			return n > 1e12 ? n / 1000 : n;
		const ms = new Date(v).getTime();
		if (!isNaN(ms)) return ms / 1000;
	}
	return 0;
}

export function timeAgo(v: unknown): string {
	const ts = parseUnixTs(v);
	if (!ts) return '';
	const diff = Math.floor(Date.now() / 1000) - ts;
	if (diff < 0) return 'just now';
	if (diff < 60) return `${diff}s ago`;
	if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
	if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
	return `${Math.floor(diff / 86400)}d ago`;
}

export function niceStep(range: number, target: number): number {
	const rough = range / target;
	const mag = Math.pow(10, Math.floor(Math.log10(rough)));
	const r = rough / mag;
	if (r <= 1.5) return mag;
	if (r <= 3) return 2 * mag;
	if (r <= 7) return 5 * mag;
	return 10 * mag;
}
