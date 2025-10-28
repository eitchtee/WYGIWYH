import {resolve, dirname} from 'path';
import {fileURLToPath} from 'url';
import {defineConfig} from 'vite';
import tailwindcss from '@tailwindcss/vite';
// import commonjs from '@rollup/plugin-commonjs';
// import * as path from "node:path";

// ESM-compatible equivalent of __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const rollupInputs = {
    autosize: resolve(__dirname, 'src/autosize.js'),
    charts: resolve(__dirname, 'src/charts.js'),
    // datepicker: resolve(__dirname, 'src/datepicker.js'),
    bootstrap: resolve(__dirname, 'src/bootstrap.js'),
    htmx: resolve(__dirname, 'src/htmx.js'),
    select: resolve(__dirname, 'src/select.js'),
    style: resolve(__dirname, 'src/style.js'),
    sweetalert2: resolve(__dirname, 'src/sweetalert2.js'),
};


export default defineConfig({
    base: '/static/',

    root: resolve(__dirname, 'src'),

    plugins: [
        tailwindcss(),
        // commonjs()
    ],

    server: {
        host: '0.0.0.0',
        port: 5173,
        open: false,
        watch: {
            usePolling: true,
            disableGlobbing: false,
        },
        origin: 'http://localhost:5173'
    },

    resolve: {
        extensions: ['.js', '.json', '.scss', '.css'],
    },

    optimizeDeps: {
        include: ['air-datepicker', 'autosize', 'javascript-natural-sort'],
    },

    build: {
        outDir: resolve(__dirname, 'build'),
        assetsDir: '',
        manifest: 'manifest.json',
        emptyOutDir: true,
        target: 'es2015',
        rollupOptions: {
            input: rollupInputs,
            output: {
                chunkFileNames: undefined,
            },
        },
    },
});
