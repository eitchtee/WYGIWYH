import {resolve, dirname} from 'path';
import {fileURLToPath} from 'url';
import {defineConfig} from 'vite';
import tailwindcss from '@tailwindcss/vite'

// ESM-compatible equivalent of __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

export default defineConfig({
    root: resolve(__dirname, 'src'),
    base: '/static/',

    plugins: [
        tailwindcss(),
    ],

    server: {
        host: 'localhost',
        port: 5173,
        open: false,
        watch: {
            usePolling: true,
            disableGlobbing: false,
        },
    },

    resolve: {
        extensions: ['.js', '.json', '.scss'],
    },

    build: {
        outDir: resolve(__dirname, '../app/static/dist'),
        assetsDir: '',
        manifest: "manifest.json",
        emptyOutDir: true,
        target: 'es2015',
        rollupOptions: {
            input: {
                // Make the input path absolute for consistency
                main: resolve(__dirname, 'src/main.js'),
            },
            output: {
                chunkFileNames: undefined,
            },
        },
    },
});
