import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';
// import commonjs from '@rollup/plugin-commonjs';
// import * as path from "node:path";

// ESM-compatible equivalent of __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const rollupInputs = {
    main: resolve(__dirname, 'src/main.js'),
};


export default defineConfig({
    base: '/static/',

    root: resolve(__dirname, 'src'),

    plugins: [
        tailwindcss(),
    ],

    css: {
        devSourcemap: true,
    },

    server: {
        host: '0.0.0.0',
        port: 5173,
        open: false,
        watch: {
            usePolling: true,
            disableGlobbing: false,
        },
        hmr: false,
        cors: true,
        origin: 'http://localhost:5173'
    },

    resolve: {
        extensions: ['.js', '.json', '.scss', '.css'],
    },

    build: {
        sourcemap: false,
        outDir: resolve(__dirname, 'build'),
        assetsDir: '',
        manifest: 'manifest.json',
        emptyOutDir: true,
        target: 'es2017',
        rollupOptions: {
            input: rollupInputs,
            output: {
                chunkFileNames: undefined,
            },
        },
    },
});
