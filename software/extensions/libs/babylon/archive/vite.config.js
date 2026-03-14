import {defineConfig} from 'vite';
import { resolve } from 'path';

// If you installed the Babylon plugin, uncomment:
// import babylonPlugin from '@babylonjs/dev-vite-plugin';

export default defineConfig({
    root: 'src',      // only if you kept index.html in src/
    publicDir: 'lib/assets',
    resolve: {
        alias: {
            '@gui': resolve(__dirname, '../gui/')
        }
    },
    plugins: [
        // babylonPlugin()
    ],
    server: {
        fs: {
            allow: [
                '..', // allows parent folder access
                resolve(__dirname, '../gui/') // specifically allows folder B
            ],
        },
    },
    build: {
        outDir: '../dist'  // so build goes into dist/ next to public/
    }
});
