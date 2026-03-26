/* ================================================================================================================== */
import {Widget} from "./lib/objects/objects.js";

import {OBJECT_MAPPING} from "./lib/objects/mapping.js";
import {ButtonWidget, MultiStateButtonWidget} from "./lib/objects/js/buttons.js";
import {ClassicSliderWidget, RotaryDialWidget, SliderWidget} from "./lib/objects/js/sliders.js";
import {MultiSelectWidget} from "./lib/objects/js/select.js";
import {DigitalNumberWidget} from "./lib/objects/js/text.js";
import {Websocket} from "./lib/websocket.js";
import {Callbacks, getColor, isObject, splitPath, writeToLocalStorage, getFromLocalStorage} from "./lib/helpers.js";
import {WidgetGroup} from "./lib/objects/group.js";

const DEFAULT_APP_WEBSOCKET_PORT = 8595
const SPLASH_TIME = 250; // Time in milliseconds for the splash screen to be displayed
const WEBSOCKET_CONNECT_DELAY = 500; // Delay before connecting WebSocket (helps mobile stability)

// Make a utility function pointer that I can use for debug printing
let debugPrint = console.log.bind(console, '[App]');
let folderChange = null;
let activeApp = null;

class AppFolderButton extends ButtonWidget {

    /** @type {string | null} */
    folder = null;

    constructor(id, payload = {}) {

        const default_config = {
            'top_icon': '🗂️',
            'border_style': 'dashed',
            'border_width': 2,
        }

        payload.config = {...default_config, ...payload.config};

        super(id, payload);

        this.folder = this.configuration.folder || null;

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    handleClick() {
        if (folderChange) {
            folderChange(this.folder);
        }

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    handleDoubleClick() {

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    handleLongClick() {

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    handleRightClick() {

    }
}

// Append the FolderButton to Object Mapping
OBJECT_MAPPING['folder_button'] = AppFolderButton;

/* ================================================================================================================== */
class AppFolderPage {

    /** @type {string} */
    id;

    /** @type {integer} */
    position;

    /** @type {Object} */
    objects = {};

    /** @type {AppFolder} */
    folder = null;

    /** @type {Object} */
    config = {};

    /** @type {HTMLElement} **/
    grid = null;

    /** @type {Callbacks} */
    callbacks = null;

    constructor(id, config = {}, objects = {}) {

        this.id = id;
        this.position = config.position || 0;

        const default_config = {
            rows: 2,
            columns: 6,
            gap: 5,  // px
            radius: 4,
            fill_empty_cells: true,
        }

        this.config = {...default_config, ...config};

        this.occupied_cells = new Set();

        this.createGrid();
        this.fillGridWithPlaceholders();

        this.callbacks = new Callbacks();
        this.callbacks.add('event');


        // Build the objects from the provided objects definition
        if (Object.keys(objects).length > 0) {
            this.buildObjectsFromDefinition(objects);
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    createGrid() {
        this.grid = document.createElement('div');
        this.grid.className = 'app-content_grid';

        this.grid.style.setProperty('--content-cols', this.config.columns);
        this.grid.style.setProperty('--content-rows', this.config.rows);
        this.grid.style.gap = `${this.config.gap}px`;
        this.grid.style.borderRadius = `${this.config.radius}px`;
        // this.grid.style.aspectRatio = `${(this.config.columns + (this.config.columns - 1) * (this.config.gap / 100)) /
        // (this.config.rows + (this.config.rows - 1) * (this.config.gap / 100))}`;

        // this.grid.style.width = 'auto';
        // this.grid.style.height = '100%';
        this.grid.style.width = '100%';
        this.grid.style.height = '100%';

        this.clearGrid();
    }


    // -----------------------------------------------------------------------------------------------------------------
    fillGridWithPlaceholders() {
        // Fill the grid with placeholders
        if (!this.config.fill_empty_cells) {
            return;
        }
        let placeholder_count = 0;

        // Remove any existing placeholders
        this.grid.querySelectorAll('.app-content_grid_placeholder').forEach(el => el.remove());

        // Create placeholders in non-occupied cells
        for (let row = 1; row < this.config.rows + 1; row++) {
            for (let col = 1; col < this.config.columns + 1; col++) {
                if (!this.occupied_cells.has(`${row},${col}`)) {
                    const placeholder = document.createElement('div');
                    placeholder.className = 'app-content_grid_placeholder';
                    this.grid.appendChild(placeholder);
                    placeholder_count++;
                }
            }
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    clearGrid() {
        this.grid.innerHTML = '';
        this.occupied_cells.clear();
    }

    // -----------------------------------------------------------------------------------------------------------------
    addObject(object, row, column, width, height) {
        if (!(object instanceof Widget)) {
            console.warn('Expected a GUI_Object, got:', object);
            return;
        }

        if (!object.id) {
            console.warn('Widget must have an ID');
            return;
        }

        if (this.objects[object.id]) {
            console.warn(`Widget with ID "${object.id}" already exists in the grid.`);
            return;
        }

        if (row < 0 || column < 0 || row > this.config.rows || column > this.config.columns) {
            console.warn(`Invalid grid coordinates: row=${row}, col=${column}`);
            return;
        }

        if (row + height - 1 > this.config.rows || column + width - 1 > this.config.columns) {
            console.warn(`Invalid grid dimensions: row=${row}, col=${column}, width=${width}, height=${height}`);
        }


        const newCells = this._getOccupiedCells(row, column, width, height);

        // Check for cell conflicts
        for (const cell of newCells) {
            if (this.occupied_cells.has(cell)) {
                console.warn(`Grid cell ${cell} is already occupied. Cannot place widget "${object.id}".`);
                return;
            }
        }

        // Mark the cells as occupied
        newCells.forEach(cell => this.occupied_cells.add(cell));
        // Render the widget’s DOM and append into the main grid container
        object.attach(this.grid, [row, column], [width, height]);
        this.objects[object.id] = object;

        // Redraw the placeholders
        this.fillGridWithPlaceholders();

        object.callbacks.get('event').register(this.onEvent.bind(this));
    }

    // -----------------------------------------------------------------------------------------------------------------
    buildObjectsFromDefinition(objects) {
        for (const [id, config] of Object.entries(objects)) {
            this.buildObjectFromConfig(config);
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    buildObjectFromConfig(payload) {
        const id = payload.id;
        const type = payload.type;
        const width = payload.width;
        const height = payload.height;
        const row = payload.row;
        const col = payload.column;

        // Check if the type is in the object mapping variable
        if (!OBJECT_MAPPING[type]) {
            console.warn(`Object type "${type}" is not defined.`);
            return;
        }
        const object_class = OBJECT_MAPPING[type];
        const object = new object_class(id, payload);
        this.addObject(object, row, col, width, height);
    }

    // -----------------------------------------------------------------------------------------------------------------
    removeObject(object) {
        // Check if the object is a string
        if (typeof object === 'string') {
            // If it's a string, assume it's the ID of the object
            object = this.objects[object];
        }
        if (!(object instanceof Widget)) {
            console.warn('Expected a GUI_Object, got:', object);
            return;
        }

        // Check if the object exists in the page
        if (!this.objects[object.id]) {
            console.warn(`Object with ID "${object.id}" does not exist in this page.`);
            return;
        }

        // Remove the object from the occupied cells. We need to get the occupied cells from the object.container html element
        if (!object.container) {
            console.warn(`Object "${object.id}" does not have a container. Cannot remove.`);
            return;
        }
        // Get the row, column, width, and height from the object
        const row = parseInt(object.container.style.gridRowStart, 10);
        const col = parseInt(object.container.style.gridColumnStart, 10);
        const width = parseInt(object.container.style.gridColumnEnd.replace('span', ''), 10);
        const height = parseInt(object.container.style.gridRowEnd.replace('span', ''), 10);

        const occupiedCells = this._getOccupiedCells(row, col, width, height);
        occupiedCells.forEach(cell => this.occupied_cells.delete(cell));

        // Remove the object from the grid
        this.grid.removeChild(object.container);

        // Remove the object from the object dictionary
        delete this.objects[object.id];

        // Redraw the placeholders
        this.fillGridWithPlaceholders();
    }

    // -----------------------------------------------------------------------------------------------------------------
    // -----------------------------------------------------------------------------------------------------------------
    getObjectByPath(path) {
        const [firstSegment, remainder] = splitPath(path);

        if (!firstSegment) return null;

        const fullObjectKey = `${this.id}/${firstSegment}`;

        const object = this.objects[fullObjectKey];

        if (!object) {
            console.warn(`Object "${fullObjectKey}" not found in path "${path}".`);
            return null;
        }

        if (!remainder) {
            // If no remainder is provided, return the object itself
            return object;
        }

        if (object instanceof WidgetGroup) {
            // If the object is a group, delegate the search to it
            return object.getObjectByPath(remainder);
        } else {
            // If the object is not a group, return null as it cannot have sub-objects
            console.warn(`Object "${fullObjectKey}" is not a group and cannot have sub-objects.`);
            return null;
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _getOccupiedCells(row, col, width, height) {
        const cells = [];
        for (let r = row; r < row + height; r++) {
            for (let c = col; c < col + width; c++) {
                cells.push(`${r},${c}`);
            }
        }
        return cells;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    handleAddMessage(data) {
        const object_config = data.config;
        if (object_config) {
            this.buildObjectFromConfig(object_config)
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    handleRemoveMessage(data) {
        const object_id = data.id;
        const object = this.objects[object_id];
        if (object) {
            this.removeObject(object);
        } else {
            console.warn(`Object with ID "${object_id}" not found in this page.`);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    onEvent(event) {
        this.callbacks.get('event').call(event);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    visible(visible) {
        this.grid.style.display = visible ? 'grid' : 'none';
    }
}


/* ================================================================================================================== */
class AppFolder {

    /** @type {string} */
    id;

    /** @type {Object} */
    pages = {};

    /** @type {Object} */
    folders = {};

    /** @type {HTMLElement} **/
    container = null;

    /** @type {Object} */
    config = {};

    /** @type {Callbacks} */
    callbacks = null;


    constructor(id, container, config = {}, folders = {}, pages = {}) {
        this.id = id;
        this.container = container;

        const default_config = {}

        this.config = {...default_config, ...config};

        this.callbacks = new Callbacks();
        this.callbacks.add('event');

        this.parent = null;


        // Build initially defined pages
        if (Object.keys(pages).length > 0) {
            this.buildPagesFromConfig(pages);
        }

        // Build initially defined folders
        if (Object.keys(folders).length > 0) {
            this.buildFoldersFromConfig(folders);
        }

    }

    // -----------------------------------------------------------------------------------------------------------------
    addPage(page) {

        // Check if page id already in this.pages
        if (this.pages[page.id]) {
            console.warn(`Page with id "${page.id}" already exists in this folder.`);
            return;
        }

        // Add the page to the dict
        this.pages[page.id] = page;
        page.callbacks.get('event').register(this.onEvent.bind(this));
        page.folder = this;
        // set the page position to the length of the pages obj
        page.position = Object.keys(this.pages).length - 1;

        // Attach the pages grid to the container
        this.container.appendChild(page.grid);

        // Make the page not visible
        page.visible(false);

        // We have to update the apps page indicators
        activeApp.updatePageIndicators();
    }

    // -----------------------------------------------------------------------------------------------------------------
    buildPagesFromConfig(pages) {
        for (const [_, config] of Object.entries(pages)) {
            console.log(`Adding page from config: ${config.id}. Config:`, config);
            this.addPageFromConfig(config);
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    addPageFromConfig(config) {
        const page = new AppFolderPage(config.id,
            config.config || {},
            config.objects || {});
        this.addPage(page);
    }

    // -----------------------------------------------------------------------------------------------------------------
    removePage(page) {
        // If page is a string, get the page by id
        if (typeof page === 'string') {
            page = this.pages[page];
        }

        // Check if page is an instance of AppFolderPage
        if (!(page instanceof AppFolderPage)) {
            console.warn(`Expected an instance of AppFolderPage, got:`, page);
            return;
        }

        // Check if the page exists in this folder
        if (!this.pages[page.id]) {
            console.warn(`Page with id "${page.id}" does not exist in this folder.`);
            return;
        }

        page.grid.remove(); // Remove the page's grid from the DOM
        delete this.pages[page.id]; // Remove the page from the pages object


        // Switch the active page if it was this page
        if (activeApp.current_page === page) {
            // Set the current page to the first page in the folder
            const firstPage = this.getPageByPosition(0);
            if (firstPage) {
                activeApp.setPage(firstPage);
            } else {
                activeApp.goHome();
            }
        }

        // We have to update the apps page indicators
        activeApp.updatePageIndicators();

    }

    // -----------------------------------------------------------------------------------------------------------------
    getPageByPosition(position) {
        const page_keys = Object.keys(this.pages);
        if (position < 0 || position >= page_keys.length) {
            console.warn(`Invalid page position: ${position}`);
            return null;
        }
        return this.pages[page_keys[position]];
    }

    // -----------------------------------------------------------------------------------------------------------------
    addFolder(folder) {
        // Check if the folder already exists
        if (this.folders[folder.id]) {
            console.error(`Folder with id ${folder.id} already exists in ${this.id}`);
            return;
        }

        // Add the folder to the folder object
        this.folders[folder.id] = folder;
        folder.parent = this;
        folder.callbacks.get('event').register(this.onEvent.bind(this));
    }

    // -----------------------------------------------------------------------------------------------------------------
    addFolderFromConfig(config) {
        console.warn(`Adding folder from config: ${config.id}. Config:`, config);
        const new_folder = new AppFolder(config.id,
            this.container,
            config.config || {},
            config.folders || {},
            config.pages || {});

        this.addFolder(new_folder);
    }

    // -----------------------------------------------------------------------------------------------------------------
    buildFoldersFromConfig(folders) {
        for (const [_, config] of Object.entries(folders)) {
            console.log(`Adding folder from config: ${config.id}. Config:`, config);
            this.addFolderFromConfig(config);
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    getObjectByPath(path) {
        const [firstSegment, remainder] = splitPath(path);
        if (!firstSegment) return null;

        // Maybe I need to handle here subapps that appear as folders TODO

        const fullKey = `${this.id}/${firstSegment}`;

        // Check if it is a page
        const page = this.pages[fullKey];
        if (page) {
            if (!remainder) {
                return page;
            } else {
                return page.getObjectByPath(remainder);
            }
        }

        // Check if it is a folder
        const folder = this.folders[fullKey];
        if (folder) {
            if (!remainder) {
                return folder;
            } else {
                return folder.getObjectByPath(remainder);
            }
        }

        return null;

    }

    // -----------------------------------------------------------------------------------------------------------------
    onEvent(event) {
        this.callbacks.get('event').call(event);
    }

    // -----------------------------------------------------------------------------------------------------------------
    handleAddMessage(data) {
        const object_type = data.type

        switch (object_type) {
            case 'page':
                this.addPageFromConfig(data.config);
                break;
            case 'folder':
                console.log('Adding folder from config:', data);
                this.addFolderFromConfig(data.config)
                break;
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    handleRemoveMessage(data) {
        const object_type = data.type
        switch (object_type) {
            case 'page':
                const page_id = data.id
                const page = this.pages[page_id]
                this.removePage(page);
                break;
            case 'folder':
                const folder_id = data.id;
                const folder = this.folders[folder_id];
                if (folder) {
                    delete this.folders[folder_id];

                    // Switch the active folder if it was this folder
                    if (activeApp.current_folder === folder) {
                        // Set the current folder to the root folder
                        activeApp.setFolder(this);
                    }
                }
        }
    }
}

/* ================================================================================================================== */
export class App {

    /** @type {Websocket} */
    websocket;

    /** @type {Object} */
    popups = {}

    /** @type {string | null} */
    id;

    /** @type {AppFolder} **/
    current_folder = null;

    /** @type {AppFolderPage} **/
    current_page = null;

    /** @type {AppFolder} **/
    root_folder = null;

    isSwiping = false;
    touchStartY = 0;
    swipeThreshold = 50;

    constructor(root_container, config = {}) {

        const default_config = {}

        this.config = {...default_config, ...config};

        this.root_container = root_container;

        // Read the websocket host and port from the environment variables
        this.websocket_host = import.meta.env.VITE_WS_HOST || window.location.hostname;
        this.websocket_port = parseInt(import.meta.env.VITE_WS_PORT_APP, 10) || DEFAULT_APP_WEBSOCKET_PORT;


        this.isTerminalExpanded = false

        debugPrint = this.terminalDebug.bind(this);
        folderChange = this.setFolder.bind(this);
        activeApp = this;

        // // 1) Kick off the splash
        this.showSplash('bilbolab_logo.png', () => {
            // 2) Once done, run the normal GUI setup
            this.initializeApp();
            // 3) Delay WebSocket connection slightly to ensure page is fully ready
            //    This helps with mobile browser stability

            setTimeout(() => this.initializeWebsocket(), WEBSOCKET_CONNECT_DELAY);
        });


    }

    // -----------------------------------------------------------------------------------------------------------------
    initializeApp() {
        this.drawApp();
        this.debugDrawing();
    }

    // -----------------------------------------------------------------------------------------------------------------
    initializeWebsocket() {
        this.addLineToTerminal('Connecting to websocket...');

        console.log(`Connecting to websocket at ${this.websocket_host}:${this.websocket_port}`);
        this.websocket = new Websocket({host: this.websocket_host, port: this.websocket_port})
        this.websocket.on('message', this.onWsMessage.bind(this));
        this.websocket.on('connected', this.onWsConnected.bind(this));
        this.websocket.on('close', this.onWSDisconnected.bind(this));
        this.websocket.on('error', this.onWsError.bind(this));
        this.websocket.connect();

    }

    // -----------------------------------------------------------------------------------------------------------------
    onWsMessage(msg) {
        console.log('Received message:', msg);
        switch (msg.type) {
            case 'init':
                this.initializeContent(msg);
                break;
            case 'close':
                this._handleCloseMessage(msg);
                break;
            case 'choose':
                this._handleFrontendChooseMessage(msg);
                break;
            case 'update':
                console.warn('This is deprecated!!!')
                console.log('Received update message:', msg);
                break;
            case 'gui_update':
                this._handleGuiUpdate(msg);
                break;
            case 'add':
                this._handleAddMessage(msg);
                break;
            case 'remove':
                this._handleRemoveMessage(msg);
                break;
            case 'widget_message':
                this._handleMessageForWidget(msg);
                break;
            case 'object_message':
                this._handleMessageForWidget(msg);
                break;
            default:
                break;
        }

        this._recordMessage();
    }

    // -----------------------------------------------------------------------------------------------------------------
    onWsConnected() {
        try {
            console.log('[App] WebSocket connected, preparing handshake...');
            this.connected = true;
            this.setConnectionStatus(true);

            // Small delay before sending handshake to ensure connection is stable
            // This helps with mobile browser quirks
            setTimeout(() => {
                try {
                    if (!this.websocket || !this.websocket.connected) {
                        console.warn('[App] WebSocket disconnected before handshake could be sent');
                        return;
                    }

                    const handshake_message = {
                        type: 'handshake',
                        data: {
                            'client_type': 'app_frontend'
                        }
                    }

                    console.log('[App] Sending handshake message...');
                    this.websocket.send(handshake_message);
                } catch (e) {
                    console.error('[App] Error sending handshake:', e);
                }
            }, 100);
        } catch (e) {
            console.error('[App] Error in onWsConnected:', e);
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    onWSDisconnected() {
        this.connected = false;
        this.setConnectionStatus(false);
        this.resetApp();
    }

    // -----------------------------------------------------------------------------------------------------------------
    onWsError(err) {
        console.error('[App] WebSocket error:', err);
        this.addLineToTerminal(`WebSocket error: ${err?.message || 'unknown'}`, 'red');
    }

    // -----------------------------------------------------------------------------------------------------------------
    resetApp() {
        // Clear the content area
        this.content.innerHTML = '';

        // Reset folder and page state
        this.root_folder = null;
        this.current_folder = null;
        this.current_page = null;

        // Clear page indicators
        if (this.page_indicators) {
            this.page_indicators.innerHTML = '';
        }

        // Clear pathbar content
        if (this.pathbar_content) {
            this.pathbar_content.textContent = 'Path:';
        }

        // Reset popups
        this.popups = {};

        // Reset the ID
        this.id = null;

        // Reset the back button state
        if (this.back_button) {
            this.back_button.disable({disable_opacity: 0.3, show_lock: false});
        }

        // Re-run debug drawing to show placeholder state
        this.debugDrawing();
    }

    // -----------------------------------------------------------------------------------------------------------------
    setConnectionStatus(connected) {
        // make the connection status element green if connected, red if not
        this.connectionStatus.classList.remove('connected', 'disconnected');
        if (connected) {
            this.connectionStatus.classList.add('connected');
            this.addLineToTerminal('Websocket connected');
        } else {
            this.connectionStatus.classList.add('disconnected');
            this.addLineToTerminal('Websocket disconnected');
        }

    }

    // -----------------------------------------------------------------------------------------------------------------
    showSplash(image, callback) {
        // Create a splash screen element
        // TODO
        // Remove the splash screen after a delay
        setTimeout(() => {
            // Remove splash overlay
            if (callback) callback();
        }, SPLASH_TIME); // Adjust the delay as needed
    }

    // -----------------------------------------------------------------------------------------------------------------
    drawApp() {

        // Make some general settings
        // Disable pinch zoom (for iOS Safari)
        document.addEventListener('gesturestart', function (e) {
            e.preventDefault();
        });


        // Prevent double click zoom
        let lastTouchEnd = 0;
        document.addEventListener('touchend', function (event) {
            const now = new Date().getTime();
            if (now - lastTouchEnd <= 300) {
                event.preventDefault();
            }
            lastTouchEnd = now;
        }, false);


        // -----------------------------------------------------
        // Create the headbar
        const headbar = document.createElement('div');
        headbar.className = 'app-headbar';
        this.root_container.appendChild(headbar);

        const headbar_grid = document.createElement('div');
        headbar_grid.className = 'app-headbar_grid_container';
        headbar.appendChild(headbar_grid);

        this.headbar_user_grid = document.createElement('div');
        this.headbar_user_grid.className = 'app-headbar_grid';
        headbar_grid.appendChild(this.headbar_user_grid);


        const connectionStatusContainer = document.createElement('div');
        connectionStatusContainer.className = 'connection-status-container';
        this.connectionStatus = document.createElement('div');
        this.connectionStatus.className = 'connection-status';
        connectionStatusContainer.appendChild(this.connectionStatus);
        this.connectionStatus.classList.add('disconnected'); // Start as disconnected
        headbar_grid.appendChild(connectionStatusContainer);

        // const logo = document.createElement('div');
        // logo.className = 'app-headbar_logo';

        const logo_container = document.createElement('a')
        logo_container.href = 'https://github.com/dustin-lehmann/bilbolab' // Change to your desired URL
        logo_container.className = 'app-headbar_logo_container'
        logo_container.target = '_blank' // Opens in a new tab
        logo_container.rel = 'noopener noreferrer' // Security best practice
        headbar_grid.appendChild(logo_container);

        const logo = document.createElement('img');
        logo.src = new URL('./lib/symbols/bilbolab_logo.png', import.meta.url).href
        logo.alt = 'Logo'
        logo.className = 'bilbolab_logo'

        logo_container.appendChild(logo)

        // -----------------------------------------------------
        // Create the main content area
        this.content = document.createElement('div');
        this.content.className = 'app-content';
        this.root_container.appendChild(this.content);


        this.content_grid = document.createElement('div');
        this.content_grid.className = 'app-content_grid';

        const resizeContentGrid = () => {
            // Dynamically set CSS variables and aspect ratio
            const cols = parseInt(getComputedStyle(document.documentElement)
                .getPropertyValue('--content-cols'));
            const rows = parseInt(getComputedStyle(document.documentElement)
                .getPropertyValue('--content-rows'));

            const gapStr = getComputedStyle(this.content_grid).gap || 5;
            const gap = parseFloat(gapStr); // Extract numeric value

            // Approximate aspect ratio (with gap correction)
            const aspect = (cols + (cols - 1) * (gap / 100)) / (rows + (rows - 1) * (gap / 100));

            this.content_grid.style.setProperty('--content-cols', cols);
            this.content_grid.style.setProperty('--content-rows', rows);
            // this.content_grid.style.aspectRatio = aspect;

            this.content_grid.style.width = '100%';
            this.content_grid.style.height = '100%'; // height adapts

        };
        resizeContentGrid();

        window.addEventListener('resize', resizeContentGrid);
        window.addEventListener('orientationchange', () => {
            // if you have other resize listeners relying on window.resize, you can also fake a resize event:
            window.dispatchEvent(new Event('resize'));
        });

        this.attachContentListeners();

        // -----------------------------------------------------
        // Navigation
        this.navigation = document.createElement('div');
        this.navigation.className = 'app-navigation';
        this.root_container.appendChild(this.navigation);

        this.navigation_bar = document.createElement('div');
        this.navigation_bar.className = 'app-navigation_bar';
        this.navigation.appendChild(this.navigation_bar);

        this.navigation_bar_grid = document.createElement('div');
        this.navigation_bar_grid.className = 'app-navigation_bar_grid';
        this.navigation_bar.appendChild(this.navigation_bar_grid);

        // Create a button widget and place it in the 3,1 field in the navigation bar grid
        this.back_button = new ButtonWidget('back_button', {
            config: {
                'icon': '⬅️',
                'icon_size': 25,
                'icon_position': 'center',
                'color': [1, 1, 1, 0.1]
            }
        });
        this.back_button.attach(this.navigation_bar_grid, [2, 1], [1, 1]);
        this.back_button.callbacks.get('click').register(this.goBackFolder.bind(this));
        this.back_button.disable({disable_opacity: 0.3, show_lock: false});


        // Add a home button to the navigation bar
        this.home_button = new ButtonWidget('home_button', {
            config: {
                'icon': '🏠',
                'icon_size': 25,
                'icon_position': 'center',
                'color': [1, 1, 1, 0.1]
            }
        });
        this.home_button.attach(this.navigation_bar_grid, [1, 1], [1, 1]);
        this.home_button.callbacks.get('click').register(this.goHome.bind(this));

        // Create the applications button
        this.applications_button = new ButtonWidget('applications_button', {
            config: {
                'icon': '⭐',
                'icon_size': 25,
                'icon_position': 'center',
                'color': [1, 1, 1, 0.1]
            }
        });

        this.applications_button.attach(this.navigation_bar_grid, [3, 1], [1, 1]);

        this.applications_button.disable({disable_opacity: 0.2, show_lock: true});

        this.attachNavigationListeners()

        // ----------------------------------------------------
        // Create the pathbar
        this.pathbar = document.createElement('div');
        this.pathbar.className = 'app-pathbar';
        this.root_container.appendChild(this.pathbar);

        this.pathbar_content = document.createElement('div');
        this.pathbar_content.className = 'app-pathbar_content';
        this.pathbar.appendChild(this.pathbar_content);

        // Add the page indicators
        this.page_indicators = document.createElement('div');
        this.page_indicators.id = 'pageIndicators';
        this.pathbar.appendChild(this.page_indicators);

        // Create the terminal container
        this.terminal = document.createElement('div');
        this.terminal.className = 'app-terminal';
        this.root_container.appendChild(this.terminal);

        this.terminal.addEventListener('dblclick', this.toggleTerminalSize.bind(this));
        // mobile “double‑tap”:
        this.terminal.addEventListener('touchend', (e) => {
            const now = Date.now();
            const delta = now - this.lastTerminalTap;
            // consider it a double‑tap if within 300ms
            if (delta > 0 && delta < 300) {
                e.preventDefault();            // kill any pending zoom
                this.toggleTerminalSize();     // your existing method
            }
            this.lastTerminalTap = now;
        });

        // ----------------------------------------------------
        this.lower_right_bar = document.createElement('div');
        this.lower_right_bar.className = 'app-lower-right-bar';
        this.root_container.appendChild(this.lower_right_bar);
        this.lower_right_bar_grid = document.createElement('div');
        this.lower_right_bar_grid.className = 'app-lower-right-bar_grid';
        this.lower_right_bar.appendChild(this.lower_right_bar_grid);

        this.stop_button = new ButtonWidget('stop_button', {
            config: {
                'icon': '🛑',
                'icon_size': 25,
                'icon_position': 'center',
                'color': [1, 1, 1, 0.1],
            }
        });

        this.stop_button.attach(this.lower_right_bar_grid, [1, 5], [1, 1])
        this.stop_button.callbacks.get('click').register(() => {
            this.terminalError('Stop')
        });

        this.popup_button = new ButtonWidget('popup_button', {
            config: {
                'icon': '📟',
                'icon_size': 25,
                'icon_position': 'center',
                'color': [1, 1, 1, 0.1],
            }
        });

        this.popup_button.attach(this.lower_right_bar_grid, [1, 4], [1, 1]);

        this.popup_button.disable({disable_opacity: 0.2, show_lock: true});

        this.settings_button = new ButtonWidget('settings_button', {
            config: {
                'icon': '⚙️',
                'icon_size': 25,
                'icon_position': 'center',
                'color': [1, 1, 1, 0.1],
            }
        });

        this.settings_button.attach(this.lower_right_bar_grid, [1, 3], [1, 1]);
        this.settings_button.disable({disable_opacity: 0.2, show_lock: true});

        this.addLineToTerminal('Welcome to the BilboLab App!');
    }

    // -----------------------------------------------------------------------------------------------------------------
    updateBackButtonState() {
        if (this.current_folder !== this.root_folder) {
            this.back_button.enable();
        } else {
            this.back_button.disable({disable_opacity: 0.3, show_lock: false});
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    initializeContent(message) {
        // Clear any existing content before initializing (handles reconnection case)
        this.content.innerHTML = '';
        this.root_folder = null;
        this.current_folder = null;
        this.current_page = null;
        this.popups = {};

        this.id = message.configuration.id || null;
        const config = message.configuration;

        if (config.folder) {
            console.log(`Initializing content with folder ${config.folder.id}`);
            console.log('Folder data:', config.folder);

            this.root_folder = new AppFolder(config.folder.id,
                this.content,
                config.folder.config || {},
                config.folder.folders || {},
                config.folder.pages || {}
            );
            this.root_folder.parent = this;
            this.root_folder.callbacks.get('event').register(this.onEvent.bind(this));

            // Restore the last active page from localStorage, or fall back to first page
            const savedPageId = getFromLocalStorage(`${this.id}_active_page`);
            let restored = false;
            if (savedPageId) {
                const savedPage = this._getObjectByUID(savedPageId);
                if (savedPage) {
                    this.setPage(savedPage);
                    restored = true;
                }
            }
            if (!restored) {
                const firstPage = this.root_folder.getPageByPosition(0);
                if (firstPage) {
                    this.setPage(firstPage);
                } else {
                    console.warn('No pages found in the root folder.');
                }
            }

            // Ensure back button state matches the restored folder
            this.updateBackButtonState();
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    attachContentListeners() {
        this.content.addEventListener("touchstart", (e) => {
            if (e.target.closest(".sliderWidget") || e.target.closest(".joystickWidget") || e.target.closest(".classicSliderWidget") || e.target.closest(".rotaryDialWidget")) return;
            this.touchStartY = e.changedTouches[0].screenY;
        }, {passive: true});

        this.content.addEventListener("touchmove", (e) => {
            if (e.target.closest(".sliderWidget") || e.target.closest(".joystickWidget") || e.target.closest(".classicSliderWidget") || e.target.closest(".rotaryDialWidget")) return;
            let currentY = e.changedTouches[0].screenY;
            if (Math.abs(this.touchStartY - currentY) > 10) {
                this.isSwiping = true;
            }
        }, {passive: true});

        this.content.addEventListener("touchend", (e) => {
            if (e.target.closest(".sliderWidget") || e.target.closest(".joystickWidget") || e.target.closest(".classicSliderWidget") || e.target.closest(".rotaryDialWidget")) return;
            let currentY = e.changedTouches[0].screenY;
            let deltaY = this.touchStartY - currentY;
            if (Math.abs(deltaY) > this.swipeThreshold) {
                let direction = deltaY > 0 ? "down" : "up";
                // Increment page by -1 if up and 1 if down
                this.incrementPage(direction === "up" ? -1 : 1);

            }
            setTimeout(() => {
                this.isSwiping = false;
            }, 100);
        }, {passive: true});
    }

    attachNavigationListeners() {
        this.navigation.addEventListener("touchstart", (e) => {
            if (e.target.closest(".sliderWidget") || e.target.closest(".joystickWidget") || e.target.closest(".classicSliderWidget") || e.target.closest(".rotaryDialWidget")) return;
            this.touchStartY = e.changedTouches[0].screenY;
        }, {passive: true});

        this.navigation.addEventListener("touchmove", (e) => {
            if (e.target.closest(".sliderWidget") || e.target.closest(".joystickWidget") || e.target.closest(".classicSliderWidget") || e.target.closest(".rotaryDialWidget")) return;
            let currentY = e.changedTouches[0].screenY;
            if (Math.abs(this.touchStartY - currentY) > 10) {
                this.isSwiping = true;
            }
        }, {passive: true});

        this.navigation.addEventListener("touchend", (e) => {
            if (e.target.closest(".sliderWidget") || e.target.closest(".joystickWidget") || e.target.closest(".classicSliderWidget") || e.target.closest(".rotaryDialWidget")) return;
            let currentY = e.changedTouches[0].screenY;
            let deltaY = this.touchStartY - currentY;
            if (Math.abs(deltaY) > this.swipeThreshold) {
                let direction = deltaY > 0 ? "down" : "up";
                // Increment page by -1 if up and 1 if down
                this.incrementPage(direction === "up" ? -1 : 1);

            }
            setTimeout(() => {
                this.isSwiping = false;
            }, 100);
        }, {passive: true});
    }


    // -----------------------------------------------------------------------------------------------------------------
    _handleCloseMessage(message) {
        this.terminalDebug("Received close message");
    }

    // -----------------------------------------------------------------------------------------------------------------
    _handleFrontendChooseMessage(message) {
        this.terminalDebug("Received choose message");
    }

    // -----------------------------------------------------------------------------------------------------------------
    _handleGuiUpdate(message) {
        const messages = message.messages;
        // messages is an object with keys being the IDs of the objects
        for (const [id, message] of Object.entries(messages)) {
            const object = this._getObjectByUID(id);
            if (!object) {
                console.warn(`Object with UID "${id}" not found.`);
                continue;
            }
            // Check if the message is an array, if so, iterate over it
            if (Array.isArray(message)) {
                console.warn(`Received array message for object "${id}":`, message);
                // If it's an array, we assume it's a list of updates
                for (const item of message) {
                    object.update(item.data);
                }
            } else {
                object.update(message.data);
            }

        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    _handleAddMessage(message) {
        const data = message.data;


        if (data.type === 'popup') {
            this.terminalDebug("I received an add popup message. Needs to be implemented");
            this._addPopup(data);
            return;
        }

        if (data.type === 'callout') {
            this.terminalDebug("I received an add callout message. Needs to be implemented");
            this.addCallout(data);
            return;
        }
        // Get the object we want to add something to
        const parent = this._getObjectByUID(data.parent);

        if (!parent) {
            console.warn(`Received add message for unknown parent "${data.parent}"`);
            return;
        }

        console.log('Received add message for parent', parent);

        parent.handleAddMessage(data);
    }

    // -----------------------------------------------------------------------------------------------------------------
    _handleRemoveMessage(message) {
        const data = message.data;

        if (data.type === 'popup') {
            this.terminalDebug("I received a remove popup message. Needs to be implemented");
            return;
            // Check if the popup exists
            if (!this.popups[data.id]) {
                console.warn(`Received remove message for unknown popup "${data.id}"`);
                console.warn('Available popups:', Object.keys(this.popups));
                return;
            }


            this.popups[data.id]?.close();
            console.log(`Removing popup with ID "${data.id}"`);
            delete this.popups[data.id];
            return;
        } else if (data.type === 'callout') {
            this.terminalDebug("I received a remove callout message. Needs to be implemented");
            return;
            // Check if the callout exists
            if (!this.callouts[data.id]) {
                console.warn(`Received remove message for unknown callout "${data.id}"`);
                console.warn('Available callouts:', Object.keys(this.callouts));
                return;
            }

            this.removeCallout(data);
            console.log(`Removing callout with ID "${data.id}"`);
            return;
        }

        const parent = this._getObjectByUID(data.parent);
        if (!parent) {
            console.warn(`Received remove message for unknown parent "${data.parent}"`);
            return;
        }
        parent.handleRemoveMessage(data);
    }


    // -----------------------------------------------------------------------------------------------------------------
    _handleMessageForWidget(message) {
        const object = this._getObjectByUID(message.id);
        console.log('Received message for object', object);
        if (object) {
            object.onMessage(message.data);
        } else {
            console.warn(`Received widget message for unknown object "${message.id}"`);
            console.warn('Message data:', message.data);
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    onMessage(message) {
        switch (message.type) {
            case 'function': {
                this.callFunction(message.function_name, message.args, message.spread_args);
                break;
            }
            default:
        }
    }

    /* ===============================================================================================================*/
    callFunction(function_name, args, spread_args = true) {
        const fn = this[function_name];

        if (typeof fn !== 'function') {
            console.warn(`Function '${function_name}' not found or not callable.`);
            return null;
        }

        // If args is an array and spreading is enabled
        if (Array.isArray(args) && spread_args) {
            return fn.apply(this, args);
        }

        // Otherwise, pass as a single argument (object, primitive, etc.)
        return fn.call(this, args);
    }

    // -----------------------------------------------------------------------------------------------------------------
    _recordMessage(message) {
        // TODO
    }

    // -----------------------------------------------------------------------------------------------------------------
    _getObjectByUID(uid) {
        const trimmed = uid.replace(/^\/+|\/+$/g, '');

        const [app_segment, app_remainder] = splitPath(trimmed);

        if (!app_segment || app_segment !== this.id) {
            console.warn(`UID "${uid}" does not match this Apps's ID "${this.id}".`);
            return null;
        }

        if (!app_remainder) {
            return this;
        }

        // Split off the type and the rest of the path
        const [object_type, object_remainder] = splitPath(app_remainder);

        if (object_type === 'folders') {

            const [folder_segment, folder_remainder] = splitPath(object_remainder);
            const fullKey = `${app_segment}/${object_type}/${folder_segment}`;

            // Check if the fullKey matches our root_folder
            if (fullKey !== this.root_folder.id) {
                console.warn(`Folder "${fullKey}" does not match the root folder ID "${this.root_folder.id}".`);
                return;
            }

            if (!folder_remainder) {
                return this.root_folder;
            }

            return this.root_folder.getObjectByPath(folder_remainder);

        } else if (object_type === 'popup') {
            const [popup_segment, popup_remainder] = splitPath(object_remainder);
            const fullKey = `${app_segment}/${object_type}/${popup_segment}`;
            const popup = this.popups[fullKey];
            if (!popup) {
                console.warn(`Popup "${fullKey}" not found in UID "${uid}".`);
                return null;
            }
            if (!popup_remainder) {
                return popup;
            } else {
                return popup.getObjectByPath(popup_remainder);
            }
        } else {
            console.warn(`Unknown object type "${object_type}" in UID "${uid}".`);
            return null;
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    setFolder(folder) {
        console.log(`We want to set the folder to ${folder}`)
        // look up folder by string, validate, etc…
        if (typeof folder === 'string') {
            folder = this._getObjectByUID(folder);
            // Check if folder is an AppFolder instance
            if (!(folder instanceof AppFolder)) {
                console.warn(`Folder with UID "${folder}" is not an instance of AppFolder.`);
                return;
            }
        }
        // now actually switch: show page 0 of the new folder
        const firstPage = folder.getPageByPosition(0);
        if (!firstPage) return;
        this.setPage(firstPage);


        this.current_folder = folder;
        // update the back button
        this.updateBackButtonState();
    }

    // -----------------------------------------------------------------------------------------------------------------
    goBackFolder() {

        // Check if the current folder has a parent that is a folder, not the app
        if (!this.current_folder || !this.current_folder.parent || !(this.current_folder.parent instanceof AppFolder)) {
            console.warn('No parent folder to go back to.');
            return;
        }

        const parent_folder = this.current_folder.parent;

        // navigate there, but don't re‑record it
        this.setFolder(parent_folder);

    }

    goHome() {
        this.setFolder(this.root_folder);
    }

    // -----------------------------------------------------------------------------------------------------------------
    setPage(page) {
        // Accept a string UID and resolve it to a page object
        if (typeof page === 'string') {
            page = this._getObjectByUID(page);
            if (!page) {
                console.warn(`Page with UID "${page}" not found.`);
                return;
            }
        }

        // Make the current page not visible
        if (this.current_page) {
            this.current_page.visible(false);
        }


        // Set the desired page as current page
        this.current_page = page;

        // Make the current page visible
        this.current_page.visible(true);

        // Set the current folder to the one corresponding to the page
        this.current_folder = page.folder;

        this.updatePageIndicators();
        this.pathbar_content.textContent = `Path: ${this.current_folder.id}`;

        // Persist active page so it survives page reloads
        if (this.id && page.id) {
            writeToLocalStorage(`${this.id}_active_page`, page.id);
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    updatePageIndicators() {
        // Draw the page indicators
        if (!this.current_folder) {
            return;
        }
        const num_indicators = Object.keys(this.current_folder.pages).length;
        const index_indicators = this.current_page.position;
        this.drawPageIndicators(num_indicators, index_indicators);
    }

    // -----------------------------------------------------------------------------------------------------------------
    drawPageIndicators(num_indicators, position) {

        // Clear the page indicators
        this.page_indicators.innerHTML = '';

        // Draw page indicators
        for (let i = 0; i < num_indicators; i++) {
            const indicator = document.createElement("div");
            indicator.className = 'pageIndicator';
            if (i === position) {
                indicator.classList.add('active');
            }

            indicator.addEventListener("click", (e) => {
                // Request page i from the current folder and then set it as current page
                const page = this.current_folder.getPageByPosition(i);
                if (page) {
                    this.setPage(page);
                } else {
                    console.warn(`Page at position ${i} not found in current folder.`);
                }
            });

            this.page_indicators.appendChild(indicator);
        }
    }

    // -----------------------------------------------------------------------------------------------------------------
    debugDrawing() {
        // This is just for debugging purposes, to see if the app is drawing correctly

        // Fill the headbar grid with app-headbar_grid_placeholder
        const headbar_grid_rows = 2;
        const headbar_grid_columns = 40;
        for (let i = 0; i < headbar_grid_rows * headbar_grid_columns; i++) {
            const placeholder = document.createElement('div');
            placeholder.className = 'app-headbar_grid_placeholder';
            this.headbar_user_grid.appendChild(placeholder);
        }

        const content_grid_columns = parseInt(getComputedStyle(document.documentElement)
            .getPropertyValue('--content-cols'));
        const content_grid_rows = parseInt(getComputedStyle(document.documentElement)
            .getPropertyValue('--content-rows'));

        for (let i = 0; i < content_grid_rows * content_grid_columns; i++) {
            const placeholder = document.createElement('div');
            placeholder.className = 'app-content_grid_placeholder';
            this.content_grid.appendChild(placeholder);
        }

        this.pathbar_content.textContent = `Path:`;

        return; // Do not run the rest of the debug code

        // Make some folders and pages for debug
        const folder1 = new AppFolder('folder1', this.content);
        const page1 = new AppFolderPage('page1', {rows: 3})
        const page2 = new AppFolderPage('page2',)
        const page3 = new AppFolderPage('page3', {rows: 5, columns: 10, gap: 2, radius: 0})


        const button1 = new ButtonWidget('button1',
            {
                text: 'Button 1',
                color: [0.5, 0, 0],
                icon: '🤖',
                icon_position: 'center',
                text_position: 'bottom',
                border_style: 'dashed',
                border_width: 1,
                top_icon: '🗂️'
            });
        page1.addObject(button1, 1, 1, 1, 1);
        // page2.addObject(button1, 1, 1, 1, 1);

        const button2 = new ButtonWidget('button1',
            {
                text: 'Button 1',
                // color: [0.5, 0, 0],
                icon: '🤖',
                icon_position: 'center',
                text_position: 'bottom',
                border_style: 'dashed',
                border_width: 1,
                top_icon: '🗂️'
            });
        page2.addObject(button2, 1, 1, 1, 1);

        const slider1 = new SliderWidget('slider1', {
            title: 'Slider 1',
            color: [0.0, 0.2, 0.1],
            value: 2,
            increment: 0.1
        });
        page1.addObject(slider1, 1, 2, 2, 1);
        const multistatebutton = new MultiStateButtonWidget('multistatebutton1',
            {title: 'MSB 1', color: [0.0, 0, 0.2], states: ['A', 'B', 'C', 'D']});
        page1.addObject(multistatebutton, 2, 1, 1, 1);


        const rotarydial1 = new RotaryDialWidget('rdw1', {title: 'Rotary', dialWidth: 7, value: 50});
        page1.addObject(rotarydial1, 2, 2, 2, 2);

        const classicslider1 = new ClassicSliderWidget('cslider1', {
            title: 'CS1',
            titlePosition: 'top',
            color: [0.0, 0.2, 0.1],
            value: 2,
            increment: 0.1
        });
        // page1.addObject(classicslider1, 2, 3, 2, 1);

        const msw1 = new MultiSelectWidget('msw1', {
            title: 'MSW 1',
            color: [0.0, 0.2, 0.1],
            options: {
                'A': {label: 'Option A'},
                'B': {label: 'Option B'},
                'C': {label: 'Option C'},
                'D': {label: 'Option D'}
            },
            value: 'A'
        });
        page1.addObject(msw1, 1, 4, 2, 1);


        const digitalnumberwidget1 = new DigitalNumberWidget('dnw1', {
            title: 'Number',
            title_position: 'top',
            increment: 0.1,
            value: -7.2,
            min_value: -9000,
            max_value: 90
        });

        page1.addObject(digitalnumberwidget1, 2, 4, 1, 1);

        folder1.addPage(page1);
        folder1.addPage(page2);
        folder1.addPage(page3);


        this.setPage(page1);
    }

    // -----------------------------------------------------------------------------------------------------------------
    incrementPage(increment) {

        const num_pages = Object.keys(this.current_folder.pages).length;
        const new_position = (this.current_page.position + increment + num_pages) % num_pages;
        const new_page = this.current_folder.getPageByPosition(new_position);
        if (!new_page) {
            return;
        }
        this.setPage(new_page);
    }

    // --------------------------------------------------------------------------------
    terminalDebug(message) {
        this.addLineToTerminal(`🟢 Debug: ${message}`, 'green');
    }

    // --------------------------------------------------------------------------------
    terminalError(message) {
        this.addLineToTerminal(`❌ Error: ${message}`, 'red');
    }

    // --------------------------------------------------------------------------------
    terminalWarning(message) {
        this.addLineToTerminal(`⚠️ Warning: ${message}`, 'orange');
    }

    // --------------------------------------------------------------------------------
    print(text, color) {
        this.addLineToTerminal(text, color);
    }

    // --------------------------------------------------------------------------------
    addLineToTerminal(lineText, color = 'white') {
        const now = new Date();
        const hh = String(now.getHours()).padStart(2, '0');
        const mm = String(now.getMinutes()).padStart(2, '0');
        const ss = String(now.getSeconds()).padStart(2, '0');
        const ts = `[${hh}:${mm}:${ss}]`;
        const lineEl = document.createElement('div');
        lineEl.className = 'terminal-line';
        lineEl.textContent = `${ts} ${lineText}`;
        lineEl.style.color = getColor(color);
        this.terminal.appendChild(lineEl);

        const {scrollTop, clientHeight, scrollHeight} = this.terminal;
        if (scrollTop + clientHeight >= scrollHeight - 40) {
            this.terminal.scrollTop = scrollHeight;
        }
    }

    // --------------------------------------------------------------------------------
    clearTerminal() {
        this.terminal.innerHTML = '';
    }

    /**
     * Expand the terminal and show the input field + send button.
     */
    expandTerminal() {
        this.terminal.classList.add('terminal-expanded');
        this.isTerminalExpanded = true;
        this.terminal.scrollTop = this.terminal.scrollHeight;

        // Create input container once
        if (!this._terminalInputContainer) {
            const container = document.createElement('div');
            container.className = 'terminal-input-container';

            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'terminal-input';
            input.placeholder = 'Type a message…';

            // force no autocorrect / no spellcheck / no autocomplete:
            input.setAttribute('autocorrect', 'off');
            input.setAttribute('autocapitalize', 'off');
            input.setAttribute('autocomplete', 'off');
            input.setAttribute('spellcheck', 'false');
            input.setAttribute('lang', 'en');
            input.setAttribute('inputmode', 'latin');
            input.setAttribute('enterkeyhint', 'enter');


            const button = document.createElement('button');
            button.className = 'terminal-send-button';
            button.innerText = '➡️';

            // on click or Enter, invoke the stub and clear
            const send = () => {
                const txt = input.value.trim();
                if (!txt) return;
                this.onTerminalSend(txt);
                input.value = '';
            };
            button.addEventListener('click', send);
            input.addEventListener('keydown', e => {
                if (e.key === 'Enter') send();
            });

            container.append(input, button);
            this.terminal.appendChild(container);
            this._terminalInputContainer = container;
        } else {
            this._terminalInputContainer.style.display = 'flex';
        }
    }

    /**
     * Collapse the terminal and hide the input field + send button.
     */
    collapseTerminal() {
        this.terminal.classList.remove('terminal-expanded');
        this.isTerminalExpanded = false;
        this.terminal.scrollTop = this.terminal.scrollHeight;
        if (this._terminalInputContainer) {
            this._terminalInputContainer.style.display = 'none';
        }
    }


    // --------------------------------------------------------------------------------
    toggleTerminalSize() {
        console.log('toggleTerminalSize');
        if (this.isTerminalExpanded) this.collapseTerminal();
        else this.expandTerminal();
    }

    // -----------------------------------------------------------------------------------------------------------------
    addFolder(folder) {
        if (folder.id in this.folders) {
            console.warn(`Folder with ID "${folder.id}" already exists.`);
            return;
        }
        this.folders[folder.id] = folder;

        // JSON stringify the event
        folder.callbacks.get('event').register(this.onEvent.bind(this));
    }

    // -----------------------------------------------------------------------------------------------------------------
    onTerminalSend(message) {
        // This is a stub, you can override it in your app
        this.addLineToTerminal(`You: ${message}`);
    }

    // -----------------------------------------------------------------------------------------------------------------
    onEvent(event) {
        // This is a stub, you can override it in your app
        const message = {
            'type': 'event', 'id': event.id, 'data': event,
        }
        if (this.connected) {
            this.websocket.send(message);
        }
    }
}
