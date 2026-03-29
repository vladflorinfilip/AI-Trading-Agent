<script>
	import { api } from '$lib/api';
	import { onMount } from 'svelte';

	let ticker = null;
	let balance = null;
	let positions = null;
	let history = null;
	let agentResponse = '';
	let agentLoading = false;
	let error = '';

	async function refresh() {
		try {
			error = '';
			[ticker, balance, positions, history] = await Promise.all([
				api.ticker('BTC/USD'),
				api.paperBalance(),
				api.paperPositions(),
				api.paperHistory()
			]);
		} catch (e) {
			error = e.message;
		}
	}

	async function runAgent() {
		agentLoading = true;
		agentResponse = '';
		try {
			const res = await api.runAgent(
				'Analyse BTC/USD. If you see an opportunity, place a paper trade.'
			);
			agentResponse = res.response;
			await refresh();
		} catch (e) {
			agentResponse = `Error: ${e.message}`;
		} finally {
			agentLoading = false;
		}
	}

	onMount(() => {
		refresh();
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
		<div class="card error">{error}</div>
	{/if}

	<div class="grid">
		<div class="card">
			<h2>BTC/USD</h2>
			{#if ticker}
				<div class="price">${parseFloat(ticker.last_trade?.[0] || ticker.c?.[0] || '0').toLocaleString()}</div>
				<div class="meta">
					Ask: ${parseFloat(ticker.ask?.[0] || ticker.a?.[0] || '0').toLocaleString()}
					&middot;
					Bid: ${parseFloat(ticker.bid?.[0] || ticker.b?.[0] || '0').toLocaleString()}
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

		<div class="card wide">
			<h2>Agent</h2>
			<button on:click={runAgent} disabled={agentLoading}>
				{agentLoading ? 'Thinking...' : 'Run Agent'}
			</button>
			{#if agentResponse}
				<pre class="agent-output">{agentResponse}</pre>
			{/if}
		</div>

		<div class="card wide">
			<h2>Trade History</h2>
			{#if history && Array.isArray(history) && history.length > 0}
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
						{#each history as trade}
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
		max-width: 960px;
		margin: 0 auto;
		padding: 2rem 1rem;
	}

	header {
		display: flex;
		align-items: center;
		gap: 1rem;
		margin-bottom: 2rem;
	}

	h1 {
		font-size: 1.5rem;
		font-weight: 700;
	}

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

	.card.wide {
		grid-column: 1 / -1;
	}

	.card.error {
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

	.meta {
		color: #64748b;
		font-size: 0.85rem;
		margin-top: 0.25rem;
	}

	.balance-list {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}

	.balance-row {
		display: flex;
		justify-content: space-between;
		font-size: 0.9rem;
	}

	.loading, .empty {
		color: #475569;
		font-size: 0.85rem;
	}

	button {
		background: #2563eb;
		color: white;
		border: none;
		padding: 0.6rem 1.2rem;
		border-radius: 6px;
		font-size: 0.9rem;
		font-weight: 500;
		cursor: pointer;
		transition: background 0.15s;
	}

	button:hover:not(:disabled) {
		background: #1d4ed8;
	}

	button:disabled {
		opacity: 0.5;
		cursor: wait;
	}

	.agent-output {
		margin-top: 1rem;
		background: #0a0e17;
		border: 1px solid #1e293b;
		border-radius: 6px;
		padding: 1rem;
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.8rem;
		white-space: pre-wrap;
		line-height: 1.5;
		max-height: 300px;
		overflow-y: auto;
	}

	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.85rem;
	}

	th {
		text-align: left;
		color: #64748b;
		font-weight: 500;
		padding: 0.5rem 0;
		border-bottom: 1px solid #1e293b;
	}

	td {
		padding: 0.5rem 0;
		border-bottom: 1px solid #1e293b0a;
	}

	.buy { color: #10b981; }
	.sell { color: #ef4444; }
</style>
