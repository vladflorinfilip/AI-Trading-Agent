import adapter from '@sveltejs/adapter-auto';
import adapterStatic from '@sveltejs/adapter-static';

const isDocker = process.env.DOCKER === '1';

export default {
	kit: {
		adapter: isDocker
			? adapterStatic({ fallback: 'index.html' })
			: adapter()
	}
};
