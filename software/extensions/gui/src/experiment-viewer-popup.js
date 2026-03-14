import { createApp } from 'vue'
import App from '@experiment_viewer/App.vue'

// Set title from URL params
const params = new URLSearchParams(window.location.search)
const title = params.get('title')
if (title) document.title = title

createApp(App).mount('#viewer-root')
