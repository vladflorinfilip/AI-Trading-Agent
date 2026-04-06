<script>
	import { api } from '$lib/api';
	import { onMount } from 'svelte';
	import { slide } from 'svelte/transition';

	let ticker = null;
	let portfolio = null;
	let performance = null;
	let onchain = null;
	let tradeHistory = null;
	let pipelineResult = null;
	let pipelineHistory = [];
	let pipelineLoading = false;
	let error = '';

	let expandedTools = {};
	let expandedRun = null;
	let sections = { pipeline: true, pipelineHistory: false, tradeHistory: false };

	// Chart
	let chartContainer;
	let chartW = 800;
	let hoverIdx = -1;
	const chartH = 220;
	const pad = { top: 24, right: 16, bottom: 32, left: 64 };

	// ── Data loading ──────────────────────────────────────────────────

	async function refreshAll() {
		try {
			error = '';
			const results = await Promise.allSettled([
				api.ticker('BTC/USD'),
				api.portfolio(),
				api.performance(),
				api.paperHistory(),
				api.getHistory(20),
				api.onchain(),
			]);
			if (results[0].status === 'fulfilled') ticker = results[0].value;
			if (results[1].status === 'fulfilled') portfolio = results[1].value;
			if (results[2].status === 'fulfilled') performance = results[2].value;
			if (results[3].status === 'fulfilled') tradeHistory = results[3].value;
			if (results[4].status === 'fulfilled') pipelineHistory = results[4].value || [];
			if (results[5].status === 'fulfilled') onchain = results[5].value;
		} catch (e) {
			error = e.message;
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
			await refreshAll();
		} catch (e) {
			pipelineResult = { error: e.message };
		} finally {
			pipelineLoading = false;
		}
	}

	onMount(() => {
		refreshAll();
		const interval = setInterval(refreshAll, 30000);
		return () => clearInterval(interval);
	});

	// ── Helpers ────────────────────────────────────────────────────────

	function toggleSection(key) {
		sections[key] = !sections[key];
		sections = sections;
	}
	function toggleTools(i) {
		expandedTools[i] = !expandedTools[i];
		expandedTools = expandedTools;
	}
	function toggleRun(id) {
		expandedRun = expandedRun === id ? null : id;
	}

	function stageIcon(name) {
		if (name.includes('Analyst')) return '📊';
		if (name.includes('Trader')) return '💹';
		if (name.includes('Risk')) return '🛡️';
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
	function formatTimestamp(ts) {
		return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
	}
	function formatDate(ts) {
		return new Date(ts * 1000).toLocaleDateString([], { month: 'short', day: 'numeric' });
	}
	function truncateResult(result, maxLen) {
		const s = JSON.stringify(result);
		return s.length <= maxLen ? s : s.slice(0, maxLen) + '…';
	}
	function fmt$(v) {
		return '$' + Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	}
	function fmtPct(v) {
		return (v >= 0 ? '+' : '') + v.toFixed(2) + '%';
	}
	function fmtPnl(v) {
		return (v >= 0 ? '+$' : '-$') + Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	}

	// ── On-chain metrics ──────────────────────────────────────────────

	function timeAgo(ts) {
		if (!ts) return '';
		const diff = Math.floor(Date.now() / 1000) - ts;
		if (diff < 60)   return `${diff}s ago`;
		if (diff < 3600)  return `${Math.floor(diff / 60)}m ago`;
		if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
		return `${Math.floor(diff / 86400)}d ago`;
	}

	$: ocHasData = onchain && onchain.timestamp > 0;
	$: ocTradesPct = ocHasData && onchain.maxTradesPerHour > 0
		? Math.min((onchain.tradesThisHour / onchain.maxTradesPerHour) * 100, 100) : 0;

	// ── PnL chart ─────────────────────────────────────────────────────

	$: chartData = portfolio?.pnl_series || [];
	$: startBal = portfolio?.starting_balance || 10000;
	$: pnlPositive = (portfolio?.pnl || 0) >= 0;
	$: accentColor = pnlPositive ? '#10b981' : '#ef4444';

	$: plotW = chartW - pad.left - pad.right;
	$: plotH = chartH - pad.top - pad.bottom;

	$: vals = chartData.map(d => d.value);
	$: allVals = [...vals, startBal];
	$: yMin = allVals.length ? Math.min(...allVals) : 9500;
	$: yMax = allVals.length ? Math.max(...allVals) : 10500;
	$: yRange = yMax - yMin || 100;
	$: yPad = yRange * 0.12;

	$: tsMin = chartData.length ? chartData[0].ts : 0;
	$: tsMax = chartData.length > 1 ? chartData[chartData.length - 1].ts : tsMin + 1;
	$: tsRange = tsMax - tsMin || 1;

	function sx(ts) { return pad.left + ((ts - tsMin) / tsRange) * plotW; }
	function sy(v)  { return pad.top + (1 - (v - (yMin - yPad)) / (yRange + 2 * yPad)) * plotH; }

	$: linePath = chartData.map((d, i) =>
		`${i === 0 ? 'M' : 'L'}${sx(d.ts).toFixed(1)},${sy(d.value).toFixed(1)}`
	).join(' ');

	$: areaPath = chartData.length > 0
		? linePath +
		  ` L${sx(chartData[chartData.length - 1].ts).toFixed(1)},${(pad.top + plotH).toFixed(1)}` +
		  ` L${sx(chartData[0].ts).toFixed(1)},${(pad.top + plotH).toFixed(1)} Z`
		: '';

	function niceStep(range, target) {
		const rough = range / target;
		const mag = Math.pow(10, Math.floor(Math.log10(rough)));
		const r = rough / mag;
		if (r <= 1.5) return mag;
		if (r <= 3) return 2 * mag;
		if (r <= 7) return 5 * mag;
		return 10 * mag;
	}

	$: yTicks = (() => {
		const step = niceStep(yRange + 2 * yPad, 4);
		const start = Math.floor((yMin - yPad) / step) * step;
		const ticks = [];
		for (let v = start; v <= yMax + yPad + step; v += step) {
			if (sy(v) >= pad.top - 5 && sy(v) <= pad.top + plotH + 5) ticks.push(v);
		}
		return ticks;
	})();

	$: xTicks = (() => {
		if (chartData.length < 2) return [];
		const count = Math.min(6, chartData.length);
		const step = Math.max(1, Math.floor((chartData.length - 1) / (count - 1)));
		const ticks = [];
		for (let i = 0; i < chartData.length; i += step) ticks.push(chartData[i]);
		if (ticks[ticks.length - 1]?.ts !== chartData[chartData.length - 1]?.ts) {
			ticks.push(chartData[chartData.length - 1]);
		}
		return ticks;
	})();

	$: startBalY = sy(startBal);

	$: hoverPoint = hoverIdx >= 0 && hoverIdx < chartData.length ? chartData[hoverIdx] : null;
	$: hoverX = hoverPoint ? sx(hoverPoint.ts) : 0;
	$: hoverY = hoverPoint ? sy(hoverPoint.value) : 0;

	function onChartMove(e) {
		if (!chartData.length || plotW <= 0) return;
		const rect = e.currentTarget.getBoundingClientRect();
		const mouseX = (e.clientX - rect.left) / rect.width * chartW;
		let best = Infinity, idx = -1;
		for (let i = 0; i < chartData.length; i++) {
			const dist = Math.abs(sx(chartData[i].ts) - mouseX);
			if (dist < best) { best = dist; idx = i; }
		}
		hoverIdx = best < 40 ? idx : -1;
	}

	// ── Performance bars ──────────────────────────────────────────────

	$: decisions = performance?.decisions || { BUY: 0, SELL: 0, HOLD: 0 };
	$: totalDecisions = (decisions.BUY || 0) + (decisions.SELL || 0) + (decisions.HOLD || 0);
	$: buyPct  = totalDecisions ? (decisions.BUY  / totalDecisions) * 100 : 0;
	$: sellPct = totalDecisions ? (decisions.SELL / totalDecisions) * 100 : 0;
	$: holdPct = totalDecisions ? (decisions.HOLD / totalDecisions) * 100 : 0;
</script>

<div class="dashboard">
	<header>
		<div class="header-left">
			<h1>AI Trading Agent</h1>
			<span class="badge live">Paper Trading</span>
			<span class="badge chain">Sepolia</span>
		</div>
		{#if performance?.last_run}
			<span class="header-meta">Last run: {formatTime(performance.last_run)}</span>
		{/if}
	</header>

	{#if error}
		<div class="alert alert-error">{error}</div>
	{/if}

	<!-- ── Stat cards ──────────────────────────────────────────────── -->

	<div class="stats">
		<div class="stat-card">
			<span class="stat-label">Portfolio Value</span>
			{#if portfolio}
				<span class="stat-value">{fmt$(portfolio.total_value)}</span>
				<span class="stat-sub">Started at {fmt$(portfolio.starting_balance)}</span>
			{:else}
				<span class="stat-value dim">—</span>
			{/if}
		</div>

		<div class="stat-card">
			<span class="stat-label">P&L</span>
			{#if portfolio}
				<span class="stat-value" class:positive={portfolio.pnl >= 0} class:negative={portfolio.pnl < 0}>
					{fmtPnl(portfolio.pnl)}
				</span>
				<span class="stat-sub" class:positive={portfolio.pnl >= 0} class:negative={portfolio.pnl < 0}>
					{fmtPct(portfolio.pnl_pct)}
				</span>
			{:else}
				<span class="stat-value dim">—</span>
			{/if}
		</div>

		<div class="stat-card">
			<span class="stat-label">BTC / USD</span>
			{#if ticker}
				<span class="stat-value">${parseFloat(ticker.c?.[0] || '0').toLocaleString()}</span>
				<span class="stat-sub">
					Ask {parseFloat(ticker.a?.[0] || '0').toLocaleString()}
					· Bid {parseFloat(ticker.b?.[0] || '0').toLocaleString()}
				</span>
			{:else}
				<span class="stat-value dim">—</span>
			{/if}
		</div>

		<div class="stat-card">
			<span class="stat-label">Trades</span>
			{#if portfolio}
				<span class="stat-value">{portfolio.trade_count}</span>
				<span class="stat-sub">
					<span class="positive">{portfolio.buy_count} buy</span>
					·
					<span class="negative">{portfolio.sell_count} sell</span>
				</span>
			{:else}
				<span class="stat-value dim">—</span>
			{/if}
		</div>
	</div>

	<!-- ── On-chain status ─────────────────────────────────────────── -->

	<div class="card onchain-card">
		<div class="card-header">
			<h2>On-Chain Status</h2>
			{#if ocHasData}
				<span class="card-meta">
					Agent #{onchain.agentId} · Sepolia · Updated {timeAgo(onchain.timestamp)}
				</span>
			{/if}
		</div>

		{#if ocHasData}
			<div class="oc-grid">
				<div class="oc-metric">
					<span class="oc-value">{onchain.attestationCount}</span>
					<div class="oc-bar-track"><div class="oc-bar-fill attestation" style="width:{Math.min(onchain.attestationCount, 100)}%"></div></div>
					<span class="oc-label">Checkpoints posted</span>
				</div>

				<div class="oc-metric">
					<span class="oc-value">{onchain.validationScore}<span class="oc-max"> / 100</span></span>
					<div class="oc-bar-track"><div class="oc-bar-fill validation" style="width:{onchain.validationScore}%"></div></div>
					<span class="oc-label">Validation score</span>
				</div>

				<div class="oc-metric">
					<span class="oc-value">{onchain.reputationScore}<span class="oc-max"> / 100</span></span>
					<div class="oc-bar-track"><div class="oc-bar-fill reputation" style="width:{onchain.reputationScore}%"></div></div>
					<span class="oc-label">Reputation score</span>
				</div>

				<div class="oc-metric">
					<span class="oc-value">{onchain.tradesThisHour}<span class="oc-max"> / {onchain.maxTradesPerHour}</span></span>
					<div class="oc-bar-track"><div class="oc-bar-fill trades" class:warn={ocTradesPct > 80} style="width:{ocTradesPct}%"></div></div>
					<span class="oc-label">Trades this hour</span>
				</div>
			</div>
		{:else}
			<p class="empty">Waiting for the agent to publish on-chain metrics...</p>
		{/if}
	</div>

	<!-- ── PnL chart ───────────────────────────────────────────────── -->

	<div class="card">
		<div class="card-header">
			<h2>Portfolio Performance</h2>
			{#if portfolio}
				<span class="card-meta mono" class:positive={pnlPositive} class:negative={!pnlPositive}>
					{fmtPnl(portfolio.pnl)} ({fmtPct(portfolio.pnl_pct)})
				</span>
			{/if}
		</div>

		<div class="chart-wrap" bind:this={chartContainer} bind:clientWidth={chartW}>
			{#if chartData.length > 0}
				<svg
					viewBox="0 0 {chartW} {chartH}"
					preserveAspectRatio="none"
					class="chart-svg"
					role="img"
					aria-label="Portfolio performance chart"
					on:mousemove={onChartMove}
					on:mouseleave={() => hoverIdx = -1}
				>
					<defs>
						<linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
							<stop offset="0%"   stop-color={accentColor} stop-opacity="0.25" />
							<stop offset="100%" stop-color={accentColor} stop-opacity="0.02" />
						</linearGradient>
					</defs>

					<!-- Y gridlines -->
					{#each yTicks as v}
						<line
							x1={pad.left} y1={sy(v)} x2={chartW - pad.right} y2={sy(v)}
							stroke="#1e293b" stroke-width="1"
						/>
						<text
							x={pad.left - 8} y={sy(v) + 4}
							fill="#475569" font-size="11" text-anchor="end"
							font-family="'JetBrains Mono', monospace"
						>${Math.round(v).toLocaleString()}</text>
					{/each}

					<!-- Starting balance reference -->
					<line
						x1={pad.left} y1={startBalY}
						x2={chartW - pad.right} y2={startBalY}
						stroke="#334155" stroke-width="1" stroke-dasharray="6,4"
					/>

					<!-- Area + Line -->
					<path d={areaPath} fill="url(#areaGrad)" />
					<path d={linePath} fill="none" stroke={accentColor} stroke-width="2" stroke-linejoin="round" />

					<!-- X labels -->
					{#each xTicks as d}
						<text
							x={sx(d.ts)} y={chartH - 6}
							fill="#475569" font-size="10" text-anchor="middle"
							font-family="'JetBrains Mono', monospace"
						>{formatTimestamp(d.ts)}</text>
					{/each}

					<!-- Hover crosshair -->
					{#if hoverPoint}
						<line
							x1={hoverX} y1={pad.top} x2={hoverX} y2={pad.top + plotH}
							stroke="#475569" stroke-width="1" stroke-dasharray="3,3"
						/>
						<circle cx={hoverX} cy={hoverY} r="4" fill={accentColor} stroke="#0a0e17" stroke-width="2" />
					{/if}
				</svg>

				<!-- Hover tooltip -->
				{#if hoverPoint}
					<div
						class="chart-tooltip"
						style="left: {Math.min(hoverX, chartW - 160)}px; top: {Math.max(hoverY - 60, 0)}px"
					>
						<div class="tooltip-value" class:positive={hoverPoint.value >= startBal} class:negative={hoverPoint.value < startBal}>
							{fmt$(hoverPoint.value)}
						</div>
						<div class="tooltip-meta">
							{fmtPnl(hoverPoint.value - startBal)} · {formatTimestamp(hoverPoint.ts)}
						</div>
					</div>
				{/if}
			{:else}
				<div class="chart-empty">Collecting data — chart appears after the first few ticks</div>
			{/if}
		</div>
	</div>

	<!-- ── Decision distribution ────────────────────────────────────── -->

	{#if performance && performance.total_runs > 0}
		<div class="card">
			<div class="card-header">
				<h2>Decision Distribution</h2>
				<span class="card-meta">{performance.total_runs} pipeline runs · avg {performance.avg_duration_ms}ms</span>
			</div>
			<div class="dist-bar">
				{#if buyPct > 0}
					<div class="dist-segment buy" style="width:{buyPct}%">
						{#if buyPct > 12}<span>BUY {decisions.BUY}</span>{/if}
					</div>
				{/if}
				{#if sellPct > 0}
					<div class="dist-segment sell" style="width:{sellPct}%">
						{#if sellPct > 12}<span>SELL {decisions.SELL}</span>{/if}
					</div>
				{/if}
				{#if holdPct > 0}
					<div class="dist-segment hold" style="width:{holdPct}%">
						{#if holdPct > 12}<span>HOLD {decisions.HOLD}</span>{/if}
					</div>
				{/if}
			</div>
			<div class="dist-legend">
				<span><i class="dot buy"></i> Buy {decisions.BUY} ({buyPct.toFixed(0)}%)</span>
				<span><i class="dot sell"></i> Sell {decisions.SELL} ({sellPct.toFixed(0)}%)</span>
				<span><i class="dot hold"></i> Hold {decisions.HOLD} ({holdPct.toFixed(0)}%)</span>
			</div>
		</div>
	{/if}

	<!-- ── Holdings ─────────────────────────────────────────────────── -->

	{#if portfolio && (portfolio.btc_balance > 0 || portfolio.eth_balance > 0)}
		<div class="card">
			<h2>Holdings</h2>
			<div class="holdings-grid">
				<div class="holding">
					<span class="holding-asset">USD</span>
					<span class="holding-value mono">{fmt$(portfolio.usd_balance)}</span>
				</div>
				{#if portfolio.btc_balance > 0}
					<div class="holding">
						<span class="holding-asset">BTC</span>
						<span class="holding-value mono">{portfolio.btc_balance.toFixed(8)}</span>
						<span class="holding-usd">≈ {fmt$(portfolio.btc_balance * portfolio.btc_price)}</span>
					</div>
				{/if}
				{#if portfolio.eth_balance > 0}
					<div class="holding">
						<span class="holding-asset">ETH</span>
						<span class="holding-value mono">{portfolio.eth_balance.toFixed(6)}</span>
						<span class="holding-usd">≈ {fmt$(portfolio.eth_balance * portfolio.eth_price)}</span>
					</div>
				{/if}
			</div>
		</div>
	{/if}

	<!-- ── Pipeline (collapsible) ───────────────────────────────────── -->

	<div class="section">
		<button class="section-toggle" on:click={() => toggleSection('pipeline')}>
			<span class="chevron" class:open={sections.pipeline}>›</span>
			<span class="section-title">Pipeline</span>
			<span class="section-meta">Analyst → Trader → Risk</span>
			<button
				class="run-btn-inline"
				on:click|stopPropagation={runPipeline}
				disabled={pipelineLoading}
			>
				{pipelineLoading ? '⏳ Running…' : '▶ Run'}
			</button>
		</button>

		{#if sections.pipeline}
			<div class="section-body" transition:slide={{ duration: 200 }}>
				{#if pipelineResult && !pipelineResult.error}
					<div class="pipeline-summary">
						<span class="decision-badge" style="background:{decisionColor(pipelineResult.decision)}">
							{pipelineResult.decision}
						</span>
						<span class="meta">{pipelineResult.total_duration_ms}ms total</span>
					</div>

					{#each pipelineResult.stages as stage, i}
						<div class="stage-card">
							<div class="stage-header">
								<span class="stage-name">{stageIcon(stage.agent)} {stage.agent}</span>
								<span class="stage-meta mono">
									{stage.tool_calls.length} tool{stage.tool_calls.length !== 1 ? 's' : ''}
									· {stage.duration_ms}ms
								</span>
							</div>

							{#if stage.tool_calls.length > 0}
								<button class="tool-toggle" on:click={() => toggleTools(i)}>
									{expandedTools[i] ? '▾ Hide' : '▸ Show'} tool calls
								</button>

								{#if expandedTools[i]}
									<div class="tool-list" transition:slide={{ duration: 150 }}>
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
				{:else if pipelineResult?.error}
					<div class="stage-response error-text">Error: {pipelineResult.error}</div>
				{:else}
					<p class="empty">Click "Run" to execute the pipeline</p>
				{/if}
			</div>
		{/if}
	</div>

	<!-- ── Pipeline History (collapsible) ───────────────────────────── -->

	<div class="section">
		<button class="section-toggle" on:click={() => toggleSection('pipelineHistory')}>
			<span class="chevron" class:open={sections.pipelineHistory}>›</span>
			<span class="section-title">Pipeline History</span>
			<span class="section-meta">{pipelineHistory.length} run{pipelineHistory.length !== 1 ? 's' : ''}</span>
		</button>

		{#if sections.pipelineHistory}
			<div class="section-body" transition:slide={{ duration: 200 }}>
				{#if pipelineHistory.length > 0}
					<div class="history-list">
						{#each pipelineHistory as run}
							<button class="history-row" on:click={() => toggleRun(run.id)}>
								<span class="history-time mono">{formatTime(run.timestamp)}</span>
								<span class="decision-badge sm" style="background:{decisionColor(run.decision)}">
									{run.decision}
								</span>
								<span class="meta">{run.total_duration_ms}ms</span>
								<span class="meta">{run.stages.length} stages</span>
							</button>

							{#if expandedRun === run.id}
								<div class="history-detail" transition:slide={{ duration: 150 }}>
									{#each run.stages as stage}
										<div class="stage-mini">
											<span class="stage-name-sm">{stageIcon(stage.agent)} {stage.agent}</span>
											<span class="meta">{stage.tool_calls.length} tools · {stage.duration_ms}ms</span>
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
		{/if}
	</div>

	<!-- ── Trade History (collapsible) ──────────────────────────────── -->

	<div class="section">
		<button class="section-toggle" on:click={() => toggleSection('tradeHistory')}>
			<span class="chevron" class:open={sections.tradeHistory}>›</span>
			<span class="section-title">Trade History</span>
			<span class="section-meta">
				{tradeHistory && Array.isArray(tradeHistory) ? tradeHistory.length : 0} trade{(tradeHistory?.length || 0) !== 1 ? 's' : ''}
			</span>
		</button>

		{#if sections.tradeHistory}
			<div class="section-body" transition:slide={{ duration: 200 }}>
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
									<td class:positive={trade.side === 'buy'} class:negative={trade.side === 'sell'}>{trade.side}</td>
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
		{/if}
	</div>
</div>

<style>
	/* ── Layout ─────────────────────────────────────────────────────── */

	.dashboard {
		max-width: 1040px;
		margin: 0 auto;
		padding: 1.5rem 1rem 3rem;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 0.5rem;
	}
	.header-left { display: flex; align-items: center; gap: 0.75rem; }
	h1 { font-size: 1.35rem; font-weight: 700; letter-spacing: -0.02em; }
	.header-meta { font-size: 0.75rem; color: #475569; }

	.badge {
		padding: 0.15rem 0.55rem;
		border-radius: 4px;
		font-size: 0.68rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}
	.badge.live  { background: #10b981; color: #022c22; }
	.badge.chain { background: #2563eb22; color: #60a5fa; border: 1px solid #2563eb44; }

	.alert { padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.85rem; }
	.alert-error { background: #7f1d1d; border: 1px solid #991b1b; }

	/* ── Stat cards ─────────────────────────────────────────────────── */

	.stats {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 0.75rem;
	}

	.stat-card {
		background: #111827;
		border: 1px solid #1e293b;
		border-radius: 10px;
		padding: 1rem 1.1rem;
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
	}

	.stat-label {
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: #64748b;
		font-weight: 500;
	}
	.stat-value {
		font-family: 'JetBrains Mono', monospace;
		font-size: 1.45rem;
		font-weight: 600;
		color: #f1f5f9;
		line-height: 1.2;
	}
	.stat-value.dim { color: #334155; }
	.stat-sub { font-size: 0.75rem; color: #64748b; }

	.positive { color: #10b981; }
	.negative { color: #ef4444; }

	/* ── Cards ──────────────────────────────────────────────────────── */

	.card {
		background: #111827;
		border: 1px solid #1e293b;
		border-radius: 10px;
		padding: 1.15rem;
	}
	.card-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.75rem;
	}
	.card-meta { font-size: 0.78rem; color: #64748b; }

	h2 {
		font-size: 0.78rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: #64748b;
		font-weight: 500;
		margin: 0;
	}

	/* ── PnL chart ─────────────────────────────────────────────────── */

	.chart-wrap {
		position: relative;
		width: 100%;
		height: 220px;
	}
	.chart-svg {
		width: 100%;
		height: 100%;
	}
	.chart-empty {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 100%;
		color: #334155;
		font-size: 0.85rem;
	}

	.chart-tooltip {
		position: absolute;
		pointer-events: none;
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 6px;
		padding: 0.4rem 0.65rem;
		z-index: 10;
	}
	.tooltip-value {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.9rem;
		font-weight: 600;
	}
	.tooltip-meta {
		font-size: 0.7rem;
		color: #64748b;
		font-family: 'JetBrains Mono', monospace;
	}

	/* ── On-chain status ───────────────────────────────────────────── */

	.onchain-card { border-color: #1e293b; }

	.oc-grid {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 1.2rem;
	}

	.oc-metric {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
	}

	.oc-value {
		font-family: 'JetBrains Mono', monospace;
		font-size: 1.3rem;
		font-weight: 600;
		color: #f1f5f9;
		line-height: 1.2;
	}
	.oc-max {
		font-size: 0.78rem;
		font-weight: 400;
		color: #475569;
	}

	.oc-bar-track {
		height: 6px;
		background: #1e293b;
		border-radius: 3px;
		overflow: hidden;
	}
	.oc-bar-fill {
		height: 100%;
		border-radius: 3px;
		transition: width 0.6s ease;
	}
	.oc-bar-fill.attestation { background: #60a5fa; }
	.oc-bar-fill.validation  { background: #a78bfa; }
	.oc-bar-fill.reputation  { background: #34d399; }
	.oc-bar-fill.trades      { background: #fbbf24; }
	.oc-bar-fill.trades.warn { background: #f97316; }

	.oc-label {
		font-size: 0.68rem;
		color: #64748b;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	/* ── Decision distribution ─────────────────────────────────────── */

	.dist-bar {
		display: flex;
		border-radius: 6px;
		overflow: hidden;
		height: 28px;
		margin-bottom: 0.6rem;
	}
	.dist-segment {
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.72rem;
		font-weight: 600;
		color: #000;
		min-width: 4px;
		transition: width 0.4s ease;
	}
	.dist-segment.buy  { background: #10b981; }
	.dist-segment.sell { background: #ef4444; }
	.dist-segment.hold { background: #475569; color: #cbd5e1; }

	.dist-legend {
		display: flex;
		gap: 1.2rem;
		font-size: 0.75rem;
		color: #94a3b8;
	}
	.dot {
		display: inline-block;
		width: 8px;
		height: 8px;
		border-radius: 50%;
		margin-right: 0.35rem;
		vertical-align: middle;
	}
	.dot.buy  { background: #10b981; }
	.dot.sell { background: #ef4444; }
	.dot.hold { background: #475569; }

	/* ── Holdings ──────────────────────────────────────────────────── */

	.holdings-grid {
		display: flex;
		gap: 1.5rem;
	}
	.holding {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}
	.holding-asset {
		font-size: 0.72rem;
		font-weight: 600;
		color: #94a3b8;
		text-transform: uppercase;
	}
	.holding-value { font-size: 1rem; color: #f1f5f9; }
	.holding-usd  { font-size: 0.72rem; color: #475569; }

	/* ── Collapsible sections ──────────────────────────────────────── */

	.section {
		background: #111827;
		border: 1px solid #1e293b;
		border-radius: 10px;
		overflow: hidden;
	}

	.section-toggle {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		width: 100%;
		padding: 0.85rem 1.15rem;
		background: none;
		border: none;
		color: #e2e8f0;
		cursor: pointer;
		text-align: left;
		transition: background 0.15s;
	}
	.section-toggle:hover { background: #1e293b33; }

	.chevron {
		font-size: 1.1rem;
		color: #475569;
		transition: transform 0.2s;
		display: inline-block;
		width: 14px;
		text-align: center;
	}
	.chevron.open { transform: rotate(90deg); }

	.section-title {
		font-weight: 600;
		font-size: 0.88rem;
	}
	.section-meta {
		font-size: 0.73rem;
		color: #475569;
		font-family: 'JetBrains Mono', monospace;
		margin-left: auto;
	}

	.section-body {
		padding: 0 1.15rem 1.15rem;
	}

	.run-btn-inline {
		background: #2563eb;
		color: #fff;
		border: none;
		padding: 0.3rem 0.85rem;
		border-radius: 5px;
		font-size: 0.78rem;
		font-weight: 500;
		cursor: pointer;
		margin-left: 0.5rem;
		transition: background 0.15s;
		white-space: nowrap;
	}
	.run-btn-inline:hover:not(:disabled) { background: #1d4ed8; }
	.run-btn-inline:disabled { opacity: 0.5; cursor: wait; }

	/* ── Pipeline internals ────────────────────────────────────────── */

	.pipeline-summary {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding-bottom: 0.75rem;
		border-bottom: 1px solid #1e293b;
		margin-bottom: 0.5rem;
	}

	.decision-badge {
		color: #000;
		font-weight: 700;
		font-size: 0.75rem;
		padding: 0.2rem 0.6rem;
		border-radius: 4px;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}
	.decision-badge.sm { font-size: 0.68rem; padding: 0.12rem 0.45rem; }

	.meta { color: #64748b; font-size: 0.78rem; }

	.stage-card {
		margin-top: 0.6rem;
		background: #0d1320;
		border: 1px solid #1e293b;
		border-radius: 6px;
		padding: 0.85rem;
	}
	.stage-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.4rem;
	}
	.stage-name { font-weight: 600; font-size: 0.88rem; }
	.stage-meta { font-size: 0.72rem; color: #64748b; }

	.tool-toggle {
		background: none;
		border: none;
		color: #60a5fa;
		font-size: 0.78rem;
		cursor: pointer;
		padding: 0.15rem 0;
	}
	.tool-toggle:hover { color: #93c5fd; }

	.tool-list { display: flex; flex-direction: column; gap: 0.35rem; margin: 0.4rem 0; }
	.tool-call {
		background: #0a0e17;
		border: 1px solid #1e293b;
		border-radius: 4px;
		padding: 0.45rem 0.65rem;
		font-size: 0.76rem;
	}
	.tool-name { display: flex; align-items: center; gap: 0.35rem; }
	.fn { color: #60a5fa; font-family: 'JetBrains Mono', monospace; font-weight: 600; }
	.tool-time { margin-left: auto; color: #475569; font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; }
	.tool-result { color: #64748b; font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; margin-top: 0.2rem; word-break: break-all; }

	.stage-response {
		margin-top: 0.4rem;
		font-size: 0.82rem;
		line-height: 1.55;
		color: #cbd5e1;
		white-space: pre-wrap;
	}
	.error-text { color: #fca5a5; }

	/* ── History list ──────────────────────────────────────────────── */

	.history-list { display: flex; flex-direction: column; gap: 0.2rem; }

	.history-row {
		display: flex;
		align-items: center;
		gap: 0.7rem;
		background: #0d1320;
		border: 1px solid #1e293b;
		border-radius: 6px;
		padding: 0.55rem 0.85rem;
		cursor: pointer;
		width: 100%;
		text-align: left;
		color: #e2e8f0;
		transition: border-color 0.15s;
	}
	.history-row:hover { border-color: #334155; }

	.history-time { font-size: 0.78rem; color: #94a3b8; }

	.history-detail {
		background: #0a0e17;
		border: 1px solid #1e293b;
		border-top: none;
		border-radius: 0 0 6px 6px;
		padding: 0.65rem;
		margin-top: -0.2rem;
		margin-bottom: 0.2rem;
	}
	.stage-mini {
		padding: 0.4rem 0;
		border-bottom: 1px solid #1e293b22;
	}
	.stage-mini:last-child { border-bottom: none; }
	.stage-name-sm { font-weight: 600; font-size: 0.8rem; }
	.stage-response-sm {
		font-size: 0.76rem;
		color: #94a3b8;
		margin-top: 0.25rem;
		white-space: pre-wrap;
		max-height: 100px;
		overflow-y: auto;
	}

	/* ── Table ──────────────────────────────────────────────────────── */

	table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
	th { text-align: left; color: #64748b; font-weight: 500; padding: 0.45rem 0; border-bottom: 1px solid #1e293b; }
	td { padding: 0.45rem 0; border-bottom: 1px solid #1e293b0a; }

	.empty { color: #334155; font-size: 0.82rem; padding: 0.5rem 0; }

	/* ── Responsive ────────────────────────────────────────────────── */

	@media (max-width: 700px) {
		.stats { grid-template-columns: 1fr 1fr; }
		.oc-grid { grid-template-columns: 1fr 1fr; }
		.holdings-grid { flex-direction: column; gap: 0.75rem; }
		.header-meta { display: none; }
	}

	@media (max-width: 420px) {
		.stats { grid-template-columns: 1fr; }
		.oc-grid { grid-template-columns: 1fr; }
	}
</style>
