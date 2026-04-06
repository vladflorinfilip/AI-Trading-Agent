<script>
	import { api } from '$lib/api';
	import { slide } from 'svelte/transition';
	import { decisionColor, stageIcon, truncateResult } from '$lib/utils';

	let pipelineResult = null;
	let pipelineLoading = false;
	let expandedTools = {};

	async function runPipeline() {
		pipelineLoading = true;
		pipelineResult = null;
		expandedTools = {};
		try {
			pipelineResult = await api.runPipeline(
				'Analyse the market and trade if you see an opportunity.'
			);
		} catch (e) {
			pipelineResult = { error: e.message };
		} finally {
			pipelineLoading = false;
		}
	}

	function toggleTools(i) {
		expandedTools[i] = !expandedTools[i];
		expandedTools = expandedTools;
	}
</script>

<div class="page">
	<!-- Architecture explanation -->
	<div class="card arch-card">
		<h2>Pipeline Architecture</h2>
		<p class="arch-desc">
			The agent runs a three-stage multi-agent pipeline. Each stage is powered by Google Gemini
			with access to Kraken CLI tools. The risk manager gates every trade before execution.
		</p>

		<div class="diagram">
			<div class="dia-node market">
				<div class="dia-icon">📡</div>
				<div class="dia-label">Market Data</div>
				<div class="dia-sub">Kraken OHLC + Ticker + Orderbook</div>
			</div>
			<div class="dia-arrow">→</div>
			<div class="dia-node analyst">
				<div class="dia-icon">📊</div>
				<div class="dia-label">Analyst</div>
				<div class="dia-sub">RSI, MACD, Bollinger, ATR<br/>computed locally, not by LLM</div>
			</div>
			<div class="dia-arrow">→</div>
			<div class="dia-node trader">
				<div class="dia-icon">💹</div>
				<div class="dia-label">Trader</div>
				<div class="dia-sub">Proposes BUY / SELL / HOLD<br/>with position sizing</div>
			</div>
			<div class="dia-arrow">→</div>
			<div class="dia-node risk">
				<div class="dia-icon">🛡️</div>
				<div class="dia-label">Risk Manager</div>
				<div class="dia-sub">APPROVE / RESIZE / VETO<br/>before execution</div>
			</div>
			<div class="dia-arrow">→</div>
			<div class="dia-node execute">
				<div class="dia-icon">⚡</div>
				<div class="dia-label">Execute</div>
				<div class="dia-sub">Paper trade via Kraken CLI<br/>+ on-chain checkpoint</div>
			</div>
		</div>

		<div class="features">
			<div class="feature">
				<span class="feature-tag">Local TA</span>
				Technical indicators (RSI, MACD, Bollinger, ATR) are computed in Python, not by the LLM. The model interprets accurate numbers instead of doing arithmetic.
			</div>
			<div class="feature">
				<span class="feature-tag">Risk Gate</span>
				The risk manager runs before execution and can veto or resize trades that exceed portfolio concentration or volatility limits.
			</div>
			<div class="feature">
				<span class="feature-tag">PnL Journal</span>
				Open positions are tracked locally. When a trade closes a position, realized PnL is computed and posted on-chain as a verifiable attestation.
			</div>
		</div>
	</div>

	<!-- Run pipeline -->
	<div class="card">
		<div class="card-header">
			<h2>Run Pipeline</h2>
			<button class="run-btn" on:click={runPipeline} disabled={pipelineLoading}>
				{pipelineLoading ? 'Running...' : 'Run Pipeline'}
			</button>
		</div>

		{#if pipelineResult && !pipelineResult.error}
			<div class="pipeline-summary">
				<span class="decision-badge" style="background:{decisionColor(pipelineResult.decision)}">
					{pipelineResult.decision}
				</span>
				<span class="meta">{pipelineResult.total_duration_ms}ms total</span>
				{#if pipelineResult.amount_usd}
					<span class="meta">${pipelineResult.amount_usd.toFixed(2)}</span>
				{/if}
				{#if pipelineResult.atr}
					<span class="meta">ATR: ${pipelineResult.atr.toFixed(2)}</span>
				{/if}
			</div>

			{#each pipelineResult.stages as stage, i}
				<div class="stage-card">
					<div class="stage-header">
						<span class="stage-name">{stageIcon(stage.agent)} {stage.agent}</span>
						<span class="stage-meta mono">
							{stage.tool_calls.length} tool{stage.tool_calls.length !== 1 ? 's' : ''} · {stage.duration_ms}ms
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
		{:else if !pipelineLoading}
			<p class="empty">Click "Run Pipeline" to execute the multi-agent trading pipeline</p>
		{:else}
			<div class="loading">
				<div class="spinner"></div>
				<span>Running Analyst → Trader → Risk Manager...</span>
			</div>
		{/if}
	</div>
</div>

<style>
	.page { display: flex; flex-direction: column; gap: 0.85rem; }

	.arch-desc {
		font-size: 0.85rem;
		color: #6b5a48;
		line-height: 1.55;
		margin: 0.5rem 0 1rem;
	}

	.diagram {
		display: flex;
		align-items: flex-start;
		gap: 0;
		overflow-x: auto;
		padding: 0.5rem 0 1rem;
	}
	.dia-node {
		flex: 1;
		min-width: 120px;
		background: #faf6f1;
		border: 1px solid #e4ddd4;
		border-radius: 10px;
		padding: 0.75rem 0.65rem;
		text-align: center;
		transition: border-color 0.2s, box-shadow 0.2s;
	}
	.dia-node:hover { border-color: #c4b8aa; box-shadow: 0 2px 8px rgba(61,46,31,0.08); }
	.dia-node.analyst { border-color: #b8cfe0; }
	.dia-node.risk    { border-color: #d4c4e4; }
	.dia-node.execute { border-color: #b8dcc4; }
	.dia-icon { font-size: 1.4rem; margin-bottom: 0.3rem; }
	.dia-label { font-weight: 600; font-size: 0.82rem; color: #3d2e1f; margin-bottom: 0.2rem; }
	.dia-sub { font-size: 0.68rem; color: #8c7a68; line-height: 1.4; }
	.dia-arrow { color: #b5a899; font-size: 1.3rem; padding: 1rem 0.3rem 0; flex-shrink: 0; }

	.features {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 0.75rem;
		margin-top: 0.25rem;
	}
	.feature {
		font-size: 0.78rem;
		color: #6b5a48;
		line-height: 1.55;
		padding: 0.75rem;
		background: #faf6f1;
		border-radius: 8px;
		border: 1px solid #e4ddd4;
	}
	.feature-tag {
		display: inline-block;
		font-weight: 600;
		font-size: 0.68rem;
		color: #7a5c2e;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		margin-bottom: 0.25rem;
	}

	.run-btn {
		background: #7a5c2e;
		color: #fff;
		border: none;
		padding: 0.5rem 1.4rem;
		border-radius: 8px;
		font-size: 0.82rem;
		font-weight: 600;
		cursor: pointer;
		transition: background 0.15s;
	}
	.run-btn:hover:not(:disabled) { background: #5e4520; }
	.run-btn:disabled { opacity: 0.5; cursor: wait; }

	.pipeline-summary {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding-bottom: 0.75rem;
		border-bottom: 1px solid #e4ddd4;
		margin-bottom: 0.5rem;
	}

	.stage-card {
		margin-top: 0.6rem;
		background: #faf6f1;
		border: 1px solid #e4ddd4;
		border-radius: 8px;
		padding: 0.85rem;
	}
	.stage-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem; }
	.stage-name { font-weight: 600; font-size: 0.88rem; color: #3d2e1f; }
	.stage-meta { font-size: 0.72rem; color: #8c7a68; }

	.tool-toggle { background: none; border: none; color: #7a5c2e; font-size: 0.78rem; cursor: pointer; padding: 0.15rem 0; font-weight: 500; }
	.tool-toggle:hover { color: #5e4520; }

	.tool-list { display: flex; flex-direction: column; gap: 0.35rem; margin: 0.4rem 0; }
	.tool-call { background: #ffffff; border: 1px solid #e4ddd4; border-radius: 6px; padding: 0.45rem 0.65rem; font-size: 0.76rem; }
	.tool-name { display: flex; align-items: center; gap: 0.35rem; }
	.fn { color: #7a5c2e; font-family: 'JetBrains Mono', monospace; font-weight: 600; }
	.tool-time { margin-left: auto; color: #8c7a68; font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; }
	.tool-result { color: #8c7a68; font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; margin-top: 0.2rem; word-break: break-all; }

	.stage-response { margin-top: 0.4rem; font-size: 0.82rem; line-height: 1.55; color: #4a3b2c; white-space: pre-wrap; }
	.error-text { color: #b5412a; }

	.loading {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 1.5rem 0;
		color: #8c7a68;
		font-size: 0.85rem;
	}
	.spinner {
		width: 18px;
		height: 18px;
		border: 2px solid #e4ddd4;
		border-top-color: #7a5c2e;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}
	@keyframes spin { to { transform: rotate(360deg); } }

	@media (max-width: 700px) {
		.diagram { flex-wrap: wrap; gap: 0.5rem; }
		.dia-arrow { display: none; }
		.dia-node { min-width: 0; flex: 1 1 calc(50% - 0.5rem); }
		.features { grid-template-columns: 1fr; }
	}
</style>
