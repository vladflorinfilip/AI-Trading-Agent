<script>
	import { api } from '$lib/api';
	import { onMount } from 'svelte';
	import { fmt$, fmtPct, fmtPnl, formatTimestamp, formatTime, timeAgo, niceStep } from '$lib/utils';

	let ticker = null;
	let portfolio = null;
	let performance = null;
	let onchain = null;
	let error = '';

	let chartContainer;
	let chartW = 800;
	let hoverIdx = -1;
	const chartH = 220;
	const pad = { top: 24, right: 16, bottom: 32, left: 64 };

	async function refresh() {
		try {
			error = '';
			const results = await Promise.allSettled([
				api.ticker('BTC/USD'),
				api.portfolio(),
				api.performance(),
				api.onchain(),
			]);
			if (results[0].status === 'fulfilled') ticker = results[0].value;
			if (results[1].status === 'fulfilled') portfolio = results[1].value;
			if (results[2].status === 'fulfilled') performance = results[2].value;
			if (results[3].status === 'fulfilled') onchain = results[3].value;
		} catch (e) {
			error = e.message;
		}
	}

	onMount(() => {
		refresh();
		const interval = setInterval(refresh, 30000);
		return () => clearInterval(interval);
	});

	$: ocHasData = onchain && onchain.timestamp > 0;
	$: ocTradesPct = ocHasData && onchain.maxTradesPerHour > 0
		? Math.min((onchain.tradesThisHour / onchain.maxTradesPerHour) * 100, 100) : 0;

	$: chartData = portfolio?.pnl_series || [];
	$: startBal = portfolio?.starting_balance || 10000;
	$: pnlPositive = (portfolio?.pnl || 0) >= 0;
	$: accentColor = pnlPositive ? '#2d7a4f' : '#b5412a';

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

	$: decisions = performance?.decisions || { BUY: 0, SELL: 0, HOLD: 0 };
	$: totalDecisions = (decisions.BUY || 0) + (decisions.SELL || 0) + (decisions.HOLD || 0);
	$: buyPct  = totalDecisions ? (decisions.BUY  / totalDecisions) * 100 : 0;
	$: sellPct = totalDecisions ? (decisions.SELL / totalDecisions) * 100 : 0;
	$: holdPct = totalDecisions ? (decisions.HOLD / totalDecisions) * 100 : 0;
</script>

<div class="page">
	{#if error}
		<div class="alert alert-error">{error}</div>
	{/if}

	{#if performance?.last_run}
		<p class="last-run">Last pipeline run: {formatTime(performance.last_run)}</p>
	{/if}

	<div class="stats">
		<div class="stat-card">
			<span class="stat-label">Portfolio Value</span>
			{#if portfolio}
				<span class="stat-value">{fmt$(portfolio.total_value)}</span>
				<span class="stat-sub">Started at {fmt$(portfolio.starting_balance)}</span>
			{:else}<span class="stat-value dim">--</span>{/if}
		</div>
		<div class="stat-card">
			<span class="stat-label">P&L</span>
			{#if portfolio}
				<span class="stat-value" class:positive={portfolio.pnl >= 0} class:negative={portfolio.pnl < 0}>{fmtPnl(portfolio.pnl)}</span>
				<span class="stat-sub" class:positive={portfolio.pnl >= 0} class:negative={portfolio.pnl < 0}>{fmtPct(portfolio.pnl_pct)}</span>
			{:else}<span class="stat-value dim">--</span>{/if}
		</div>
		<div class="stat-card">
			<span class="stat-label">BTC / USD</span>
			{#if ticker}
				<span class="stat-value">${parseFloat(ticker.c?.[0] || '0').toLocaleString()}</span>
				<span class="stat-sub">Ask {parseFloat(ticker.a?.[0] || '0').toLocaleString()} · Bid {parseFloat(ticker.b?.[0] || '0').toLocaleString()}</span>
			{:else}<span class="stat-value dim">--</span>{/if}
		</div>
		<div class="stat-card">
			<span class="stat-label">Trades</span>
			{#if portfolio}
				<span class="stat-value">{portfolio.trade_count}</span>
				<span class="stat-sub"><span class="positive">{portfolio.buy_count} buy</span> · <span class="negative">{portfolio.sell_count} sell</span></span>
			{:else}<span class="stat-value dim">--</span>{/if}
		</div>
	</div>

	<!-- On-chain -->
	<div class="card">
		<div class="card-header">
			<h2>On-Chain Status</h2>
			{#if ocHasData}
				<span class="card-meta">Agent #{onchain.agentId} · Sepolia · Updated {timeAgo(onchain.timestamp)}</span>
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

	<!-- PnL chart -->
	<div class="card">
		<div class="card-header">
			<h2>Portfolio Performance</h2>
			{#if portfolio}
				<span class="card-meta mono" class:positive={pnlPositive} class:negative={!pnlPositive}>{fmtPnl(portfolio.pnl)} ({fmtPct(portfolio.pnl_pct)})</span>
			{/if}
		</div>
		<div class="chart-wrap" bind:this={chartContainer} bind:clientWidth={chartW}>
			{#if chartData.length > 0}
				<svg viewBox="0 0 {chartW} {chartH}" preserveAspectRatio="none" class="chart-svg" role="img" aria-label="Portfolio performance chart" on:mousemove={onChartMove} on:mouseleave={() => hoverIdx = -1}>
					<defs>
						<linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
							<stop offset="0%" stop-color={accentColor} stop-opacity="0.15" />
							<stop offset="100%" stop-color={accentColor} stop-opacity="0.02" />
						</linearGradient>
					</defs>
					{#each yTicks as v}
						<line x1={pad.left} y1={sy(v)} x2={chartW - pad.right} y2={sy(v)} stroke="#e4ddd4" stroke-width="1" />
						<text x={pad.left - 8} y={sy(v) + 4} fill="#8c7a68" font-size="11" text-anchor="end" font-family="'JetBrains Mono', monospace">${Math.round(v).toLocaleString()}</text>
					{/each}
					<line x1={pad.left} y1={startBalY} x2={chartW - pad.right} y2={startBalY} stroke="#b5a899" stroke-width="1" stroke-dasharray="6,4" />
					<path d={areaPath} fill="url(#areaGrad)" />
					<path d={linePath} fill="none" stroke={accentColor} stroke-width="2.5" stroke-linejoin="round" />
					{#each xTicks as d}
						<text x={sx(d.ts)} y={chartH - 6} fill="#8c7a68" font-size="10" text-anchor="middle" font-family="'JetBrains Mono', monospace">{formatTimestamp(d.ts)}</text>
					{/each}
					{#if hoverPoint}
						<line x1={hoverX} y1={pad.top} x2={hoverX} y2={pad.top + plotH} stroke="#8c7a68" stroke-width="1" stroke-dasharray="3,3" />
						<circle cx={hoverX} cy={hoverY} r="4.5" fill={accentColor} stroke="#fff" stroke-width="2" />
					{/if}
				</svg>
				{#if hoverPoint}
					<div class="chart-tooltip" style="left: {Math.min(hoverX, chartW - 160)}px; top: {Math.max(hoverY - 60, 0)}px">
						<div class="tooltip-value" class:positive={hoverPoint.value >= startBal} class:negative={hoverPoint.value < startBal}>{fmt$(hoverPoint.value)}</div>
						<div class="tooltip-meta">{fmtPnl(hoverPoint.value - startBal)} · {formatTimestamp(hoverPoint.ts)}</div>
					</div>
				{/if}
			{:else}
				<div class="chart-empty">Collecting data -- chart appears after the first few ticks</div>
			{/if}
		</div>
	</div>

	<!-- Decision distribution -->
	{#if performance && performance.total_runs > 0}
		<div class="card">
			<div class="card-header">
				<h2>Decision Distribution</h2>
				<span class="card-meta">{performance.total_runs} pipeline runs · avg {performance.avg_duration_ms}ms</span>
			</div>
			<div class="dist-bar">
				{#if buyPct > 0}<div class="dist-segment buy" style="width:{buyPct}%">{#if buyPct > 12}<span>BUY {decisions.BUY}</span>{/if}</div>{/if}
				{#if sellPct > 0}<div class="dist-segment sell" style="width:{sellPct}%">{#if sellPct > 12}<span>SELL {decisions.SELL}</span>{/if}</div>{/if}
				{#if holdPct > 0}<div class="dist-segment hold" style="width:{holdPct}%">{#if holdPct > 12}<span>HOLD {decisions.HOLD}</span>{/if}</div>{/if}
			</div>
			<div class="dist-legend">
				<span><i class="dot buy"></i> Buy {decisions.BUY} ({buyPct.toFixed(0)}%)</span>
				<span><i class="dot sell"></i> Sell {decisions.SELL} ({sellPct.toFixed(0)}%)</span>
				<span><i class="dot hold"></i> Hold {decisions.HOLD} ({holdPct.toFixed(0)}%)</span>
			</div>
		</div>
	{/if}

	<!-- Holdings -->
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
						<span class="holding-usd">{fmt$(portfolio.btc_balance * portfolio.btc_price)}</span>
					</div>
				{/if}
				{#if portfolio.eth_balance > 0}
					<div class="holding">
						<span class="holding-asset">ETH</span>
						<span class="holding-value mono">{portfolio.eth_balance.toFixed(6)}</span>
						<span class="holding-usd">{fmt$(portfolio.eth_balance * portfolio.eth_price)}</span>
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	.page { display: flex; flex-direction: column; gap: 0.85rem; }
	.last-run { font-size: 0.75rem; color: #8c7a68; text-align: right; }

	.alert { padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.85rem; }
	.alert-error { background: #fce8e4; border: 1px solid #e8c4bc; color: #8b3020; }

	.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; }

	.stat-card {
		background: #ffffff;
		border: 1px solid #e4ddd4;
		border-radius: 12px;
		padding: 1rem 1.1rem;
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		box-shadow: 0 1px 3px rgba(61, 46, 31, 0.04);
	}
	.stat-label { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; color: #8c7a68; font-weight: 600; }
	.stat-value { font-family: 'JetBrains Mono', monospace; font-size: 1.45rem; font-weight: 600; color: #3d2e1f; line-height: 1.2; }
	.stat-value.dim { color: #c4b8aa; }
	.stat-sub { font-size: 0.75rem; color: #8c7a68; }

	.oc-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1.2rem; }
	.oc-metric { display: flex; flex-direction: column; gap: 0.3rem; }
	.oc-value { font-family: 'JetBrains Mono', monospace; font-size: 1.3rem; font-weight: 600; color: #3d2e1f; line-height: 1.2; }
	.oc-max { font-size: 0.78rem; font-weight: 400; color: #8c7a68; }
	.oc-bar-track { height: 6px; background: #f0ebe4; border-radius: 3px; overflow: hidden; }
	.oc-bar-fill { height: 100%; border-radius: 3px; transition: width 0.6s ease; }
	.oc-bar-fill.attestation { background: #5b8db8; }
	.oc-bar-fill.validation  { background: #8b6db5; }
	.oc-bar-fill.reputation  { background: #4a9e6f; }
	.oc-bar-fill.trades      { background: #c8943e; }
	.oc-bar-fill.trades.warn { background: #c06a2e; }
	.oc-label { font-size: 0.68rem; color: #8c7a68; text-transform: uppercase; letter-spacing: 0.04em; }

	.chart-wrap { position: relative; width: 100%; height: 220px; }
	.chart-svg { width: 100%; height: 100%; }
	.chart-empty { display: flex; align-items: center; justify-content: center; height: 100%; color: #b5a899; font-size: 0.85rem; }
	.chart-tooltip { position: absolute; pointer-events: none; background: #ffffff; border: 1px solid #e4ddd4; border-radius: 8px; padding: 0.45rem 0.7rem; z-index: 10; box-shadow: 0 2px 8px rgba(61,46,31,0.1); }
	.tooltip-value { font-family: 'JetBrains Mono', monospace; font-size: 0.9rem; font-weight: 600; }
	.tooltip-meta { font-size: 0.7rem; color: #8c7a68; font-family: 'JetBrains Mono', monospace; }

	.dist-bar { display: flex; border-radius: 8px; overflow: hidden; height: 30px; margin-bottom: 0.6rem; }
	.dist-segment { display: flex; align-items: center; justify-content: center; font-size: 0.72rem; font-weight: 600; color: #fff; min-width: 4px; transition: width 0.4s ease; }
	.dist-segment.buy  { background: #2d7a4f; }
	.dist-segment.sell { background: #b5412a; }
	.dist-segment.hold { background: #8c7a68; }
	.dist-legend { display: flex; gap: 1.2rem; font-size: 0.75rem; color: #6b5a48; }
	.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 0.35rem; vertical-align: middle; }
	.dot.buy  { background: #2d7a4f; }
	.dot.sell { background: #b5412a; }
	.dot.hold { background: #8c7a68; }

	.holdings-grid { display: flex; gap: 1.5rem; margin-top: 0.5rem; }
	.holding { display: flex; flex-direction: column; gap: 0.15rem; }
	.holding-asset { font-size: 0.72rem; font-weight: 600; color: #8c7a68; text-transform: uppercase; }
	.holding-value { font-size: 1rem; color: #3d2e1f; }
	.holding-usd  { font-size: 0.72rem; color: #8c7a68; }

	@media (max-width: 700px) {
		.stats { grid-template-columns: 1fr 1fr; }
		.oc-grid { grid-template-columns: 1fr 1fr; }
		.holdings-grid { flex-direction: column; gap: 0.75rem; }
	}
	@media (max-width: 420px) {
		.stats { grid-template-columns: 1fr; }
		.oc-grid { grid-template-columns: 1fr; }
	}
</style>
