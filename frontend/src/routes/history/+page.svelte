<script>
	import { api } from '$lib/api';
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { decisionColor, formatDateTime, stageIcon, fmt$, timeAgo } from '$lib/utils';
	import RunModal from '$lib/components/RunModal.svelte';

	let tab = 'pipeline';
	let pipelineHistory = [];
	let tradeHistory = [];
	let error = '';
	let loading = false;

	let timeFilter = '1h';
	let customFrom = '';
	let customTo = '';

	let selectedRun = null;
	let modalOpen = false;

	const PRESETS = ['1h', '6h', '24h', '7d'];

	function initFromUrl() {
		const params = $page.url.searchParams;
		const d = params.get('duration');
		if (!d) return;
		if (PRESETS.includes(d)) {
			timeFilter = d;
		} else if (d.includes('-', 3)) {
			timeFilter = 'custom';
			const parts = d.split('_');
			if (parts.length === 2) {
				customFrom = parts[0];
				customTo = parts[1];
			}
		}
	}

	function syncUrl() {
		const params = new URLSearchParams($page.url.searchParams);
		if (timeFilter === 'custom' && (customFrom || customTo)) {
			params.set('duration', `${customFrom}_${customTo}`);
		} else {
			params.set('duration', timeFilter);
		}
		const target = `${$page.url.pathname}?${params}`;
		if (target !== `${$page.url.pathname}?${$page.url.searchParams}`) {
			goto(target, { replaceState: true, keepFocus: true, noScroll: true });
		}
	}

	function getTimeRange() {
		const now = Date.now() / 1000;
		if (timeFilter === '1h')  return { from_ts: now - 3600 };
		if (timeFilter === '6h')  return { from_ts: now - 6 * 3600 };
		if (timeFilter === '24h') return { from_ts: now - 86400 };
		if (timeFilter === '7d')  return { from_ts: now - 7 * 86400 };
		if (timeFilter === 'custom') {
			const range = {};
			if (customFrom) range.from_ts = new Date(customFrom).getTime() / 1000;
			if (customTo) {
				const to = new Date(customTo);
				to.setHours(23, 59, 59, 999);
				range.to_ts = to.getTime() / 1000;
			}
			return range;
		}
		return {};
	}

	async function refresh() {
		loading = true;
		try {
			error = '';
			const range = getTimeRange();
			const [ph, th] = await Promise.all([
				api.getHistory(range),
				api.paperHistory(range)
			]);
			pipelineHistory = ph;
			tradeHistory = Array.isArray(th) ? th : [];
		} catch (e) {
			error = e.message;
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		initFromUrl();
		refresh();
	});

	$: timeFilter, customFrom, customTo, (() => { syncUrl(); refresh(); })();

	function openRunModal(run) {
		selectedRun = run;
		modalOpen = true;
	}

	function closeModal() {
		modalOpen = false;
		selectedRun = null;
	}
</script>

<div class="page">
	{#if error}
		<div class="alert alert-error">{error}</div>
	{/if}

	<!-- Tabs + time filter -->
	<div class="toolbar">
		<div class="tab-bar">
			<button class:active={tab === 'pipeline'} on:click={() => tab = 'pipeline'}>Pipeline Runs</button>
			<button class:active={tab === 'trades'} on:click={() => tab = 'trades'}>Trades</button>
		</div>
		<div class="time-controls">
			<div class="time-filters">
				{#each [['1h','1 h'],['6h','6 h'],['24h','24 h'],['7d','7 d'],['custom','Range']] as [v,l]}
					<button class:active={timeFilter === v} on:click={() => timeFilter = v}>{l}</button>
				{/each}
			</div>
			{#if timeFilter === 'custom'}
				<div class="date-range">
					<label>
						From
						<input type="date" bind:value={customFrom} />
					</label>
					<label>
						To
						<input type="date" bind:value={customTo} />
					</label>
				</div>
			{/if}
		</div>
	</div>

	{#if loading}
		<p class="loading">Loading...</p>
	{/if}

	<!-- Pipeline history tab -->
	{#if tab === 'pipeline'}
		{#if pipelineHistory.length > 0}
			<div class="card scrollable">
				<table>
					<thead>
						<tr>
							<th>Time</th>
							<th>Decision</th>
							<th>Stages</th>
							<th>Duration</th>
						</tr>
					</thead>
					<tbody>
						{#each pipelineHistory as run}
							<tr class="clickable" on:click={() => openRunModal(run)}>
								<td class="mono">{formatDateTime(run.timestamp)}</td>
								<td><span class="decision-badge sm" style="background:{decisionColor(run.decision)}">{run.decision}</span></td>
								<td class="stage-pills">
									{#each run.stages as s}
										<span class="stage-pill" title="{s.agent}: {s.duration_ms}ms">{stageIcon(s.agent)} {s.agent.split('_').map(w=>w[0].toUpperCase()).join('')}</span>
									{/each}
								</td>
								<td class="mono">{run.total_duration_ms}ms</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{:else if !loading}
			<p class="empty">No pipeline runs in this time window.</p>
		{/if}
	{/if}

	<!-- Trades tab -->
	{#if tab === 'trades'}
		{#if tradeHistory.length > 0}
			<div class="card scrollable">
				<table>
					<thead>
						<tr>
							<th>Time</th>
							<th>Side</th>
							<th>Pair</th>
							<th>Volume</th>
							<th>Price</th>
							<th>Cost</th>
						</tr>
					</thead>
					<tbody>
						{#each tradeHistory as trade}
							<tr>
								<td class="mono">{trade.time ? timeAgo(trade.time) : '--'}</td>
								<td><span class="decision-badge sm" style="background:{decisionColor((trade.type || trade.side || '').toUpperCase())}">{trade.type || trade.side || '?'}</span></td>
								<td>{trade.pair || '--'}</td>
								<td class="mono">{parseFloat(trade.vol || trade.volume || 0).toFixed(6)}</td>
								<td class="mono">{fmt$(parseFloat(trade.price || 0))}</td>
								<td class="mono">{fmt$(parseFloat(trade.cost || 0))}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{:else if !loading}
			<p class="empty">No trades in this time window.</p>
		{/if}
	{/if}
</div>

{#if modalOpen && selectedRun}
	<RunModal run={selectedRun} on:close={closeModal} />
{/if}

<style>
	.page { display: flex; flex-direction: column; gap: 0.85rem; }

	.alert { padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.85rem; }
	.alert-error { background: #fce8e4; border: 1px solid #e8c4bc; color: #8b3020; }

	.loading { color: #8b7a66; font-size: 0.85rem; text-align: center; padding: 2rem 0; }

	.toolbar {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.tab-bar, .time-filters { display: flex; gap: 0.3rem; }

	.time-controls {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: 0.4rem;
	}

	.tab-bar button, .time-filters button {
		padding: 0.45rem 1rem;
		border: 1px solid #e4ddd4;
		background: #ffffff;
		border-radius: 8px;
		font-size: 0.8rem;
		font-weight: 500;
		cursor: pointer;
		color: #6b5a48;
		transition: color 0.15s, background 0.15s, border-color 0.15s;
	}
	.tab-bar button:hover, .time-filters button:hover {
		background: #f5f0ea;
		border-color: #c4b8aa;
		color: #3d2e1f;
	}
	.tab-bar button.active {
		background: #7a5c2e;
		border-color: #7a5c2e;
		color: #fff;
		font-weight: 600;
	}
	.time-filters button.active {
		background: #f0ebe4;
		border-color: #c4b8aa;
		color: #3d2e1f;
		font-weight: 600;
	}

	.date-range {
		display: flex;
		gap: 0.6rem;
		align-items: center;
	}
	.date-range label {
		display: flex;
		align-items: center;
		gap: 0.3rem;
		font-size: 0.78rem;
		color: #6b5a48;
	}
	.date-range input[type="date"] {
		padding: 0.3rem 0.5rem;
		border: 1px solid #e4ddd4;
		border-radius: 6px;
		font-size: 0.78rem;
		color: #3d2e1f;
		background: #fff;
	}

	.scrollable {
		max-height: 70vh;
		overflow-y: auto;
	}

	.clickable {
		cursor: pointer;
		transition: background 0.12s;
	}
	.clickable:hover {
		background: #f9f6f2;
	}

	.stage-pills { display: flex; gap: 0.3rem; }
	.stage-pill {
		background: #f0ebe4;
		color: #6b5a48;
		font-size: 0.65rem;
		padding: 0.12rem 0.45rem;
		border-radius: 5px;
		font-weight: 500;
	}

	@media (max-width: 600px) {
		.toolbar { flex-direction: column; align-items: flex-start; }
		.time-controls { align-items: flex-start; }
		table { font-size: 0.75rem; }
	}
</style>
