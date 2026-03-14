<template>
    <div class="admin-layout">
        <aside class="admin-sidebar">
            <div class="admin-sidebar-header">
                <router-link to="/admin" class="admin-logo">Admin Panel</router-link>
            </div>
            <nav class="admin-nav">
                <router-link to="/admin" class="admin-nav-item" exact-active-class="active">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
                    Dashboard
                </router-link>
                <router-link to="/admin/folders" class="admin-nav-item" active-class="active">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/></svg>
                    Folders & Items
                </router-link>
                <router-link to="/admin/visitors" class="admin-nav-item" active-class="active">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                    Visitors
                </router-link>
                <router-link to="/admin/settings" class="admin-nav-item" active-class="active">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                    Settings
                </router-link>
            </nav>
            <div class="admin-sidebar-footer">
                <router-link to="/" class="admin-nav-item">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
                    Back to Site
                </router-link>
                <button class="admin-nav-item logout-btn" @click="handleLogout">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                    Logout
                </button>
            </div>
        </aside>
        <main class="admin-main">
            <router-view />
        </main>
    </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useAuth } from '../../composables/useAuth.js'

const router = useRouter()
const { logout } = useAuth()

function handleLogout() {
    logout()
    router.push('/admin/login')
}
</script>

<style scoped>
.admin-layout {
    display: flex;
    height: 100%;
    overflow: hidden;
}
.admin-sidebar {
    width: 220px;
    background: var(--bg-sidebar);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
}
.admin-sidebar-header {
    padding: 20px 16px;
    border-bottom: 1px solid var(--border);
}
.admin-logo {
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
    text-decoration: none;
}
.admin-nav {
    flex: 1;
    padding: 8px 0;
    overflow-y: auto;
}
.admin-nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 16px;
    color: var(--text-muted);
    text-decoration: none;
    font-size: 13px;
    transition: all 0.15s;
    border: none;
    background: none;
    width: 100%;
    cursor: pointer;
    text-align: left;
}
.admin-nav-item:hover {
    background: var(--bg-elevated);
    color: var(--text-primary);
}
.admin-nav-item.active {
    background: var(--bg-elevated);
    color: #3b82f6;
    border-right: 2px solid #3b82f6;
}
.admin-sidebar-footer {
    border-top: 1px solid var(--border);
    padding: 8px 0;
}
.admin-main {
    flex: 1;
    overflow: auto;
    padding: 24px 32px;
    background: linear-gradient(90deg, var(--bg-page) 0%, var(--bg-header) 50%, var(--bg-page) 100%);
}
</style>
