import { useAuth } from './useAuth.js'

export function useApi() {
    const { token, logout } = useAuth()

    async function adminFetch(url, options = {}) {
        const headers = {
            ...options.headers,
            'Authorization': `Bearer ${token.value}`
        }
        // Don't set Content-Type for FormData
        if (!(options.body instanceof FormData) && !headers['Content-Type']) {
            headers['Content-Type'] = 'application/json'
        }
        const res = await fetch(url, { ...options, headers })
        if (res.status === 401) {
            logout()
            window.location.hash = '#/admin/login'
            throw new Error('Session expired')
        }
        return res
    }

    async function adminGet(url) {
        const res = await adminFetch(url)
        return res.json()
    }

    async function adminPost(url, data) {
        const res = await adminFetch(url, {
            method: 'POST',
            body: data instanceof FormData ? data : JSON.stringify(data)
        })
        return res.json()
    }

    async function adminPut(url, data) {
        const res = await adminFetch(url, {
            method: 'PUT',
            body: JSON.stringify(data)
        })
        return res.json()
    }

    async function adminDelete(url) {
        const res = await adminFetch(url, { method: 'DELETE' })
        return res.json()
    }

    return { adminFetch, adminGet, adminPost, adminPut, adminDelete }
}
