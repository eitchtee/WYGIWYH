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
        port: parseInt(process.env.VITE_DEV_SERVER_PORT || '5173'),
        open: false,
        watch: {
            usePolling: true,
            disableGlobbing: false,
        },
        hmr: false,
        cors: true,
        origin: `http://${process.env.VITE_DEV_SERVER_HOST || 'localhost'}:${process.env.VITE_DEV_SERVER_PORT || '5173'}`
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
        chunkSizeWarningLimit: 800,
        rollupOptions: {
            input: rollupInputs,
            output: {
                chunkFileNames: undefined,
                manualChunks(id) {
                    if (!id.includes('node_modules')) {
                        return;
                    }

                    if (id.includes('/chart.js/') || id.includes('/chartjs-chart-sankey/')) {
                        return 'vendor-chart';
                    }

                    if (id.includes('/mathjs/')) {
                        return 'vendor-math';
                    }

                    if (
                        id.includes('/alpinejs/') ||
                        id.includes('/@alpinejs/') ||
                        id.includes('/htmx.org/') ||
                        id.includes('/hyperscript.org/')
                    ) {
                        return 'vendor-interaction';
                    }

                    if (
                        id.includes('/bootstrap/') ||
                        id.includes('/@popperjs/') ||
                        id.includes('/sweetalert2/') ||
                        id.includes('/tippy.js/') ||
                        id.includes('/tom-select/') ||
                        id.includes('/air-datepicker/')
                    ) {
                        return 'vendor-ui';
                    }
                },
            },
        },
    },
});
