import { ref, watch } from 'vue'

const viewMode = ref(localStorage.getItem('contentViewMode') || 'grid')

watch(viewMode, (val) => {
    localStorage.setItem('contentViewMode', val)
})

export function useViewMode() {
    function toggle() {
        viewMode.value = viewMode.value === 'grid' ? 'list' : 'grid'
    }
    return { viewMode, toggle }
}
