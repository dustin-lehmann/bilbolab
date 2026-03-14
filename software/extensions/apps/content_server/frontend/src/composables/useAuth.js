import { ref, computed } from 'vue'

const token = ref(localStorage.getItem('admin_token') || '')
const isAdmin = ref(false)

// Verify on load if token exists
if (token.value) {
    fetch('/api/admin/verify', {
        headers: { 'Authorization': `Bearer ${token.value}` }
    }).then(res => {
        isAdmin.value = res.ok
        if (!res.ok) {
            token.value = ''
            localStorage.removeItem('admin_token')
        }
    }).catch(() => {
        isAdmin.value = false
    })
}

export function useAuth() {
    const isAuthenticated = computed(() => !!token.value)

    async function login(password) {
        const res = await fetch('/api/admin/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
        })
        if (!res.ok) {
            const data = await res.json()
            throw new Error(data.error || 'Login failed')
        }
        const data = await res.json()
        token.value = data.token
        localStorage.setItem('admin_token', data.token)
        isAdmin.value = true
        return data.token
    }

    function logout() {
        token.value = ''
        isAdmin.value = false
        localStorage.removeItem('admin_token')
    }

    async function verify() {
        if (!token.value) return false
        try {
            const res = await fetch('/api/admin/verify', {
                headers: { 'Authorization': `Bearer ${token.value}` }
            })
            if (!res.ok) {
                logout()
                return false
            }
            isAdmin.value = true
            return true
        } catch {
            logout()
            return false
        }
    }

    return { token, isAuthenticated, isAdmin, login, logout, verify }
}
