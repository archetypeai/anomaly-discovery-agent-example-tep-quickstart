import tailwindcss from '@tailwindcss/vite';
// adapter-node, not adapter-auto: the Docker web image serves the built app
// with `node build`, and adapter-auto resolves to a platform adapter only on a
// known host (Vercel, Netlify, ...) — on a plain container it falls back to a
// build that cannot be served. Native `vite dev` does not care either way.
import adapter from '@sveltejs/adapter-node';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	// 5180 is the app's fixed port. strictPort makes a clash FAIL rather than silently
	// drift to 5178 — an unpinned vite lands on whatever is free, which is how
	// this demo came to answer on a port its own README did not name.
	server: { port: 5180, strictPort: true },
	preview: { port: 5180, strictPort: true },
	plugins: [
		tailwindcss(),
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) => filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			// adapter-auto only supports some environments, see https://svelte.dev/docs/kit/adapter-auto for a list.
			// If your environment is not supported, or you settled on a specific environment, switch out the adapter.
			// See https://svelte.dev/docs/kit/adapters for more information about adapters.
			adapter: adapter()
		})
	]
});
