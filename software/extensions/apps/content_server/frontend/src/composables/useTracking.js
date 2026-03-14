/**
 * Visitor tracking composable.
 * Tracks page views and time spent on public pages.
 * Uses sendBeacon for reliable unload tracking.
 */
import { onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'

function getVisitorId() {
    const KEY = 'visitor_id'
    let id = localStorage.getItem(KEY)
    if (!id) {
        id = crypto.randomUUID?.() || (Math.random().toString(36).slice(2) + Date.now().toString(36))
        localStorage.setItem(KEY, id)
    }
    return id
}

export function useTracking() {
    const route = useRoute()
    const vid = getVisitorId()
    let startTime = null
    let currentPath = null
    let currentTitle = null

    function sendView(path, title) {
        fetch('/api/track', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'view', path, title, vid }),
        }).catch(() => {})
    }

    function sendLeave(path, duration) {
        const data = JSON.stringify({ action: 'leave', path, duration: Math.round(duration), vid })
        // Try sendBeacon first (works on page unload), fall back to fetch
        if (navigator.sendBeacon) {
            navigator.sendBeacon('/api/track', new Blob([data], { type: 'application/json' }))
        } else {
            fetch('/api/track', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: data, keepalive: true }).catch(() => {})
        }
    }

    function recordLeave() {
        if (currentPath && startTime) {
            const duration = (Date.now() - startTime) / 1000
            if (duration >= 1) {
                sendLeave(currentPath, duration)
            }
        }
    }

    function startTracking(path) {
        // Skip admin routes
        if (path.startsWith('/admin')) return

        recordLeave()
        currentPath = path
        currentTitle = document.title
        startTime = Date.now()
        sendView(path, currentTitle)
    }

    function handleVisibilityChange() {
        if (document.hidden) {
            recordLeave()
        } else if (currentPath) {
            // Resume tracking
            startTime = Date.now()
        }
    }

    function handleBeforeUnload() {
        recordLeave()
    }

    onMounted(() => {
        startTracking(route.path)
        document.addEventListener('visibilitychange', handleVisibilityChange)
        window.addEventListener('beforeunload', handleBeforeUnload)
    })

    onUnmounted(() => {
        recordLeave()
        document.removeEventListener('visibilitychange', handleVisibilityChange)
        window.removeEventListener('beforeunload', handleBeforeUnload)
    })

    watch(() => route.path, (newPath) => {
        startTracking(newPath)
    })
}
