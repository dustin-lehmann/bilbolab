import './theme.css'
import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import ExperimentList from './components/ExperimentList.vue'
import ExperimentViewer from './components/ExperimentViewer.vue'
import FolderView from './components/FolderView.vue'
import PDFViewer from './components/PDFViewer.vue'
import FigureViewer from './components/FigureViewer.vue'
import CodeViewer from './components/CodeViewer.vue'
import VideoViewer from './components/VideoViewer.vue'
import InteractiveViewer from './components/InteractiveViewer.vue'
import Model3DViewer from './components/Model3DViewer.vue'
import AdminLogin from './components/admin/AdminLogin.vue'
import AdminLayout from './components/admin/AdminLayout.vue'
import AdminDashboard from './components/admin/AdminDashboard.vue'
import AdminFolders from './components/admin/AdminFolders.vue'
import AdminSettings from './components/admin/AdminSettings.vue'
import AdminVisitors from './components/admin/AdminVisitors.vue'
import AdminItemEdit from './components/admin/AdminItemEdit.vue'

const routes = [
    { path: '/', component: ExperimentList },
    { path: '/folder/:id', component: FolderView, props: true },
    { path: '/experiment/:id', component: ExperimentViewer, props: true },
    { path: '/video/:id', component: VideoViewer, props: true },
    { path: '/pdf/:id', component: PDFViewer, props: true },
    { path: '/figures/:id', component: FigureViewer, props: true },
    { path: '/code/:id', component: CodeViewer, props: true },
    { path: '/interactive/:id', component: InteractiveViewer, props: true },
    { path: '/model3d/:id', component: Model3DViewer, props: true },
    { path: '/admin/login', component: AdminLogin, meta: { hideHeader: true } },
    {
        path: '/admin',
        component: AdminLayout,
        meta: { requiresAuth: true, hideHeader: true },
        children: [
            { path: '', component: AdminDashboard },
            { path: 'folders', component: AdminFolders },
            { path: 'folders/:id', component: AdminFolders, props: true },
            { path: 'edit/:id', component: AdminItemEdit, props: true },
            { path: 'visitors', component: AdminVisitors },
            { path: 'settings', component: AdminSettings },
        ]
    }
]

const router = createRouter({
    history: createWebHistory(),
    routes
})

// Navigation guard for admin routes
router.beforeEach((to, from, next) => {
    if (to.matched.some(r => r.meta.requiresAuth)) {
        const token = localStorage.getItem('admin_token')
        if (!token) {
            next('/admin/login')
            return
        }
    }
    next()
})

// Restore theme before mount to avoid flash
const savedTheme = localStorage.getItem('theme')
if (savedTheme === 'light') {
    document.documentElement.classList.add('light')
}

const app = createApp(App)
app.use(router)
app.mount('#app')
