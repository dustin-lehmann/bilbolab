<template>
    <div class="visitors-page">
        <div class="page-header">
            <h1 class="page-title">Visitors</h1>
            <div class="header-actions">
                <select v-model="days" class="input input-sm days-select" @change="loadVisitors">
                    <option :value="7">Last 7 days</option>
                    <option :value="30">Last 30 days</option>
                    <option :value="90">Last 90 days</option>
                    <option :value="365">Last year</option>
                    <option :value="9999">All time</option>
                </select>
                <button class="btn btn-ghost" @click="loadVisitors">Refresh</button>
                <button class="btn btn-danger-sm" @click="confirmClear" v-if="visitors.length">Clear Log</button>
            </div>
        </div>

        <div class="stats-row" v-if="visitors.length">
            <div class="stat-card">
                <div class="stat-value">{{ visitors.length }}</div>
                <div class="stat-label">Unique Visitors</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ totalViews }}</div>
                <div class="stat-label">Total Page Views</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ formatDuration(totalDuration) }}</div>
                <div class="stat-label">Total Time Spent</div>
            </div>
        </div>

        <div v-if="loading" class="loading-state">Loading visitor data...</div>

        <div v-else-if="visitors.length === 0" class="empty-state">
            No visitor data recorded yet.
        </div>

        <div v-else class="visitors-list">
            <div v-for="visitor in visitors" :key="visitor.vid" class="visitor-card"
                 :class="{ expanded: expandedIps.has(visitor.vid) }">
                <div class="visitor-header" @click="toggleVisitor(visitor.vid)">
                    <div class="visitor-info">
                        <svg class="expand-icon" :class="{ open: expandedIps.has(visitor.vid) }"
                             width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                            <polyline points="9 18 15 12 9 6"/>
                        </svg>
                        <div class="visitor-id">Visitor {{ visitor.vid.slice(0, 8) }}</div>
                        <div class="visitor-badge">{{ parseBrowser(visitor.userAgent) }}</div>
                        <div class="visitor-ips" v-if="visitor.ips && visitor.ips.length">{{ visitor.ips.join(', ') }}</div>
                    </div>
                    <div class="visitor-meta">
                        <span class="meta-item">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                            {{ visitor.totalViews }} views
                        </span>
                        <span class="meta-item">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
                            {{ formatDuration(visitor.totalDuration) }}
                        </span>
                        <span class="meta-item last-seen">
                            Last: {{ formatTime(visitor.lastSeen) }}
                        </span>
                    </div>
                </div>

                <div v-if="expandedIps.has(visitor.vid)" class="visitor-views">
                    <table class="views-table">
                        <thead>
                            <tr>
                                <th class="sortable-th" @click="toggleViewSort(visitor.vid, 'page')"
                                    :class="{ active: getViewSort(visitor.vid).key === 'page' }">
                                    Page <span class="sort-arrow" v-if="getViewSort(visitor.vid).key === 'page'">{{ getViewSort(visitor.vid).dir === 1 ? '↑' : '↓' }}</span>
                                </th>
                                <th class="sortable-th" @click="toggleViewSort(visitor.vid, 'time')"
                                    :class="{ active: getViewSort(visitor.vid).key === 'time' }">
                                    Time <span class="sort-arrow" v-if="getViewSort(visitor.vid).key === 'time'">{{ getViewSort(visitor.vid).dir === 1 ? '↑' : '↓' }}</span>
                                </th>
                                <th class="sortable-th" @click="toggleViewSort(visitor.vid, 'duration')"
                                    :class="{ active: getViewSort(visitor.vid).key === 'duration' }">
                                    Duration <span class="sort-arrow" v-if="getViewSort(visitor.vid).key === 'duration'">{{ getViewSort(visitor.vid).dir === 1 ? '↑' : '↓' }}</span>
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr v-for="(view, i) in getSortedViews(visitor)" :key="i">
                                <td class="view-path">
                                    <span class="path-text">{{ view.title || view.path }} <span class="visits-badge" v-if="view.visits > 1">{{ view.visits }}×</span></span>
                                    <span class="path-sub" v-if="view.title">{{ view.path }}</span>
                                </td>
                                <td class="view-time">{{ formatTime(view.timestamp) }}</td>
                                <td class="view-duration">{{ view.duration ? formatDuration(view.duration) : '-' }}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useApi } from '../../composables/useApi.js'

const { adminGet, adminPost } = useApi()

const visitors = ref([])
const loading = ref(true)
const days = ref(30)
const expandedIps = reactive(new Set())
const viewSorts = reactive({}) // { vid: { key: 'time', dir: -1 } }

const totalViews = computed(() => visitors.value.reduce((s, v) => s + v.totalViews, 0))
const totalDuration = computed(() => visitors.value.reduce((s, v) => s + v.totalDuration, 0))

function getViewSort(vid) {
    return viewSorts[vid] || { key: 'time', dir: -1 }
}

function toggleViewSort(vid, key) {
    const current = getViewSort(vid)
    if (current.key === key) {
        viewSorts[vid] = { key, dir: current.dir * -1 }
    } else {
        viewSorts[vid] = { key, dir: key === 'page' ? 1 : -1 }
    }
}

function getSortedViews(visitor) {
    if (!visitor.views || !visitor.views.length) return []
    // Aggregate by page: sum duration, keep most recent timestamp, count visits
    const byPage = {}
    for (const v of visitor.views) {
        if (v.path === '/' || (!v.path && !v.title)) continue
        const pageKey = v.path || v.title
        if (!byPage[pageKey]) {
            byPage[pageKey] = { title: v.title, path: v.path, duration: 0, timestamp: v.timestamp, visits: 0 }
        }
        byPage[pageKey].duration += (v.duration || 0)
        byPage[pageKey].visits++
        if (v.timestamp && (!byPage[pageKey].timestamp || new Date(v.timestamp) > new Date(byPage[pageKey].timestamp))) {
            byPage[pageKey].timestamp = v.timestamp
        }
    }
    const arr = Object.values(byPage)
    const { key, dir } = getViewSort(visitor.vid)
    arr.sort((a, b) => {
        if (key === 'page') {
            const pa = (a.title || a.path || '').toLowerCase()
            const pb = (b.title || b.path || '').toLowerCase()
            return dir * pa.localeCompare(pb)
        } else if (key === 'time') {
            const ta = a.timestamp ? new Date(a.timestamp).getTime() : 0
            const tb = b.timestamp ? new Date(b.timestamp).getTime() : 0
            return dir * (ta - tb)
        } else if (key === 'duration') {
            return dir * ((a.duration || 0) - (b.duration || 0))
        }
        return 0
    })
    return arr
}

async function loadVisitors() {
    loading.value = true
    try {
        const data = await adminGet(`/api/admin/visitors?days=${days.value}`)
        visitors.value = data.visitors || []
    } catch (e) {
        console.error('Failed to load visitors:', e)
    }
    loading.value = false
}

function toggleVisitor(ip) {
    if (expandedIps.has(ip)) {
        expandedIps.delete(ip)
    } else {
        expandedIps.add(ip)
    }
}

async function confirmClear() {
    if (!confirm('Clear all visitor tracking data? This cannot be undone.')) return
    await adminPost('/api/admin/visitors/clear')
    visitors.value = []
}

function formatDuration(seconds) {
    if (!seconds || seconds < 1) return '0s'
    if (seconds < 60) return Math.round(seconds) + 's'
    if (seconds < 3600) return Math.round(seconds / 60) + 'm'
    const h = Math.floor(seconds / 3600)
    const m = Math.round((seconds % 3600) / 60)
    return h + 'h ' + m + 'm'
}

function formatTime(iso) {
    if (!iso) return ''
    const d = new Date(iso)
    const now = new Date()
    const diffMs = now - d
    const diffH = diffMs / (1000 * 60 * 60)

    if (diffH < 1) return Math.round(diffMs / (1000 * 60)) + 'm ago'
    if (diffH < 24) return Math.round(diffH) + 'h ago'

    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) +
        ' ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}

function parseBrowser(ua) {
    if (!ua) return 'Unknown'
    if (ua.includes('Firefox')) return 'Firefox'
    if (ua.includes('Edg/')) return 'Edge'
    if (ua.includes('Chrome')) return 'Chrome'
    if (ua.includes('Safari')) return 'Safari'
    if (ua.includes('bot') || ua.includes('Bot') || ua.includes('crawl')) return 'Bot'
    return 'Other'
}

onMounted(loadVisitors)
</script>

<style scoped>
.visitors-page { max-width: 960px; }

.page-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 20px; flex-wrap: wrap; gap: 12px;
}
.page-title { font-size: 24px; font-weight: 600; }
.header-actions { display: flex; gap: 8px; align-items: center; }

.days-select { width: auto; padding: 6px 10px; font-size: 12px; background: var(--code-bg); border: 1px solid var(--border-light); border-radius: 7px; color: var(--text-secondary); cursor: pointer; }

.btn {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 6px 14px; border: none; border-radius: 7px;
    font-size: 12px; font-weight: 500; cursor: pointer; transition: all 0.15s;
}
.btn-ghost { background: transparent; color: var(--text-muted); border: 1px solid var(--border-light); }
.btn-ghost:hover { background: var(--bg-elevated); color: var(--text-secondary); border-color: var(--border-hover); }
.btn-danger-sm { background: #dc2626; color: white; padding: 6px 12px; }
.btn-danger-sm:hover { background: #b91c1c; }

.input-sm { padding: 6px 10px; font-size: 12px; }

/* Stats */
.stats-row { display: flex; gap: 12px; margin-bottom: 20px; }
.stat-card {
    flex: 1; background: var(--bg-sidebar); border: 1px solid var(--bg-card-hover);
    border-radius: 10px; padding: 16px 20px; text-align: center;
}
.stat-value { font-size: 28px; font-weight: 700; color: var(--text-primary); }
.stat-label { font-size: 11px; color: var(--text-faint); margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }

/* Visitors list */
.loading-state, .empty-state { padding: 48px; text-align: center; color: var(--text-faint); font-size: 14px; }

.visitor-card {
    background: var(--bg-sidebar); border: 1px solid var(--bg-card-hover);
    border-radius: 10px; margin-bottom: 8px; overflow: hidden;
    transition: border-color 0.15s;
}
.visitor-card.expanded { border-color: var(--border); }
.visitor-card:hover { border-color: var(--border); }

.visitor-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 14px 18px; cursor: pointer; transition: background 0.1s;
    flex-wrap: wrap; gap: 8px;
}
.visitor-header:hover { background: var(--bg-elevated); }

.visitor-info { display: flex; align-items: center; gap: 10px; }
.expand-icon { color: var(--text-faint); transition: transform 0.15s; flex-shrink: 0; }
.expand-icon.open { transform: rotate(90deg); }
.visitor-id { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.visitor-ips { font-size: 11px; color: var(--text-faint); font-family: monospace; }
.visitor-badge {
    font-size: 10px; font-weight: 600; padding: 2px 8px;
    border-radius: 4px; background: rgba(59,130,246,0.12); color: #60a5fa;
    text-transform: uppercase; letter-spacing: 0.3px;
}

.visitor-meta { display: flex; gap: 16px; align-items: center; }
.meta-item {
    display: flex; align-items: center; gap: 4px;
    font-size: 12px; color: var(--text-faint);
}
.last-seen { color: var(--text-faint); }

/* Views table */
.visitor-views {
    border-top: 1px solid var(--bg-card-hover);
    padding: 0;
}
.views-table {
    width: 100%; border-collapse: collapse; font-size: 13px;
}
.views-table th {
    text-align: left; padding: 8px 18px; font-size: 11px;
    color: var(--text-faint); font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.3px; border-bottom: 1px solid var(--bg-card-hover);
}
.sortable-th {
    cursor: pointer; user-select: none; transition: color 0.15s;
}
.sortable-th:hover { color: var(--text-secondary); }
.sortable-th.active { color: var(--accent); }
.sort-arrow { font-size: 11px; }
.views-table td { padding: 8px 18px; border-bottom: 1px solid var(--bg-card-hover); }
.views-table tr:last-child td { border-bottom: none; }
.views-table tr:hover td { background: var(--bg-card); }

.view-path { max-width: 400px; }
.path-text { color: var(--text-secondary); display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.path-sub { color: var(--border-hover); font-size: 11px; font-family: monospace; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.visits-badge {
    font-size: 10px; font-weight: 600; color: var(--text-faint);
    background: var(--bg-button); padding: 1px 5px; border-radius: 4px;
    margin-left: 4px; vertical-align: middle;
}
.view-time { color: var(--text-faint); white-space: nowrap; }
.view-duration { color: var(--text-muted); white-space: nowrap; }
</style>
