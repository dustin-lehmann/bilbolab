import {Widget} from "../objects.js";

// Inject popout button styles once
if (!document.getElementById('experiment-designer-widget-styles')) {
    const style = document.createElement('style');
    style.id = 'experiment-designer-widget-styles';
    style.textContent = `
        .experiment-designer-popout-btn {
            position: absolute;
            top: 4px;
            right: 4px;
            z-index: 100;
            width: 22px;
            height: 22px;
            padding: 3px;
            box-sizing: border-box;
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 4px;
            cursor: pointer;
            color: rgba(200, 200, 200, 0.6);
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background 0.15s, color 0.15s;
        }
        .experiment-designer-popout-btn:hover {
            background: rgba(255, 255, 255, 0.15);
            color: rgba(255, 255, 255, 0.9);
        }
        .experiment-designer-popout-btn:active {
            opacity: 0.6;
        }
        .experiment-designer-popout-btn svg {
            width: 100%;
            height: 100%;
        }
    `;
    document.head.appendChild(style);
}

export class ExperimentDesignerWidget extends Widget {
    constructor(id, payload = {}) {
        super(id, payload);

        const default_config = {}
        this.configuration = {...default_config, ...this.configuration};

        this.element = this.initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);

        this._vueApp = null;
        this._vueInstance = null;
        this._pendingUpdates = [];
        this._beforeUnloadHandler = null;

        // Unique instance ID for mutation loop prevention
        this._instanceId = `widget_${id}_${Math.random().toString(36).slice(2, 10)}`;

        // Popout state
        this._popupWindow = null;
        this._popupChannel = null;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    initializeElement() {
        const element = document.createElement('div');
        element.id = this.id;
        element.classList.add('widget', 'experiment-designer-widget');
        element.style.width = '100%';
        element.style.height = '100%';
        element.style.overflow = 'hidden';
        // Override .widget's "display: grid; place-items: center" which
        // prevents content from stretching to fill the container.
        element.style.display = 'flex';
        element.style.flexDirection = 'column';
        element.style.alignItems = 'stretch';
        element.style.position = 'relative';
        return element;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    async onFirstShow() {
        // Dynamically import Vue and the DesignerWidget component
        const [{ createApp }, { default: DesignerWidget }] = await Promise.all([
            import('vue'),
            import('@experiment_designer/DesignerWidget.vue'),
        ]);

        const self = this;
        const darkMode = this.configuration.dark_mode !== false;
        const actionLibrary = this.configuration.action_library || null;
        const readOnly = !!this.configuration.read_only;

        this._vueApp = createApp(DesignerWidget, {
            darkMode,
            showToolbar: this.configuration.show_toolbar !== false,
            showYamlPreview: !!this.configuration.show_yaml_preview,
            showExperimentTabs: !!this.configuration.show_experiment_tabs,
            readOnly,
            actionLibrary,
            transparent: !!this.configuration.transparent,
            instanceId: this._instanceId,
            onPlay(yaml, filePath) {
                self._sendEvent('play', { yaml, file_path: filePath || null });
            },
            onStop() {
                self._sendEvent('stop', {});
            },
            onMutation(mutation) {
                // Forward mutation to Python backend
                self._sendEvent('mutation', mutation);
                // Forward mutation to popup if open
                self._forwardMutationToPopup(mutation);
            },
        });

        const container = document.createElement('div');
        container.style.flex = '1';
        container.style.minHeight = '0';
        container.style.width = '100%';
        container.style.display = 'flex';
        container.style.flexDirection = 'column';
        this.element.appendChild(container);

        this._vueInstance = this._vueApp.mount(container);

        // Replay any updates that arrived before Vue was ready
        for (const pendingData of this._pendingUpdates) {
            this.update(pendingData);
        }
        this._pendingUpdates = [];

        // Listen for template management events from the Vue DesignerCore
        this._designerSendEventHandler = (e) => {
            const { event, data } = e.detail || {};
            if (event && data) {
                this._sendEvent(event, data);
            }
        };
        window.addEventListener('designer-send-event', this._designerSendEventHandler);

        // Restore state from backend — but only if no tabs were already restored
        // from localStorage (page refresh) or module memory (widget reconnect).
        // Otherwise the Python single-graph state would overwrite the multi-tab state.
        const hasTabs = this._vueInstance.hasRestoredTabs?.()
        if (!hasTabs) {
            if (this.configuration.full_state) {
                this._vueInstance.applyFullState(this.configuration.full_state);
            } else if (this.configuration.graph_state) {
                this._vueInstance.restoreFullState(this.configuration.graph_state);
            } else if (this.configuration.loaded_yaml) {
                this._vueInstance.loadExperiment(this.configuration.loaded_yaml);
            }
        }

        // Sync state on page unload as safety net — send full state as load_state mutation
        this._beforeUnloadHandler = () => {
            if (!this._vueInstance) return;
            const state = this._vueInstance.getFullState();
            const yaml = this._vueInstance.getYaml?.() || '';
            this._sendEvent('state_changed', { state, yaml });
        };
        window.addEventListener('beforeunload', this._beforeUnloadHandler);

        // Add popout button
        this._createPopoutButton();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _createPopoutButton() {
        const btn = document.createElement('button');
        btn.className = 'experiment-designer-popout-btn';
        btn.title = 'Pop Out';
        btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>`;
        this.element.appendChild(btn);
        this._popoutButton = btn;

        btn.addEventListener('click', () => this._popOut());
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _popOut() {
        // If a popup is already open, focus it
        if (this._popupWindow && !this._popupWindow.closed) {
            this._popupWindow.focus();
            return;
        }

        // Serialize current state to sessionStorage
        const storageKey = `experiment_designer_popup_${this.id}`;
        const state = this._vueInstance ? this._vueInstance.getFullState() : null;
        sessionStorage.setItem(storageKey, JSON.stringify({
            state,
            config: this.configuration,
        }));

        // Open popup window
        const url = new URL('/experiment-designer-popup.html', window.location.origin);
        url.searchParams.set('widget_id', this.id);
        url.searchParams.set('title', 'Experiment Designer');
        this._popupWindow = window.open(url.href, '_blank', 'width=1200,height=800,resizable=yes');

        // Set up BroadcastChannel for bidirectional communication
        this._popupChannel = new BroadcastChannel(`experiment_designer_${this.id}`);
        this._popupChannel.onmessage = (e) => this._onPopupMessage(e.data);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _onPopupMessage(msg) {
        if (!msg || !msg.type) return;

        switch (msg.type) {
            case 'play':
                this._sendEvent('play', { yaml: msg.yaml, file_path: msg.file_path || null });
                break;
            case 'stop':
                this._sendEvent('stop', {});
                break;
            case 'mutation':
                // Popup sent a mutation — forward to Python and apply locally
                if (msg.mutation) {
                    this._sendEvent('mutation', msg.mutation);
                    if (this._vueInstance) {
                        this._vueInstance.applyRemoteMutation(msg.mutation);
                    }
                }
                break;
            case 'state_changed':
                this._sendEvent('state_changed', { state: msg.state, yaml: msg.yaml });
                break;
            case 'file_event':
                // Popup sent a delegated file operation — forward to Python
                if (msg.event) {
                    this._sendEvent(msg.event, msg.data || {});
                }
                break;
            case 'popup_closed':
                this._cleanupPopup();
                break;
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _forwardToPopup(data) {
        if (this._popupChannel && this._popupWindow && !this._popupWindow.closed) {
            this._popupChannel.postMessage({ type: 'update', data });
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _forwardMutationToPopup(mutation) {
        if (this._popupChannel && this._popupWindow && !this._popupWindow.closed) {
            this._popupChannel.postMessage({ type: 'mutation', mutation });
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _cleanupPopup() {
        if (this._popupChannel) {
            this._popupChannel.close();
            this._popupChannel = null;
        }
        this._popupWindow = null;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _sendEvent(eventName, data) {
        this.callbacks.get('event').call({
            id: this.id,
            event: eventName,
            data: data,
        });
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    resize() {
        // Vue handles its own resizing
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    update(data) {
        if (!this._vueInstance) {
            this._pendingUpdates.push(data);
            return;
        }

        // Handle mutation from Python (broadcast to local Vue + popup)
        if (data.mutation) {
            this._vueInstance.applyRemoteMutation(data.mutation);
            this._forwardMutationToPopup(data.mutation);
            return;
        }

        // Handle full state replacement from Python
        if (data.full_state) {
            this._vueInstance.applyFullState(data.full_state);
            this._forwardToPopup(data);
            return;
        }

        if (data.mode !== undefined) {
            this._vueInstance.setMode(data.mode);
        }
        if (data.yaml !== undefined) {
            this._vueInstance.loadExperiment(data.yaml);
        }
        if (data.action_states !== undefined) {
            for (const [actionId, state] of Object.entries(data.action_states)) {
                this._vueInstance.setActionState(actionId, state);
            }
        }
        if (data.clear_action_states) {
            this._vueInstance.clearActionStates();
        }

        // File operation responses from Python backend
        if (data.file_content) {
            this._vueInstance.loadFileContent(data.file_content.yaml, data.file_content.filename, data.file_content.file_path);
        }
        if (data.file_saved) {
            this._vueInstance.notifyFileSaved(data.file_saved.filename, data.file_saved.file_path);
        }

        // Forward all updates to popup window if open
        this._forwardToPopup(data);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    updateConfig(data) {
        // No runtime config updates needed
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    destroy() {
        // Close popup if open
        if (this._popupWindow && !this._popupWindow.closed) {
            this._popupWindow.close();
        }
        this._cleanupPopup();

        if (this._designerSendEventHandler) {
            window.removeEventListener('designer-send-event', this._designerSendEventHandler);
            this._designerSendEventHandler = null;
        }
        if (this._beforeUnloadHandler) {
            window.removeEventListener('beforeunload', this._beforeUnloadHandler);
            this._beforeUnloadHandler = null;
        }
        if (this._vueApp) {
            this._vueApp.unmount();
            this._vueApp = null;
            this._vueInstance = null;
        }
        super.destroy();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    // Direct methods callable from Python via widget.function()
    loadExperiment(yaml) {
        if (this._vueInstance) this._vueInstance.loadExperiment(yaml);
        this._forwardToPopup({ yaml });
    }

    setMode(mode) {
        if (this._vueInstance) this._vueInstance.setMode(mode);
        this._forwardToPopup({ mode });
    }

    setActionState(actionId, state) {
        if (this._vueInstance) this._vueInstance.setActionState(actionId, state);
        this._forwardToPopup({ action_states: { [actionId]: state } });
    }

    setActionStates(states) {
        if (!this._vueInstance) return;
        for (const [actionId, state] of Object.entries(states)) {
            this._vueInstance.setActionState(actionId, state);
        }
        this._forwardToPopup({ action_states: states });
    }

    clearActionStates() {
        if (this._vueInstance) this._vueInstance.clearActionStates();
        this._forwardToPopup({ clear_action_states: true });
    }

    updateTemplates(manifest) {
        // Push updated manifest to the Vue template registry
        window.dispatchEvent(new CustomEvent('designer-templates-updated', {
            detail: manifest,
        }));
    }
}
