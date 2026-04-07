<script>
	import { api } from '$lib/api';
	import { onMount } from 'svelte';

	let stats = null;
	let error = '';
	let loading = true;

	async function refresh() {
		loading = true;
		try {
			error = '';
			stats = await api.llmStats();
		} catch (e) {
			error = e.message;
		} finally {
			loading = false;
		}
	}

	onMount(refresh);

	$: total = stats ? stats.gemini_calls + stats.mistral_calls : 0;
	$: geminiPct = total > 0 ? Math.round((stats.gemini_calls / total) * 100) : 0;
	$: mistralPct = total > 0 ? 100 - geminiPct : 0;
</script>

<div class="page">
	<div class="header">
		<h1>LLM Provider Stats</h1>
		<button class="refresh-btn" on:click={refresh}>Refresh</button>
	</div>

	{#if error}
		<div class="alert alert-error">{error}</div>
	{/if}

	{#if loading}
		<p class="loading">Loading...</p>
	{:else if stats}
		<!-- Summary cards -->
		<div class="grid-3">
			<div class="card stat-card gemini">
				<h2>Gemini</h2>
				<div class="stat-value">{stats.gemini_calls}</div>
				<div class="stat-label">calls ({geminiPct}%)</div>
			</div>
			<div class="card stat-card mistral">
				<h2>Mistral</h2>
				<div class="stat-value">{stats.mistral_calls}</div>
				<div class="stat-label">calls ({mistralPct}%)</div>
			</div>
			<div class="card stat-card fallback">
				<h2>Fallbacks</h2>
				<div class="stat-value">{stats.fallbacks}</div>
				<div class="stat-label">Gemini → Mistral</div>
			</div>
		</div>

		<!-- Usage bar -->
		<div class="card">
			<h2>Provider Split</h2>
			<div class="bar-container">
				{#if total > 0}
					<div class="bar-segment gemini-bar" style="width:{geminiPct}%">
						{#if geminiPct > 10}<span>Gemini {geminiPct}%</span>{/if}
					</div>
					<div class="bar-segment mistral-bar" style="width:{mistralPct}%">
						{#if mistralPct > 10}<span>Mistral {mistralPct}%</span>{/if}
					</div>
				{:else}
					<div class="bar-empty">No calls recorded yet</div>
				{/if}
			</div>
			<div class="bar-legend">
				<span class="legend-item"><span class="dot gemini-dot"></span> Gemini</span>
				<span class="legend-item"><span class="dot mistral-dot"></span> Mistral</span>
			</div>
		</div>

		<!-- Per-agent breakdown -->
		<div class="card">
			<h2>Calls by Agent</h2>
			<table>
				<thead>
					<tr>
						<th>Agent</th>
						<th>Gemini</th>
						<th>Mistral</th>
					</tr>
				</thead>
			<tbody>
				{#each [...new Set([
					...Object.keys(stats.by_agent.gemini || {}),
					...Object.keys(stats.by_agent.mistral || {})
				])] as agent}
					<tr>
						<td>{agent}</td>
						<td class="mono">{stats.by_agent.gemini?.[agent] ?? 0}</td>
						<td class="mono">{stats.by_agent.mistral?.[agent] ?? 0}</td>
					</tr>
				{:else}
					<tr><td colspan="3" class="empty">No per-agent data yet</td></tr>
				{/each}
			</tbody>
			</table>
		</div>

		<!-- Strategy info -->
		<div class="card info-card">
			<h2>Provider Strategy</h2>
			<p>
				Every pipeline call tries <strong>Gemini first</strong> (with key rotation and
				429 retry logic). If Gemini fails after all retries, the call automatically
				falls back to <strong>Mistral</strong>. Fallback count shows how often this happened.
			</p>
		</div>
	{/if}
</div>

<style>
	.page { display: flex; flex-direction: column; gap: 1rem; }

	.header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}
	h1 {
		font-size: 1.1rem;
		font-weight: 700;
		color: #3d2e1f;
	}
	.refresh-btn {
		padding: 0.4rem 1rem;
		border: 1px solid #e4ddd4;
		background: #fff;
		border-radius: 8px;
		font-size: 0.8rem;
		font-weight: 500;
		cursor: pointer;
		color: #6b5a48;
		transition: background 0.15s;
	}
	.refresh-btn:hover { background: #f5f0ea; }

	.alert { padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.85rem; }
	.alert-error { background: #fce8e4; border: 1px solid #e8c4bc; color: #8b3020; }
	.loading { color: #8b7a66; font-size: 0.85rem; text-align: center; padding: 2rem 0; }

	.grid-3 {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 0.75rem;
	}

	.stat-card { text-align: center; padding: 1.5rem 1rem; }
	.stat-value {
		font-family: 'JetBrains Mono', monospace;
		font-size: 2rem;
		font-weight: 700;
		margin: 0.3rem 0;
	}
	.stat-label { font-size: 0.78rem; color: #8c7a68; }

	.stat-card.gemini .stat-value { color: #2563eb; }
	.stat-card.mistral .stat-value { color: #ea580c; }
	.stat-card.fallback .stat-value { color: #8b5cf6; }

	.bar-container {
		display: flex;
		height: 36px;
		border-radius: 8px;
		overflow: hidden;
		margin: 0.75rem 0 0.5rem;
		background: #f0ebe4;
	}
	.bar-segment {
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.72rem;
		font-weight: 600;
		color: #fff;
		transition: width 0.4s ease;
	}
	.gemini-bar { background: #2563eb; }
	.mistral-bar { background: #ea580c; }
	.bar-empty {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		color: #8c7a68;
		font-size: 0.8rem;
	}

	.bar-legend {
		display: flex;
		gap: 1.2rem;
		justify-content: center;
	}
	.legend-item { display: flex; align-items: center; gap: 0.35rem; font-size: 0.78rem; color: #6b5a48; }
	.dot { width: 10px; height: 10px; border-radius: 3px; }
	.gemini-dot { background: #2563eb; }
	.mistral-dot { background: #ea580c; }

	.info-card p {
		font-size: 0.82rem;
		color: #6b5a48;
		line-height: 1.5;
		margin-top: 0.5rem;
	}

	@media (max-width: 600px) {
		.grid-3 { grid-template-columns: 1fr; }
		.stat-value { font-size: 1.5rem; }
	}
</style>
