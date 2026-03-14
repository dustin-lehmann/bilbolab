import { ref } from 'vue'

const isDark = ref(!document.documentElement.classList.contains('light'))

export function useTheme() {
    function toggle() {
        isDark.value = !isDark.value
        if (isDark.value) {
            document.documentElement.classList.remove('light')
            localStorage.setItem('theme', 'dark')
        } else {
            document.documentElement.classList.add('light')
            localStorage.setItem('theme', 'light')
        }
    }

    function setTheme(theme) {
        isDark.value = theme === 'dark'
        if (isDark.value) {
            document.documentElement.classList.remove('light')
        } else {
            document.documentElement.classList.add('light')
        }
        localStorage.setItem('theme', theme)
    }

    return { isDark, toggle, setTheme }
}
