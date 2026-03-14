import {Widget} from "../objects.js";

// Inject popout button styles once
if (!document.getElementById('experiment-viewer-widget-styles')) {
    const style = document.createElement('style');
    style.id = 'experiment-viewer-widget-styles';
    style.textContent = `
        .experiment-viewer-popout-btn {
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
        .experiment-viewer-popout-btn:hover {
            background: rgba(255, 255, 255, 0.15);
            color: rgba(255, 255, 255, 0.9);
        }
        .experiment-viewer-popout-btn:active {
            opacity: 0.6;
        }
        .experiment-viewer-popout-btn svg {
            width: 100%;
            height: 100%;
        }
    `;
    document.head.appendChild(style);
}

export class ExperimentViewerWidget extends Widget {
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

        this._instanceId = `viewer_${id}_${Math.random().toString(36).slice(2, 10)}`;

        this._popupWindow = null;
        this._popupChannel = null;
    }

    initializeElement() {
        const element = document.createElement('div');
        element.id = this.id;
        element.classList.add('widget', 'experiment-viewer-widget');
        element.style.width = '100%';
        element.style.height = '100%';
        element.style.overflow = 'hidden';
        element.style.display = 'flex';
        element.style.flexDirection = 'column';
        element.style.alignItems = 'stretch';
        element.style.position = 'relative';
        return element;
    }

    async onFirstShow() {
        const [{ createApp }, { default: ViewerWidget }] = await Promise.all([
            import('vue'),
            import('@experiment_viewer/ViewerWidget.vue'),
        ]);

        const self = this;
        const darkMode = this.configuration.dark_mode !== false;

        this._vueApp = createApp(ViewerWidget, {
            darkMode,
            transparent: !!this.configuration.transparent,
            instanceId: this._instanceId,
            onFileLoaded(name) {
                self._sendEvent('file_loaded', { name });
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

        // Replay pending updates
        for (const data of this._pendingUpdates) {
            this.update(data);
        }
        this._pendingUpdates = [];

        this._createPopoutButton();
    }

    _createPopoutButton() {
        const btn = document.createElement('button');
        btn.className = 'experiment-viewer-popout-btn';
        btn.title = 'Pop Out';
        btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>`;
        this.element.appendChild(btn);
        btn.addEventListener('click', () => this._popOut());
    }

    _popOut() {
        if (this._popupWindow && !this._popupWindow.closed) {
            this._popupWindow.focus();
            return;
        }

        const url = new URL('/experiment-viewer-popup.html', window.location.origin);
        url.searchParams.set('widget_id', this.id);
        url.searchParams.set('title', 'Experiment Viewer');
        this._popupWindow = window.open(url.href, '_blank', 'width=1400,height=900,resizable=yes');
    }

    _sendEvent(eventName, data) {
        this.callbacks.get('event').call({
            id: this.id,
            event: eventName,
            data: data,
        });
    }

    resize() {
        // Vue handles its own resizing
    }

    update(data) {
        if (!this._vueInstance) {
            this._pendingUpdates.push(data);
            return;
        }

        if (data.experiment_data) {
            this._vueInstance.loadData(data.experiment_data, data.file_name || '');
        }
        if (data.clear) {
            this._vueInstance.clear();
        }
    }

    updateConfig(data) {
        // No runtime config updates needed
    }

    destroy() {
        if (this._popupWindow && !this._popupWindow.closed) {
            this._popupWindow.close();
        }
        if (this._vueApp) {
            this._vueApp.unmount();
            this._vueApp = null;
            this._vueInstance = null;
        }
        super.destroy();
    }

    loadData(jsonData, fileName) {
        if (this._vueInstance) this._vueInstance.loadData(jsonData, fileName);
    }

    clear() {
        if (this._vueInstance) this._vueInstance.clear();
    }
}
