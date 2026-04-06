<script>
	import { page } from '$app/stores';

	$: path = $page.url.pathname;
</script>

<svelte:head>
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet" />
</svelte:head>

<div class="shell">
	<nav>
		<div class="nav-left">
			<a href="/performance" class="nav-brand">AI Trading Agent</a>
			<span class="badge live">Paper Trading</span>
			<span class="badge chain">Sepolia</span>
		</div>
		<div class="nav-links">
			<a href="/performance" class:active={path === '/performance' || path === '/'}>Performance</a>
			<a href="/pipeline" class:active={path === '/pipeline'}>Pipeline</a>
			<a href="/history" class:active={path === '/history'}>History</a>
		</div>
	</nav>

	<main>
		<slot />
	</main>
</div>

<style>
	:global(*) {
		margin: 0;
		padding: 0;
		box-sizing: border-box;
	}

	:global(body) {
		font-family: 'DM Sans', sans-serif;
		background: #faf6f1;
		color: #3d2e1f;
		min-height: 100vh;
	}

	:global(code, .mono) {
		font-family: 'JetBrains Mono', monospace;
	}

	:global(.positive) { color: #2d7a4f; }
	:global(.negative) { color: #b5412a; }

	:global(.card) {
		background: #ffffff;
		border: 1px solid #e4ddd4;
		border-radius: 12px;
		padding: 1.25rem;
		box-shadow: 0 1px 3px rgba(61, 46, 31, 0.04);
	}
	:global(.card-header) {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.75rem;
	}
	:global(.card-meta) { font-size: 0.78rem; color: #8c7a68; }

	:global(h2) {
		font-size: 0.78rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: #8c7a68;
		font-weight: 600;
		margin: 0;
	}

	:global(.empty) { color: #b5a899; font-size: 0.82rem; padding: 0.5rem 0; }

	:global(.decision-badge) {
		color: #fff;
		font-weight: 700;
		font-size: 0.75rem;
		padding: 0.2rem 0.6rem;
		border-radius: 5px;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}
	:global(.decision-badge.sm) { font-size: 0.68rem; padding: 0.12rem 0.45rem; }

	:global(.meta) { color: #8c7a68; font-size: 0.78rem; }

	:global(table) { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
	:global(th) { text-align: left; color: #8c7a68; font-weight: 600; padding: 0.55rem 0.4rem; border-bottom: 2px solid #e4ddd4; }
	:global(td) { padding: 0.55rem 0.4rem; border-bottom: 1px solid #f0ebe4; }

	.shell {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
	}

	nav {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0 2rem;
		height: 64px;
		background: #ffffff;
		border-bottom: 1px solid #e4ddd4;
		position: sticky;
		top: 0;
		z-index: 100;
		box-shadow: 0 1px 4px rgba(61, 46, 31, 0.05);
	}

	.nav-left {
		display: flex;
		align-items: center;
		gap: 0.85rem;
	}

	.nav-brand {
		font-size: 1.1rem;
		font-weight: 700;
		color: #3d2e1f;
		text-decoration: none;
		letter-spacing: -0.02em;
	}

	.badge {
		padding: 0.15rem 0.55rem;
		border-radius: 5px;
		font-size: 0.65rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}
	.badge.live  { background: #d4edda; color: #2d7a4f; }
	.badge.chain { background: #e8e0f4; color: #6b4fa0; }

	.nav-links {
		display: flex;
		gap: 0.3rem;
	}

	.nav-links a {
		color: #8c7a68;
		text-decoration: none;
		font-size: 0.85rem;
		font-weight: 500;
		padding: 0.5rem 1rem;
		border-radius: 8px;
		transition: color 0.15s, background 0.15s;
	}
	.nav-links a:hover {
		color: #3d2e1f;
		background: #f5f0ea;
	}
	.nav-links a.active {
		color: #3d2e1f;
		background: #f0ebe4;
		font-weight: 600;
	}

	main {
		flex: 1;
		max-width: 1080px;
		width: 100%;
		margin: 0 auto;
		padding: 1.5rem 1.25rem 3rem;
	}

	@media (max-width: 600px) {
		nav { flex-direction: column; height: auto; padding: 0.75rem 1rem; gap: 0.5rem; }
		.nav-links a { font-size: 0.78rem; padding: 0.35rem 0.7rem; }
	}
</style>
