import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'

export default defineConfig({
  base: '/api/plugins/my115scan/fe/',
  plugins: [
    vue(),
    federation({
      name: 'movie_monitor_115_config',
      filename: 'remoteEntry.js',
      exposes: { './Config': './src/Config.vue' },
      shared: ['vue'],
    }),
  ],
  build: {
    target: 'esnext',
    minify: false,
    cssCodeSplit: false,
  },
})
