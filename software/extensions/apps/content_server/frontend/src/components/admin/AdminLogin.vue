<template>
    <div class="login-page">
        <div class="login-card">
            <h1 class="login-title">Admin Login</h1>
            <form @submit.prevent="handleLogin">
                <div class="form-group">
                    <input
                        type="password"
                        v-model="password"
                        placeholder="Password"
                        class="input"
                        autofocus
                        :disabled="loading"
                    >
                </div>
                <div v-if="error" class="error">{{ error }}</div>
                <button type="submit" class="btn btn-primary" :disabled="loading || !password">
                    {{ loading ? 'Logging in...' : 'Login' }}
                </button>
            </form>
        </div>
    </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../../composables/useAuth.js'

const router = useRouter()
const { login } = useAuth()
const password = ref('')
const error = ref('')
const loading = ref(false)

async function handleLogin() {
    error.value = ''
    loading.value = true
    try {
        await login(password.value)
        router.push('/admin')
    } catch (e) {
        error.value = e.message
    } finally {
        loading.value = false
    }
}
</script>

<style scoped>
.login-page {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 80vh;
}
.login-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 40px;
    width: 100%;
    max-width: 380px;
}
.login-title {
    font-size: 24px;
    font-weight: 600;
    margin-bottom: 24px;
    text-align: center;
}
.form-group {
    margin-bottom: 16px;
}
.input {
    width: 100%;
    padding: 12px 16px;
    background: var(--bg-elevated);
    border: 1px solid var(--border-light);
    border-radius: 8px;
    color: var(--text-primary);
    font-size: 14px;
    outline: none;
    box-sizing: border-box;
}
.input:focus {
    border-color: #3b82f6;
}
.error {
    color: #f87171;
    font-size: 13px;
    margin-bottom: 12px;
}
.btn {
    width: 100%;
    padding: 12px;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
}
.btn-primary {
    background: #3b82f6;
    color: white;
}
.btn-primary:hover:not(:disabled) {
    background: #2563eb;
}
.btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}
</style>
