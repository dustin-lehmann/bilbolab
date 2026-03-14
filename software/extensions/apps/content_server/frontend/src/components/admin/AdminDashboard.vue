<template>
    <div class="dashboard">
        <h1 class="page-title">Dashboard</h1>
        <div class="stats-grid" v-if="stats">
            <div class="stat-card">
                <div class="stat-value">{{ stats.folders }}</div>
                <div class="stat-label">Folders</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ stats.items }}</div>
                <div class="stat-label">Items</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ stats.drafts }}</div>
                <div class="stat-label">Drafts</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ stats.files }}</div>
                <div class="stat-label">Files</div>
            </div>
        </div>
        <div v-else class="loading">Loading...</div>
    </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useApi } from '../../composables/useApi.js'

const { adminGet } = useApi()
const stats = ref(null)

function countTree(data) {
    let folders = 0, items = 0, drafts = 0, files = 0
    function walk(folderList) {
        for (const folder of folderList) {
            folders++
            if (folder.draft) drafts++
            for (const exp of (folder.experiments || [])) {
                items++
                if (exp.draft) drafts++
                const type = exp.type || 'synchronized'
                if (type === 'synchronized' || type === 'collection') files += (exp.videos || []).length
                else if (type === 'figures') files += (exp.figures || []).length
                else if (type === 'pdf' || type === 'code') files += 1
            }
            walk(folder.folders || [])
        }
    }
    walk(data.folders || [])
    return { folders, items, drafts, files }
}

onMounted(async () => {
    const data = await adminGet('/api/admin/content')
    stats.value = countTree(data)
})
</script>

<style scoped>
.page-title {
    font-size: 24px;
    font-weight: 600;
    margin-bottom: 24px;
}
.stats-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
}
.stat-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 24px;
    text-align: center;
}
.stat-value {
    font-size: 36px;
    font-weight: 700;
    color: #3b82f6;
}
.stat-label {
    color: var(--text-muted);
    font-size: 13px;
    margin-top: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.loading {
    color: var(--text-muted);
    padding: 40px;
    text-align: center;
}
</style>
