<script>
	import { createEventDispatcher } from 'svelte';
	import { decisionColor, formatDateTime, stageIcon, truncateResult } from '$lib/utils';

	export let run;

	const dispatch = createEventDispatcher();

	function close() {
		dispatch('close');
	}

	function handleKeydown(e) {
		if (e.key === 'Escape') close();
	}
</script>

<svelte:window on:keydown={handleKeydown} />

<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
<div class="modal-backdrop" on:click={close}>
	<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
	<div class="modal" on:click|stopPropagation>
		<div class="modal-header">
			<div>
				<span class="decision-badge" style="background:{decisionColor(run.decision)}">{run.decision}</span>
				<span class="modal-time">{formatDateTime(run.timestamp)}</span>
				<span class="modal-duration">{run.total_duration_ms}ms</span>
			</div>
			<button class="modal-close" on:click={close}>&times;</button>
		</div>
		<div class="modal-body">
			{#each run.stages as stage, i}
				<details open={i === 0}>
					<summary>
						<span class="stage-icon">{stageIcon(stage.agent)}</span>
						<span class="stage-name">{stage.agent}</span>
						<span class="stage-dur">{stage.duration_ms}ms</span>
					</summary>
					<div class="stage-content">
						{#if stage.response}
							<div class="stage-response">{stage.response}</div>
						{/if}
						{#if stage.tool_calls && stage.tool_calls.length > 0}
							<div class="tool-calls">
								<h4>Tool calls</h4>
								{#each stage.tool_calls as tc}
									<div class="tool-call">
										<code>{tc.name}({JSON.stringify(tc.args || {})})</code>
										{#if tc.result}
											<pre>{truncateResult(tc.result, 600)}</pre>
										{/if}
									</div>
								{/each}
							</div>
						{/if}
					</div>
				</details>
			{/each}
		</div>
	</div>
</div>

<style>
	.modal-backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0,0,0,0.45);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: 1.5rem;
	}
	.modal {
		background: #fff;
		border-radius: 14px;
		box-shadow: 0 20px 60px rgba(0,0,0,0.2);
		width: 100%;
		max-width: 720px;
		max-height: 85vh;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}
	.modal-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 1rem 1.25rem;
		border-bottom: 1px solid #ece6de;
		gap: 0.6rem;
	}
	.modal-header > div {
		display: flex;
		align-items: center;
		gap: 0.6rem;
	}
	.modal-time {
		font-size: 0.82rem;
		color: #6b5a48;
	}
	.modal-duration {
		font-size: 0.75rem;
		color: #9a8c7c;
		font-family: 'SF Mono', 'Fira Code', monospace;
	}
	.modal-close {
		background: none;
		border: none;
		font-size: 1.6rem;
		cursor: pointer;
		color: #8b7a66;
		line-height: 1;
		padding: 0 0.2rem;
	}
	.modal-close:hover { color: #3d2e1f; }

	.modal-body {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		padding: 1rem 1.25rem;
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
	}

	details {
		border: 1px solid #ece6de;
		border-radius: 10px;
		overflow: clip;
	}
	summary {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.65rem 0.9rem;
		background: #faf7f3;
		cursor: pointer;
		font-size: 0.85rem;
		font-weight: 500;
		color: #3d2e1f;
		user-select: none;
	}
	summary:hover { background: #f5f0ea; }
	.stage-icon { font-size: 1.05rem; }
	.stage-name { flex: 1; }
	.stage-dur {
		font-size: 0.72rem;
		color: #9a8c7c;
		font-family: 'SF Mono', 'Fira Code', monospace;
	}

	.stage-content {
		padding: 0.75rem 0.9rem;
		font-size: 0.82rem;
		line-height: 1.55;
		color: #3d2e1f;
	}
	.stage-response {
		white-space: pre-wrap;
		word-break: break-word;
		max-height: 300px;
		overflow-y: auto;
		background: #faf7f3;
		border-radius: 8px;
		padding: 0.7rem;
		margin-bottom: 0.5rem;
	}

	.tool-calls {
		max-height: 300px;
		overflow-y: auto;
	}
	.tool-calls h4 {
		font-size: 0.75rem;
		color: #8b7a66;
		margin: 0 0 0.4rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}
	.tool-call {
		margin-bottom: 0.5rem;
	}
	.tool-call code {
		display: block;
		font-size: 0.75rem;
		background: #f0ebe4;
		padding: 0.35rem 0.5rem;
		border-radius: 5px;
		overflow-x: auto;
		color: #6b5a48;
	}
	.tool-call pre {
		font-size: 0.72rem;
		background: #faf7f3;
		padding: 0.35rem 0.5rem;
		border-radius: 5px;
		margin: 0.25rem 0 0;
		overflow-x: auto;
		color: #8b7a66;
		max-height: 150px;
		overflow-y: auto;
	}

	@media (max-width: 600px) {
		.modal { max-width: 100%; }
	}
</style>
