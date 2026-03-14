import { createApp } from 'vue'
import DesignerWidget from '@experiment_designer/DesignerWidget.vue'

window.addEventListener('DOMContentLoaded', () => {
    const params = new URLSearchParams(window.location.search)
    const widgetId = params.get('widget_id') || 'experiment_designer'
    const title = params.get('title') || 'Experiment Designer'

    document.title = title

    // Unique instance ID for this popup
    const popupInstanceId = `popup_${widgetId}_${Math.random().toString(36).slice(2, 10)}`

    // Load initial state from sessionStorage
    const storageKey = `experiment_designer_popup_${widgetId}`
    let initialState = null
    let initialConfig = {}
    try {
        const raw = sessionStorage.getItem(storageKey)
        if (raw) {
            const stored = JSON.parse(raw)
            initialState = stored.state || null
            initialConfig = stored.config || {}
            sessionStorage.removeItem(storageKey)
        }
    } catch { /* ignore parse errors */ }

    const root = document.getElementById('designer-root')

    // BroadcastChannel for bidirectional communication with the main widget
    const channel = new BroadcastChannel(`experiment_designer_${widgetId}`)

    const app = createApp(DesignerWidget, {
        darkMode: initialConfig.dark_mode !== false,
        showToolbar: initialConfig.show_toolbar !== false,
        showYamlPreview: !!initialConfig.show_yaml_preview,
        showExperimentTabs: !!initialConfig.show_experiment_tabs,
        readOnly: !!initialConfig.read_only,
        actionLibrary: initialConfig.action_library || null,
        transparent: false,  // never transparent in popup — it has its own window
        instanceId: popupInstanceId,
        onPlay(yaml) {
            channel.postMessage({ type: 'play', yaml })
        },
        onStop() {
            channel.postMessage({ type: 'stop' })
        },
        onMutation(mutation) {
            // Forward mutation to main widget (which forwards to Python)
            channel.postMessage({ type: 'mutation', mutation })
        },
    })

    const instance = app.mount(root)

    // Restore full graph state if available
    if (initialState) {
        instance.restoreFullState(initialState)
    }

    channel.onmessage = (e) => {
        const msg = e.data
        if (!msg || !msg.type) return

        switch (msg.type) {
            case 'mutation':
                // Remote mutation from main widget (originated from Python or main widget)
                if (msg.mutation) {
                    instance.applyRemoteMutation(msg.mutation)
                }
                break
            case 'update':
                // Legacy update messages (mode, yaml, action_states, full_state)
                if (msg.data.full_state) {
                    instance.applyFullState(msg.data.full_state)
                }
                if (msg.data.mode !== undefined) {
                    instance.setMode(msg.data.mode)
                }
                if (msg.data.yaml !== undefined) {
                    instance.loadExperiment(msg.data.yaml)
                }
                if (msg.data.action_states) {
                    for (const [actionId, state] of Object.entries(msg.data.action_states)) {
                        instance.setActionState(actionId, state)
                    }
                }
                if (msg.data.clear_action_states) {
                    instance.clearActionStates()
                }
                break
            case 'close':
                window.close()
                break
        }
    }

    // Forward delegated file operation events to main widget via BroadcastChannel
    window.addEventListener('designer-send-event', (e) => {
        const { event, data } = e.detail || {}
        if (event && data) {
            channel.postMessage({ type: 'file_event', event, data })
        }
    })

    // Notify main window that popup is ready
    channel.postMessage({ type: 'popup_ready' })

    // Notify main window when popup is closed
    window.addEventListener('beforeunload', () => {
        channel.postMessage({ type: 'popup_closed' })
    })
})
