<svelte:head>
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
</svelte:head>

<slot />

<style>
	:global(*) {
		margin: 0;
		padding: 0;
		box-sizing: border-box;
	}

	:global(body) {
		font-family: 'Inter', sans-serif;
		background: #0a0e17;
		color: #e2e8f0;
		min-height: 100vh;
	}

	:global(code, .mono) {
		font-family: 'JetBrains Mono', monospace;
	}
</style>
