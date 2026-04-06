<script>
	import { api } from '$lib/api';
	import { onMount } from 'svelte';
	import { decisionColor, formatDateTime, stageIcon, formatDate, truncateResult, fmt$, timeAgo } from '$lib/utils';

	let tab = 'pipeline';
	let pipelineHistory = [];
	let tradeHistory = [];
	let error = '';

	let timeFilter = 'all';

	async function refresh() {
		try {
			error = '';
			const [ph, th] = await Promise.all([api.getHistory(), api.paperHistory()]);
			pipelineHistory = ph;
			tradeHistory = Array.isArray(th) ? th : [];
		} catch (e) {
			error = e.message;
		}
	}
	onMount(refresh);

	function matchesFilter(ts) {
		if (timeFilter === 'all') return true;
		const now = Date.now();
		if (timeFilter === 'today') {
			const start = new Date();
			start.setHours(0, 0, 0, 0);
			return ts >= start.getTime();
		}
		if (timeFilter === '24h') return ts >= now - 86_400_000;
		if (timeFilter === '7d')  return ts >= now - 7 * 86_400_000;
		return true;
	}

	$: filteredPipeline = pipelineHistory.filter(r => matchesFilter(new Date(r.timestamp).getTime()));
	$: filteredTrades   = tradeHistory.filter(t => matchesFilter((t.time || 0) * 1000));
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
		<div class="time-filters">
			{#each [['today','Today'],['24h','24 h'],['7d','7 d'],['all','All']] as [v,l]}
				<button class:active={timeFilter === v} on:click={() => timeFilter = v}>{l}</button>
			{/each}
		</div>
	</div>

	<!-- Pipeline history tab -->
	{#if tab === 'pipeline'}
		{#if filteredPipeline.length > 0}
			<div class="card">
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
						{#each filteredPipeline as run}
							<tr>
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
		{:else}
			<p class="empty">No pipeline runs match the current filter.</p>
		{/if}
	{/if}

	<!-- Trades tab -->
	{#if tab === 'trades'}
		{#if filteredTrades.length > 0}
			<div class="card">
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
						{#each filteredTrades as trade}
							<tr>
								<td class="mono">{trade.time ? formatDateTime(trade.time * 1000) : '--'}</td>
								<td><span class="decision-badge sm" style="background:{decisionColor(trade.type?.toUpperCase())}">{trade.type || '?'}</span></td>
								<td>{trade.pair || '--'}</td>
								<td class="mono">{parseFloat(trade.vol || 0).toFixed(6)}</td>
								<td class="mono">{fmt$(parseFloat(trade.price || 0))}</td>
								<td class="mono">{fmt$(parseFloat(trade.cost || 0))}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{:else}
			<p class="empty">No trades match the current filter.</p>
		{/if}
	{/if}
</div>

<style>
	.page { display: flex; flex-direction: column; gap: 0.85rem; }

	.alert { padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.85rem; }
	.alert-error { background: #fce8e4; border: 1px solid #e8c4bc; color: #8b3020; }

	.toolbar {
		display: flex;
		justify-content: space-between;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.tab-bar, .time-filters { display: flex; gap: 0.3rem; }

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
		table { font-size: 0.75rem; }
	}
</style>
