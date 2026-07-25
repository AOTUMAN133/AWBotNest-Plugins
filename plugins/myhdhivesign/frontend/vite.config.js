// vite.config.js
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'

export default defineConfig({
  base: '/api/plugins/myhdhivesign/fe/',
  plugins: [
    vue(),
    federation({
      name: 'myhdhivesign',
      filename: 'remoteEntry.js',
      exposes: { './Config': './src/Config.vue' },
      shared: ['vue'],
    }),
  ],
  build: {
    target: 'esnext',
    cssCodeSplit: false,
  },
})