<script>
	import { api } from '$lib/api';
	import { onMount } from 'svelte';

	let ticker = null;
	let balance = null;
	let positions = null;
	let tradeHistory = null;
	let pipelineResult = null;
	let pipelineHistory = [];
	let pipelineLoading = false;
	let expandedTools = {};
	let expandedRun = null;
	let error = '';

	async function refresh() {
		try {
			error = '';
			[ticker, balance, positions, tradeHistory] = await Promise.all([
				api.ticker('BTC/USD'),
				api.paperBalance(),
				api.paperPositions(),
				api.paperHistory()
			]);
		} catch (e) {
			error = e.message;
		}
	}

	async function loadHistory() {
		try {
			pipelineHistory = await api.getHistory(20);
		} catch (e) {
			// Redis might not be connected
		}
	}

	async function runPipeline() {
		pipelineLoading = true;
		pipelineResult = null;
		expandedTools = {};
		try {
			pipelineResult = await api.runPipeline(
				'Analyse the market and trade if you see an opportunity.'
			);
			await refresh();
			await loadHistory();
		} catch (e) {
			pipelineResult = { error: e.message };
		} finally {
			pipelineLoading = false;
		}
	}

	function toggleTools(stageIdx) {
		expandedTools[stageIdx] = !expandedTools[stageIdx];
		expandedTools = expandedTools;
	}

	function toggleRun(runId) {
		expandedRun = expandedRun === runId ? null : runId;
	}

	function stageIcon(agentName) {
		if (agentName.includes('Analyst')) return '📊';
		if (agentName.includes('Trader')) return '💹';
		if (agentName.includes('Risk')) return '🛡️';
		return '🤖';
	}

	function decisionColor(d) {
		if (d === 'BUY') return '#10b981';
		if (d === 'SELL') return '#ef4444';
		return '#64748b';
	}

	function formatTime(iso) {
		return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
	}

	function truncateResult(result, maxLen) {
		const s = JSON.stringify(result);
		if (s.length <= maxLen) return s;
		return s.slice(0, maxLen) + '…';
	}

	onMount(() => {
		refresh();
		loadHistory();
		const interval = setInterval(refresh, 30000);
		return () => clearInterval(interval);
	});
</script>

<div class="dashboard">
	<header>
		<h1>AI Trading Agent</h1>
		<span class="badge">Paper Trading</span>
	</header>

	{#if error}
		<div class="card error-card">{error}</div>
	{/if}

	<div class="grid">
		<!-- Price + Balance -->
		<div class="card">
			<h2>BTC/USD</h2>
			{#if ticker}
				<div class="price">${parseFloat(ticker.c?.[0] || '0').toLocaleString()}</div>
				<div class="meta">
					Ask: ${parseFloat(ticker.a?.[0] || '0').toLocaleString()}
					&middot;
					Bid: ${parseFloat(ticker.b?.[0] || '0').toLocaleString()}
				</div>
			{:else}
				<div class="loading">Loading...</div>
			{/if}
		</div>

		<div class="card">
			<h2>Paper Balance</h2>
			{#if balance}
				<div class="balance-list">
					{#each Object.entries(balance) as [asset, info]}
						{#if info && info.total > 0}
							<div class="balance-row">
								<span class="mono">{asset}</span>
								<span class="mono">{asset === 'USD' ? '$' : ''}{parseFloat(String(info.total)).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: asset === 'USD' ? 2 : 8})}</span>
							</div>
						{/if}
					{/each}
				</div>
			{:else}
				<div class="loading">Loading...</div>
			{/if}
		</div>

		<!-- Pipeline -->
		<div class="card wide">
			<div class="section-header">
				<h2>Pipeline</h2>
				<span class="pipeline-label">Analyst → Trader → Risk</span>
			</div>

			<button on:click={runPipeline} disabled={pipelineLoading} class="run-btn">
				{pipelineLoading ? '⏳ Running pipeline...' : '▶ Run Pipeline'}
			</button>

			{#if pipelineResult && !pipelineResult.error}
				<div class="pipeline-summary">
					<span class="decision-badge" style="background: {decisionColor(pipelineResult.decision)}">
						{pipelineResult.decision}
					</span>
					<span class="meta">{pipelineResult.total_duration_ms}ms total</span>
				</div>

				{#each pipelineResult.stages as stage, i}
					<div class="stage-card">
						<div class="stage-header">
							<span class="stage-name">{stageIcon(stage.agent)} {stage.agent}</span>
							<span class="stage-meta">
								{stage.tool_calls.length} tool{stage.tool_calls.length !== 1 ? 's' : ''}
								&middot; {stage.duration_ms}ms
							</span>
						</div>

						{#if stage.tool_calls.length > 0}
							<button class="tool-toggle" on:click={() => toggleTools(i)}>
								{expandedTools[i] ? '▾ Hide' : '▸ Show'} tool calls
							</button>

							{#if expandedTools[i]}
								<div class="tool-list">
									{#each stage.tool_calls as tc}
										<div class="tool-call">
											<div class="tool-name">
												<span class="fn">{tc.name}</span>({Object.entries(tc.args).map(([k,v]) => `${k}="${v}"`).join(', ')})
												<span class="tool-time">{tc.duration_ms}ms</span>
											</div>
											<div class="tool-result">{truncateResult(tc.result, 200)}</div>
										</div>
									{/each}
								</div>
							{/if}
						{/if}

						<div class="stage-response">{stage.response}</div>
					</div>
				{/each}
			{:else if pipelineResult && pipelineResult.error}
				<div class="stage-response error-text">Error: {pipelineResult.error}</div>
			{/if}
		</div>

		<!-- Pipeline History -->
		<div class="card wide">
			<h2>Pipeline History</h2>
			{#if pipelineHistory.length > 0}
				<div class="history-list">
					{#each pipelineHistory as run}
						<button class="history-row" on:click={() => toggleRun(run.id)}>
							<span class="history-time">{formatTime(run.timestamp)}</span>
							<span class="decision-badge small" style="background: {decisionColor(run.decision)}">
								{run.decision}
							</span>
							<span class="meta">{run.total_duration_ms}ms</span>
							<span class="meta">{run.stages.length} stages</span>
						</button>

						{#if expandedRun === run.id}
							<div class="history-detail">
								{#each run.stages as stage}
									<div class="stage-mini">
										<span class="stage-name-sm">{stageIcon(stage.agent)} {stage.agent}</span>
										<span class="meta">{stage.tool_calls.length} tools &middot; {stage.duration_ms}ms</span>
										<div class="stage-response-sm">{stage.response}</div>
									</div>
								{/each}
							</div>
						{/if}
					{/each}
				</div>
			{:else}
				<p class="empty">No pipeline runs yet</p>
			{/if}
		</div>

		<!-- Trade History -->
		<div class="card wide">
			<h2>Trade History</h2>
			{#if tradeHistory && Array.isArray(tradeHistory) && tradeHistory.length > 0}
				<table>
					<thead>
						<tr>
							<th>Pair</th>
							<th>Side</th>
							<th>Volume</th>
							<th>Price</th>
						</tr>
					</thead>
					<tbody>
						{#each tradeHistory as trade}
							<tr>
								<td class="mono">{trade.pair}</td>
								<td class:buy={trade.side === 'buy'} class:sell={trade.side === 'sell'}>{trade.side}</td>
								<td class="mono">{trade.volume}</td>
								<td class="mono">{trade.price}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{:else}
				<p class="empty">No trades yet</p>
			{/if}
		</div>
	</div>
</div>

<style>
	.dashboard {
		max-width: 1000px;
		margin: 0 auto;
		padding: 2rem 1rem;
	}

	header {
		display: flex;
		align-items: center;
		gap: 1rem;
		margin-bottom: 2rem;
	}

	h1 { font-size: 1.5rem; font-weight: 700; }

	.badge {
		background: #10b981;
		color: #000;
		padding: 0.2rem 0.6rem;
		border-radius: 4px;
		font-size: 0.75rem;
		font-weight: 600;
		text-transform: uppercase;
	}

	h2 {
		font-size: 0.85rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: #64748b;
		margin-bottom: 0.75rem;
	}

	.grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 1rem;
	}

	.card {
		background: #111827;
		border: 1px solid #1e293b;
		border-radius: 8px;
		padding: 1.25rem;
	}

	.card.wide { grid-column: 1 / -1; }

	.error-card {
		grid-column: 1 / -1;
		background: #7f1d1d;
		border-color: #991b1b;
	}

	.price {
		font-family: 'JetBrains Mono', monospace;
		font-size: 2rem;
		font-weight: 600;
		color: #f1f5f9;
	}

	.meta { color: #64748b; font-size: 0.8rem; }

	.balance-list { display: flex; flex-direction: column; gap: 0.4rem; }
	.balance-row { display: flex; justify-content: space-between; font-size: 0.9rem; }

	.loading, .empty { color: #475569; font-size: 0.85rem; }

	/* Pipeline */
	.section-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	.pipeline-label {
		font-size: 0.75rem;
		color: #475569;
		font-family: 'JetBrains Mono', monospace;
	}

	.run-btn {
		background: #2563eb;
		color: white;
		border: none;
		padding: 0.6rem 1.4rem;
		border-radius: 6px;
		font-size: 0.9rem;
		font-weight: 500;
		cursor: pointer;
		transition: background 0.15s;
		width: 100%;
	}

	.run-btn:hover:not(:disabled) { background: #1d4ed8; }
	.run-btn:disabled { opacity: 0.5; cursor: wait; }

	.pipeline-summary {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-top: 1rem;
		padding-bottom: 0.75rem;
		border-bottom: 1px solid #1e293b;
	}

	.decision-badge {
		color: #000;
		font-weight: 700;
		font-size: 0.8rem;
		padding: 0.25rem 0.7rem;
		border-radius: 4px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.decision-badge.small {
		font-size: 0.7rem;
		padding: 0.15rem 0.5rem;
	}

	/* Stage cards */
	.stage-card {
		margin-top: 0.75rem;
		background: #0d1320;
		border: 1px solid #1e293b;
		border-radius: 6px;
		padding: 1rem;
	}

	.stage-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}

	.stage-name {
		font-weight: 600;
		font-size: 0.9rem;
	}

	.stage-meta {
		font-size: 0.75rem;
		color: #64748b;
		font-family: 'JetBrains Mono', monospace;
	}

	.tool-toggle {
		background: none;
		border: none;
		color: #60a5fa;
		font-size: 0.8rem;
		cursor: pointer;
		padding: 0.2rem 0;
		width: auto;
		text-align: left;
	}

	.tool-toggle:hover { color: #93c5fd; }

	.tool-list {
		margin: 0.5rem 0;
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}

	.tool-call {
		background: #0a0e17;
		border: 1px solid #1e293b;
		border-radius: 4px;
		padding: 0.5rem 0.75rem;
		font-size: 0.78rem;
	}

	.tool-name {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}

	.fn {
		color: #60a5fa;
		font-family: 'JetBrains Mono', monospace;
		font-weight: 600;
	}

	.tool-time {
		margin-left: auto;
		color: #475569;
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.7rem;
	}

	.tool-result {
		color: #64748b;
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.72rem;
		margin-top: 0.25rem;
		word-break: break-all;
	}

	.stage-response {
		margin-top: 0.5rem;
		font-size: 0.85rem;
		line-height: 1.6;
		color: #cbd5e1;
		white-space: pre-wrap;
	}

	.error-text { color: #fca5a5; }

	/* History */
	.history-list {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.history-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		background: #0d1320;
		border: 1px solid #1e293b;
		border-radius: 6px;
		padding: 0.6rem 0.9rem;
		cursor: pointer;
		width: 100%;
		text-align: left;
		color: #e2e8f0;
		transition: border-color 0.15s;
	}

	.history-row:hover { border-color: #334155; }

	.history-time {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.8rem;
		color: #94a3b8;
	}

	.history-detail {
		background: #0a0e17;
		border: 1px solid #1e293b;
		border-top: none;
		border-radius: 0 0 6px 6px;
		padding: 0.75rem;
		margin-top: -0.25rem;
		margin-bottom: 0.25rem;
	}

	.stage-mini {
		padding: 0.5rem 0;
		border-bottom: 1px solid #1e293b22;
	}

	.stage-mini:last-child { border-bottom: none; }

	.stage-name-sm {
		font-weight: 600;
		font-size: 0.82rem;
	}

	.stage-response-sm {
		font-size: 0.78rem;
		color: #94a3b8;
		margin-top: 0.3rem;
		white-space: pre-wrap;
		max-height: 100px;
		overflow-y: auto;
	}

	/* Table */
	table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
	th { text-align: left; color: #64748b; font-weight: 500; padding: 0.5rem 0; border-bottom: 1px solid #1e293b; }
	td { padding: 0.5rem 0; border-bottom: 1px solid #1e293b0a; }
	.buy { color: #10b981; }
	.sell { color: #ef4444; }
</style>
