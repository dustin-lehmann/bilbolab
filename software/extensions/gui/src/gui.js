import {CLI_Terminal} from './lib/cli_terminal/cli_terminal.js';
import {ButtonWidget} from './lib/objects/js/buttons.js';
import {ContextMenuItem} from './lib/objects/contextmenu.js'
import {openFilePicker} from './lib/file_picker.js';

import './lib/styles/popup.css'
import './lib/styles/objects.css';

// NOTE: Page must be imported before WidgetGroup to ensure mapping.js
// loads before group.js, resolving their circular dependency correctly.
import {Page} from './lib/page.js';
import {Category} from './lib/category.js';
import {Popup} from './lib/popup.js';
import {Callout} from './lib/callout.js';

import {WidgetGroup} from './lib/objects/group.js';
import {activeGUI, setActiveGUI} from "./lib/globals.js";

import {
    existsInLocalStorage,
    getFromLocalStorage,
    removeFromLocalStorage,
    splitPath,
    writeToLocalStorage
} from './lib/helpers.js';
import {Websocket} from './lib/websocket.js';

const GUI_WS_DEFAULT_PORT = 8100;


/* ================================================================================================================== */

export class ShortcutButton extends ButtonWidget {
    constructor(id, data = {}) {
        super(id, data);

        // style the button
        this.element.classList.add('shortcut_button');
        this.on('click', this.onClick.bind(this));
        this.disabled = false;

        const context_menu_item_remove = new ContextMenuItem('remove',
            {
                name: 'Remove from Favorites',
                front_icon: '🗑️'
            });

        this.addItemToContextMenu(context_menu_item_remove);
        context_menu_item_remove.callbacks.get('click').register(this.removeFromFavorites.bind(this));

    }

    removeFromFavorites() {
        activeGUI.removeShortcut(this.id);

        delete this;
    }

    // clean up if destroying this button
    destroy() {
    }

    disable() {
        this.element.classList.add('disabled-shortcut');
        this.disabled = true;
    }

    enable() {
        this.element.classList.remove('disabled-shortcut');
        this.disabled = false;
    }

    onClick() {

        if (this.disabled) {
            return;
        }

        // Try to get the page from the gui
        const object = activeGUI.getObjectByUID(this.id);

        if (object instanceof Page) {
            if (object.parent && object.parent.setPage) {
                activeGUI.setCategory(object.parent.id);
                object.parent.setPage(object.id);
                writeToLocalStorage(`${activeGUI.id}_active_page`, object.id);
            } else {
                console.warn(`Cannot set page "${object.id}" in category "${object.parent ? object.parent.id : 'unknown'}".`);
            }
        } else if (object instanceof Category) {
            activeGUI.setCategory(object.id);
            // Set it to the first page
            const firstPage = Object.values(object.pages)[0];
            if (firstPage) {
                object.setPage(firstPage.id);
                writeToLocalStorage(`${activeGUI.id}_active_page`, firstPage.id);
            } else {
                console.warn(`Category "${object.id}" has no pages to select.`);
            }

        } else {
            console.warn(`Cannot find object with ID "${this.id}".`);
        }
    }

    resize() {
    }
}

/* ================================================================================================================== */
/* Extracted modules: Page→lib/page.js, Category→lib/category.js, Popup→lib/popup.js, Callout→lib/callout.js       */
/* ================================================================================================================== */

// Re-export moved classes for external compatibility
export {Page} from './lib/page.js';
export {Category, CategoryButton} from './lib/category.js';
export {Popup} from './lib/popup.js';
export {Callout} from './lib/callout.js';

/* ================================================================================================================== */
export class GUI {

    grid = null;
    content = null;
    head_bar = null;
    head_bar_grid = null;
    page_bar = null;
    category_bar = null;
    terminal_container = null;
    rows = 0;
    cols = 0;

    _emergencyArmed = false;
    _armTimeoutId = null;

    /** @type {Object} */
    category_buttons = {};

    /** @type {Object} */
    popups = {};


    /** @type {Object} */
    callouts = {};


    /** @type {Object} */
    configuration = {};

    /** @type {boolean} */
    connected = false;

    /** @type {Object} */
    popup_terminals = {};


    /* ===============================================================================================================*/
    constructor(rootContainer, configuration = {}) {

        const default_configuration = {
            number_of_categories: 10,
            show_category_bar: true,
            // auto_hide_category_bar: true,
            callout_position: ['right', 'bottom'],
            callout_margins: [10, 200]
        }

        this.rootContainer = rootContainer;
        this.configuration = {...default_configuration, ...configuration};

        this.globalInitialize();
        this.initializeGUI();
        // 1) Kick off the splash
        // this.showSplash('bilbolab_logo.png', () => {
        //     // 2) Once done, run the normal GUI setup
        //     this.initializeGUI();
        // });

        setActiveGUI(this);
    }

    /* ===============================================================================================================*/
    initializeGUI() {
        this.drawGUI();
        this.showCategoryBar(this.configuration.show_category_bar);

        this.category = null;
        this.categories = {}
        this.category_buttons = {}

        for (let i = 0; i < this.configuration.number_of_categories; i++) {
            this.category_buttons[i] = null;
        }

        this.addLogo();
        this.addConnectionIndicator();

        const websocket_host = import.meta.env.VITE_WS_HOST || window.location.hostname;
        const websocket_port = parseInt(import.meta.env.VITE_WS_PORT, 10) || GUI_WS_DEFAULT_PORT;

        this.websocket = new Websocket({host: websocket_host, port: websocket_port})
        this.websocket.connect();
        this.websocket.on('message', this.onWsMessage.bind(this));
        this.websocket.on('connected', this.onWsConnected.bind(this));
        this.websocket.on('close', this.onWSDisconnected.bind(this));
        this.websocket.on('error', this.onWsError.bind(this));

        this.resetGUI();

        this._clearRateTimer = null;

        window.addEventListener('keydown', this._onWindowKeyDown.bind(this));

    }

    /* ===============================================================================================================*/
    closeWindow() {
        // hack to make some browsers treat this as a script-opened window
        window.open('', '_self').close();
    }

    /* ===============================================================================================================*/
    globalInitialize() {

    }

    /* ===============================================================================================================*/
    testFunction(input) {
        console.log("Test function called with input:");
        console.log(input);
        this.terminal.print(`Test function called with input: ${input}`);
    }

    /* ===============================================================================================================*/
    deleteAllLocalStorage() {
        // If the GUI is not initialized yet, i.e. has no ID, do nothing
        if (!this.id) {
            console.warn("GUI not initialized, cannot delete localStorage.");
            return;
        }

        // Get all keys in localStorage that start with this.id
        const keysToDelete = Object.keys(localStorage).filter(key => key.startsWith(this.id));

        // Delete each key
        keysToDelete.forEach(key => {
            localStorage.removeItem(key);
        });
    }


    /* ===============================================================================================================*/
    drawGUI() {
        // clear any existing content
        this.rootContainer.innerHTML = '';

        // ── HEADER / HEADBAR ────────────────────────────────────────────────────
        this.head_bar = document.createElement('header');
        this.head_bar.id = 'headbar';
        this.head_bar_grid = document.createElement('div');
        this.head_bar_grid.id = 'headbar_grid';
        this.head_bar.appendChild(this.head_bar_grid);
        this.rootContainer.appendChild(this.head_bar);

        // ── SIDE PLACEHOLDER ───────────────────────────────────────────────────
        this.side_placeholder = document.createElement('div');
        this.side_placeholder.id = 'side_placeholder';
        this.rootContainer.appendChild(this.side_placeholder);

        // ── ROBOT STATUS BAR ───────────────────────────────────────────────────
        this.category_head_bar = document.createElement('div');
        this.category_head_bar.id = 'category_head_bar';
        this.rootContainer.appendChild(this.category_head_bar);

        // ── PAGE BAR ───────────────────────────────────────────────────────────
        this.page_bar = document.createElement('nav');
        this.page_bar.id = 'page_bar';
        this.page_bar_grid = document.createElement('div');
        this.page_bar_grid.id = 'page_bar_grid';
        this.page_bar_grid.className = 'page_bar_grid';
        this.page_bar.appendChild(this.page_bar_grid);
        this.rootContainer.appendChild(this.page_bar);

        // ── CATEGORY BAR ───────────────────────────────────────────────────────
        this.category_bar = document.createElement('aside');
        this.category_bar.id = 'category_bar';

        // <— instead of a <div class="grid">, make a <ul> for nesting
        this.category_bar_list = document.createElement('ul');
        this.category_bar_list.id = 'category_bar_list';
        this.category_bar.appendChild(this.category_bar_list);

        // ── FAVORITES SECTION (in category bar) ────────────────────────────────
        this.favorites_section = document.createElement('div');
        this.favorites_section.id = 'favorites_section';
        this.category_bar.appendChild(this.favorites_section);

        this.shortcuts_container = document.createElement('div');
        this.shortcuts_container.className = 'shortcuts-container';
        this.favorites_section.appendChild(this.shortcuts_container);

        this.drawShortcutsContainer();

        this.rootContainer.appendChild(this.category_bar);


        // ── MAIN CONTENT ───────────────────────────────────────────────────────
        this.content = document.createElement('main');
        this.content.id = 'content';
        this.rootContainer.appendChild(this.content);

        // ── FOOTER / TERMINAL ──────────────────────────────────────────────────
        this.bottombar = document.createElement('footer');
        this.bottombar.id = 'bottombar';

        this.terminal_container = document.createElement('div');
        this.terminal_container.id = 'terminal-container';
        this.terminal_container.className = 'terminal-container';


        this.bottombar.appendChild(this.terminal_container);

        this.rootContainer.appendChild(this.bottombar);

        this.bottom_container = document.createElement('div');
        this.bottom_container.className = 'bottom-container';
        this.bottombar.appendChild(this.bottom_container);

        // Category-specific bottom group (left side, hidden by default)
        this.bottom_category_container = document.createElement('div');
        this.bottom_category_container.className = 'bottom-category-container hidden';
        this.bottom_container.appendChild(this.bottom_category_container);

        // Global bottom group (right side)
        this.bottom_global_container = document.createElement('div');
        this.bottom_global_container.className = 'bottom-global-container';
        this.bottom_container.appendChild(this.bottom_global_container);

        // Emergency stop container (conditionally shown later via _initialize)
        this.emergency_container = document.createElement('div');
        this.emergency_container.className = 'emergency-container';
        this.bottombar.appendChild(this.emergency_container);

        this.stopButton = document.createElement('button');
        this.stopButton.className = 'stop-button';
        this.emergency_container.appendChild(this.stopButton);

        const stopIcon = document.createElement('img');
        stopIcon.src = 'emergency_stop.png';
        stopIcon.alt = 'Stop';
        stopIcon.className = 'stop-icon';
        this.stopButton.appendChild(stopIcon);

        // Add a click listener to the stop button
        this.stopButton.addEventListener('click', () => {
            this._emergencyStop();
        });

        // Emergency stop is enabled by default; _initialize may disable it
        this._enableEmergencyStop = true;

        // Initial Display
        this.bottombar.style.display = 'none';
    }

    /* ===============================================================================================================*/
    drawShortcutsContainer() {
        this.shortcuts_group = new WidgetGroup('shortcuts', {
                config: {
                    rows: 4,
                    columns: 1,
                    border_width: 0,
                    gap: 3,
                    fit: true,
                    title: 'Favorites',
                    title_bottom_border: false,
                    fill_empty: true,
                    non_fit_aspect_ratio: 0.5
                }
            }
        );
        this.shortcuts_container.appendChild(this.shortcuts_group.getElement());
    }

    /* ===============================================================================================================*/
    addShortcut(object, text = null, save = true) {
        // Create a button widget for the shortcut

        let object_id;
        // Check if page is a string or an actual page
        if (typeof object === 'string') {
            object_id = object;
        } else {
            object_id = object.id;
        }

        let button_text = text;
        if (text === null) {
            if (object instanceof Page) {
                button_text = `${object.parent.configuration.name} / ${object.configuration.name}`
            } else if (object instanceof Category) {
                if (object.configuration.icon) {
                    button_text = `${object.configuration.icon} ${object.configuration.name}`
                } else {
                    button_text = object.configuration.name;
                }

            } else {
                button_text = object_id;
            }
        }

        const button = new ShortcutButton(object_id, {
                config: {
                    text: button_text,
                }
            }
        );

        const free_spot = this.shortcuts_group.getEmptySpot(1, 1);

        if (!free_spot) {
            this.terminal.print(`No free spot in shortcuts group for object "${object_id}".`, 'orange');
            return;
        }

        // Add the button to the shortcuts group
        this.shortcuts_group.addObject(button,
            free_spot[0], free_spot[1], 1, 1);

        if (save) {
            this.storeShortcuts();
        }
    }

    /* ===============================================================================================================*/
    removeShortcut(page) {
        // Lookup the entry by its id in the map
        const entry = this.shortcuts_group.objects[page];
        if (!entry) {
            console.warn(`Shortcut for page "${page}" not found in shortcuts group.`);
            return;
        }

        // Remove it (removeObject accepts either the id string or the child instance)
        this.shortcuts_group.removeObject(page);

        // Store the shortcuts
        this.storeShortcuts();
        this.updateShortcuts();
    }

    /* ===============================================================================================================*/
    /**
     * This is called whenever a page or category is added, to check if the stored shortcut is accessible
     */
    updateShortcuts() {
        // Make a copy of the current shortcut objects
        const shortcuts = {};

        // Copy the id and text out of each shortcut
        for (const [id, shortcut] of Object.entries(this.shortcuts_group.objects)) {
            shortcuts[id] = {
                id: id,
                text: shortcut.configuration.text
            }
        }

        // Clear the group
        this.shortcuts_group.clear();

        // Add the shortcuts back to the group
        for (const [id, shortcut] of Object.entries(shortcuts)) {
            this.addShortcut(id, shortcut.text, false);
        }

        // Loop through all objects in the shortcuts group
        for (const [id, entry] of Object.entries(this.shortcuts_group.objects)) {
            // Check if the object exists
            const object = this.getObjectByUID(id);
            if (!object) {
                entry.disable();
            } else {
                entry.enable();
            }
        }
    }

    /* ===============================================================================================================*/
    storeShortcuts() {
        const shortcuts_key = `${this.id}_shortcuts`;

        // Check if it already is in local storage, if yes, remove it
        if (existsInLocalStorage(shortcuts_key)) {
            removeFromLocalStorage(shortcuts_key);
        }

        // Generate a shortcut array and go through this.shortcuts_group to store their ids
        const shortcuts = [];
        for (const [key, value] of Object.entries(this.shortcuts_group.objects)) {

            if (key === 'undefined') continue;

            const shortcut_data = {
                page_id: key,
                text: value.configuration.text || key,
            }

            shortcuts.push(shortcut_data);
        }

        // Store the array in local storage
        writeToLocalStorage(shortcuts_key, shortcuts);
    }

    /* ===============================================================================================================*/
    /**
     * Load the shortcuts from local storage, if possible
     */
    restoreShortcuts() {
        this.shortcuts_group.clear();

        const shortcuts_key = `${this.id}_shortcuts`;
        if (existsInLocalStorage(shortcuts_key)) {
            const shortcuts = getFromLocalStorage(shortcuts_key);

            // Loop over the shortcut array and generate shortcuts
            for (const shortcut of shortcuts) {

                // Check if shortcut is an object, if not return
                if (typeof shortcut !== 'object') {
                    console.warn(`Shortcut "${shortcut}" is not an object.`);
                    continue;
                }
                this.addShortcut(shortcut.page_id, shortcut.text, false); // Do not save it to local storage since we just received it
            }
        }
        this.updateShortcuts();
    }

    /* ===============================================================================================================*/
    showPageBar(show) {
        if (show) {
            // put the page_bar back…
            this.page_bar.style.display = '';
            // …and restore your default CSS template‐rows
            this.rootContainer.style.gridTemplateRows = '';
        } else {
            // hide the page_bar completely
            this.page_bar.style.display = 'none';
            // collapse that row to zero and let content fill it
            this.rootContainer.style.gridTemplateRows =
                'var(--headbar-height) ' +
                'var(--category-bar-height) ' +
                '0 ' +               // ← collapse the “pages” row
                'auto ' +             // ← content now starts here
                'var(--bottom-height)';
        }
    }

    /* ===============================================================================================================*/
    showCategoryBar(show) {
        // Do we currently have the bar hidden?

        if (show) {
            // → SHOW IT AGAIN
            this.category_bar.style.display = '';
            // restore the grid-template-columns from your CSS
            this.rootContainer.style.gridTemplateColumns = '';
        } else {
            // → HIDE IT
            this.category_bar.style.display = 'none';
            // collapse the first column, let the 2nd column fill 100%
            this.rootContainer.style.gridTemplateColumns = '0 1fr';
        }
    }

    /* ===============================================================================================================*/
    getObjectByUID(uid) {

        if (this.id === undefined) {
            return null;
        }
        const trimmed = uid.replace(/^\/+|\/+$/g, '');

        const [gui_segment, gui_remainder] = splitPath(trimmed);

        if (!gui_segment || gui_segment !== this.id) {
            console.warn(`UID "${uid}" does not match this GUI's ID "${this.id}".`);
            return null;
        }

        if (!gui_remainder) {
            return this;
        }

        // Split off the type
        const [object_type, object_remainder] = splitPath(gui_remainder);

        // Check if the type is in ['categories', 'popups', 'callouts']
        if (object_type === 'categories') {
            const [category_segment, category_remainder] = splitPath(object_remainder);
            const fullKey = `${this.id}/categories/${category_segment}`;
            // 1) Sub‐category?
            const subCat = this.categories[fullKey];
            if (subCat) {
                if (!category_remainder) return subCat;
                return subCat.getObjectByPath(category_remainder);
            }
        } else if (object_type === 'popups') {
            const [popup_segment, popup_remainder] = splitPath(object_remainder);
            const fullKey = `${this.id}/popups/${popup_segment}`;
            // 1) Popup itself?
            const popup = this.popups[fullKey];
            if (popup) {
                return popup.getObjectByPath(popup_remainder);
            }
        } else if (object_type === 'callouts') {
            const [callout_segment, callout_remainder] = splitPath(object_remainder);
            const fullKey = `${this.id}/callouts/${callout_segment}`;
            // 1) Callout itself?
            const callout = this.callouts[fullKey];
            if (callout) {
                if (!callout_remainder) return callout.element;
                // Callout buttons are not nested, so we can just return the element
                // or null if it doesn't match any button.
                const button = callout.buttons[callout_remainder];
                return button ? button.element : null;
            }
        } else if (object_type === 'terminals') {
            const [cli_terminal_segment, cli_terminal_remainder] = splitPath(object_remainder);
            const fullKey = `${this.id}/terminals/${cli_terminal_segment}`;
            // 1) CLI terminal itself?
            if (!this.terminal) {
                console.warn(`CLI terminal "${fullKey}" not found.`);
                return null;
            }
            if (fullKey === this.terminal.id) {
                return this.terminal;
            }
        } else if (object_type === 'bottom_group') {
            if (!this.bottom_group) {
                console.warn(`Bottom group not found in GUI "${this.id}".`);
                return null;
            }
            if (!object_remainder) return this.bottom_group;
            return this.bottom_group.getObjectByPath(object_remainder);
        } else {
            console.warn(`UID "${uid}" does not start with a valid type (categories, popups, callouts).`);
            return null;
        }

        console.warn(`No matching object found for UID "${uid}" in GUI.`);
        return null; // not found
    }

    /* ===============================================================================================================*/
    resetGUI() {
        // Empty the content
        this.content.innerHTML = '';
        this.category_bar_list.innerHTML = '';
        this.page_bar.innerHTML = '';
        this.category_head_bar.innerHTML = '';

        // Delete all categories that are currently stored
        this.categories = {};
        this.category = null;

        for (let i = 0; i < this.configuration.number_of_categories; i++) {
            this.category_buttons[i] = null;
        }

        // Add the placeholder in the middle of the content area
        const placeholder = document.createElement('div');
        placeholder.className = 'content_placeholder';
        placeholder.innerHTML = `
            <span class="placeholder_title">Not connected</span>
            <span class="placeholder_info">${this.websocket.url}</span>
            `;
        this.content.appendChild(placeholder);

        this.msgRateDisplay.textContent = '-----';
    }

    /* ===============================================================================================================*/
    addLogo() {

        const logoLink = document.createElement('a')
        logoLink.href = 'https://github.com/dustin-lehmann/bilbolab' // Change to your desired URL
        logoLink.className = 'logo_link'
        logoLink.target = '_blank' // Opens in a new tab
        logoLink.rel = 'noopener noreferrer' // Security best practice

        const logo = document.createElement('img')
        logo.src = new URL('./lib/symbols/bilbolab_logo.png', import.meta.url).href
        logo.alt = 'Logo'
        logo.className = 'bilbolab_logo'

        logoLink.appendChild(logo)
        this.head_bar_grid.appendChild(logoLink)

    }

    /* ===============================================================================================================*/
    addConnectionIndicator() {

        // ——— websocket status & rate indicator ———
        this.msgTimestamps = [];
        this.msgRateWindow = 1;
        this.blinkThrottle = 100;      // ms between blinks
        this._lastBlinkTime = 0;

        // create a container in the head_bar_grid
        const statusContainer = document.createElement('div');
        statusContainer.style.gridRow = '1 / span 2';                       // top row
        statusContainer.style.gridColumn = `${String(this.headbar_cols - 1)} / span 2`; // far right
        statusContainer.style.justifySelf = 'end';
        statusContainer.style.marginRight = '10px';
        statusContainer.style.paddingRight = '10px';
        statusContainer.style.display = 'flex';
        statusContainer.style.alignItems = 'center';
        statusContainer.style.gap = '8px';


        // the little circle
        this.statusIndicator = document.createElement('div');
        this.statusIndicator.className = 'status-indicator';

        // the “X M/s” text
        this.msgRateDisplay = document.createElement('span');
        this.msgRateDisplay.className = 'msg-rate';
        this.msgRateDisplay.textContent = '-----';

        statusContainer.appendChild(this.statusIndicator);
        statusContainer.appendChild(this.msgRateDisplay);
        this.head_bar_grid.appendChild(statusContainer);
    }

    /* ===============================================================================================================*/
    addCategory(category, position = null) {
        // 1) Dedupe
        category.parent = this;
        if (this.categories[category.id]) {
            console.warn(`Category "${category.id}" already exists.`);
            return;
        }

        // 2) Register it
        this.categories[category.id] = category;
        category.callbacks.get('event').register(this._onEvent.bind(this));


        // 3) If this is the very first category, select it immediately
        if (this.category === null) {
            this.setCategory(category.id);
        }


        // 4) Rebuild the nested sidebar list so it shows the new category
        this.renderCategoryTree();
    }

    /* ===============================================================================================================*/
    setCategory(category_id) {

        // Try to retrieve the category from the object tree
        let category;
        if (category_id instanceof Category) {
            category = category_id;
        } else if (typeof category_id === 'string') {
            category = this.getObjectByUID(category_id);
        } else {
            console.warn(`Invalid category ID "${category_id}".`);
            return;
        }

        if (!category) {
            console.warn(`Category "${category_id}" not found.`);
            return;
        }
        // 1) Hide the page from the active category
        // 2) Make the category button unselected
        if (this.category) {
            this.category.hidePages();
            this.category.button.getElement().classList.remove('selected');
        }

        // 3) Save the category as the new active category
        this.category = category;

        this.category.buildCategory(this.page_bar, this.category_head_bar, this.content);

        // Swap category-specific bottom group (container stays visible, just empty if no group)
        this.bottom_category_container.innerHTML = '';
        if (category.bottom_group) {
            category.bottom_group.attach(this.bottom_category_container);
        }

        this.renderCategoryTree();
    }


    setPage(page_id) {
        const page = this.getObjectByUID(page_id);
        if (!page) {
            console.warn(`Page "${page_id}" not found.`);
            return;
        }

        const category = page.parent;
        this.setCategory(category.id);
        category.setPage(page);
    }


    /* ===============================================================================================================*/
    renderCategoryTree() {
        const container = this.category_bar_list;
        container.innerHTML = '';

        // Grab indent size once
        const indentPx = parseInt(
            getComputedStyle(document.documentElement)
                .getPropertyValue('--category-indent-step'),
            10
        );

        const build = (cats, level = 0) => {
            cats.forEach(cat => {
                // 1) make the <li>
                const li = document.createElement('li');
                li.className = 'category-item';
                li.style.position = 'relative';
                li.style.paddingLeft = `${level * indentPx}px`;

                // 2) insert one <span> per ancestor-level to draw its vertical line
                for (let lv = 1; lv <= level; lv++) {
                    const line = document.createElement('span');
                    line.className = 'connector-line';
                    // position each at its own indent offset
                    line.style.left = `${lv * indentPx - 5}px`;
                    li.appendChild(line);
                }

                // 3) double-click toggles open/closed if it has children
                if (Object.keys(cat.categories).length > 0) {

                    cat.button.getElement().classList.add('has-children');

                    li.addEventListener('dblclick', e => {
                        e.stopPropagation();
                        cat.configuration.collapsed = !cat.configuration.collapsed;
                        this.renderCategoryTree();
                    });

                    cat.button.getElement().classList.toggle('collapsed', cat.configuration.collapsed);

                } else {
                    cat.button.getElement().classList.remove('has-children');
                    cat.button.getElement().classList.remove('collapsed');
                }

                // 4) style/select button
                cat.button.getElement().classList.toggle('selected',
                    this.category && this.category.id === cat.id
                );
                cat.button.getElement().classList.toggle('not-selected',
                    !(this.category && this.category.id === cat.id)
                );

                // 5) click selects

                li.appendChild(cat.button.getElement());

                container.appendChild(li);

                // 6) recurse into open subcategories
                if (!cat.configuration.collapsed) {
                    build(Object.values(cat.categories), level + 1);
                }
            });
        };

        build(Object.values(this.categories), 0);
    }


    /* ===============================================================================================================*/
    _initializeTerminal(id, payload = {}) {
        this.terminal = new CLI_Terminal(id, payload)

        this.terminal.attach(this.terminal_container);

        this.terminal.callbacks.get('maximize').register(() => {
            this.openTerminalInPopup();
        });
        this.terminal.callbacks.get('command').register(({command, set}) => {
            // this.websocket.sendCommand(command, set);
            // Print this in all popup terminals. Loop through the this.popup_terminals object
            for (const popup_terminal of Object.values(this.popup_terminals)) {
                // popup_terminal._printUserInput(command, set);
            }
            this.onTerminalCommand(id, command, set);
        });
        this.terminal.print(`Welcome to the terminal`);
    }

    /* ===============================================================================================================*/
    openTerminalInPopup() {
        // generate a random id
        const popup_id = `popup_${Math.random().toString(36).substring(2, 15)}`;

        // Generate the group payload
        const groupPayload = {
            id: popup_id + '_group',
            config: {
                rows: 1,
                columns: 1
            }
        }

        // Create a new popup window
        const popup = new Popup(popup_id,
            {size: [800, 400], type: 'window', title: 'Terminal'},
            groupPayload,);


        // Make a new div for in the popup group gridDiv
        const terminalContainer = document.createElement('div');
        terminalContainer.style.width = '100%';
        terminalContainer.style.height = '100%';
        terminalContainer.style.maxHeight = '100%';
        terminalContainer.style.minHeight = '0';
        terminalContainer.style.gridArea = '1 / 1 / 2 / 2'; // span the whole grid
        terminalContainer.style.zIndex = '1000'; // make sure it is on top
        popup.groupWidget.gridDiv.appendChild(terminalContainer);

        // Make a new terminal
        const newTerminal = new CLI_Terminal('terminal', this.terminal.root_command_set.toConfig());
        newTerminal.attach(terminalContainer);

        popup.open();

        this.popup_terminals[popup_id] = newTerminal;

        newTerminal.setOnScreenHistory(this.terminal.on_screen_history);
        newTerminal.history = this.terminal.history;
        newTerminal.setCurrentCommandSet(this.terminal.command_set);
        newTerminal.focusInputField();

        popup.callbacks.get('closed').register(() => {
            // Remove the terminal from the popup_terminals
            delete this.popup_terminals[popup_id];
        });

        newTerminal.callbacks.get('close').register(() => {
            popup.close();
        });

        newTerminal.callbacks.get('command').register(({command, set}) => {
            this.terminal._printUserInput(command, set);
            this.terminal.callbacks.get('command').call({command, set});
        });

        // attach the keydown listener here, because apparently it does not work from inside the class ...
        popup._win.addEventListener('keydown', e => {
            if (e.key === 'Meta') {
                newTerminal.input_field.focus();
            }
        });
    }

    /* ===============================================================================================================*/
    onTerminalCommand(id, command, set) {
        const message = {
            type: 'cli_command',
            id: id,
            'data': {
                'command': command,
                'set': set.getFullPath()
            },
        }
        if (this.connected) {
            this.websocket.send(message);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    print(text, color = 'white') {
        if (this.terminal) {
            this.terminal.print(text, color);
        }

        // Loop through all the popups and print the text in them
        for (const popup_terminal of Object.values(this.popup_terminals)) {
            popup_terminal.print(text, color);
        }
    }

    /* ===============================================================================================================*/
    drawHeadBarGrid() {
        for (let row = 0; row < this.headbar_rows; row++) {
            for (let col = 0; col < this.headbar_cols; col++) {
                const gridItem = document.createElement('div');
                gridItem.className = 'headbar_cell';
                // gridItem.textContent = `${row},${col}`;  // Optional: for debugging
                this.head_bar_grid.appendChild(gridItem);
            }
        }
    }


    /* ===============================================================================================================*/
    onWsConnected() {
        this.connected = true;
        this.setConnectionStatus(true);

        const handshake_message = {
            type: 'handshake',
            data: {
                'client_type': 'frontend'
            }
        }
        this.websocket.send(handshake_message);
    }

    onWSDisconnected() {
        this.connected = false;
        this.setConnectionStatus(false);
        this.resetGUI();
    }

    onWsMessage(msg) {
        switch (msg.type) {
            case 'init':
                this._initialize(msg);
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
                this._update(msg);
                break;
            case 'gui_update':
                this._handleGuiUpdate(msg);
                break;
            case 'add':
                this.handleAddMessage(msg);
                break;
            case 'remove':
                this.handleRemoveMessage(msg);
                break;
            case 'object_message':
                this._handleMessageForWidget(msg);
                break;
            default:
                console.warn('Unknown message type', msg.type);
        }

        this._recordMessage();
    }

    onWsError(err) {

    }

    /* ===============================================================================================================*/
    _onEvent(event) {
        const message = {
            'type': 'event', 'id': event.id, 'data': event,
        }

        if (this.connected) {
            this.websocket.send(message);
        }
    }

    /* ===============================================================================================================*/
    _initialize(msg) {
        // Check if msg has a field name configuration, if yes extract it
        if (msg.configuration) {
            const config = msg.configuration;

            this.id = config.id || 'gui';
            // TODO: Here we have to set some properties, such as show category bar or auto_hide

            // Handle top bar option (category head bar above page bar)
            if (config.options && config.options.enable_top_bar === false) {
                this.category_head_bar.style.display = 'none';
                this.side_placeholder.style.display = 'none';
                this.rootContainer.style.setProperty('--category-bar-height', '0px');
            }

            // Handle emergency stop option
            if (config.options && config.options.enable_emergency_stop === false) {
                this._enableEmergencyStop = false;
                this.emergency_container.style.display = 'none';
                this.bottombar.classList.add('no-emergency');
            } else {
                this._enableEmergencyStop = true;
                this.emergency_container.style.display = '';
                this.bottombar.classList.remove('no-emergency');
            }

            // Handle terminal option
            if (config.options && config.options.enable_terminal === false) {
                this.terminal_container.style.display = 'none';
                this.bottombar.classList.add('no-terminal');
            } else {
                this.terminal_container.style.display = '';
                this.bottombar.classList.remove('no-terminal');
            }

            // Handle category bottom group option
            if (config.options && config.options.category_bottom_group_size) {
                this.bottom_category_container.classList.remove('hidden');
                const w = config.options.category_bottom_width || 0.4;
                this.bottom_category_container.style.flex = `0 0 ${w * 100}%`;
            }

            // Handle message rate display option
            this._showMessageRate = !(config.options && config.options.show_message_rate === false);
            this._messageRateWarning = (config.options && config.options.message_rate_warning) || 200;

            if (!this._showMessageRate) {
                this.msgRateDisplay.style.display = 'none';
            }

            if (config.categories) {
                for (let id in config.categories) {
                    const category = new Category(config.categories[id].id,
                        config.categories[id].config,
                        config.categories[id].pages,
                        config.categories[id].categories,
                        config.categories[id].headbar || {},
                        config.categories[id].bottom_group || null,);

                    this.addCategory(category);
                }
            }

            // Prepare the terminal
            if (config.cli_terminal) {
                console.log('Terminal is enabled');
                const rootPayload = config.cli_terminal.cli?.root || {}
                this._initializeTerminal(config.cli_terminal.id, rootPayload);

            } else {
                console.log('Terminal is disabled');
            }

            // Add bottom group
            if (config.bottom_group) {
                this._addBottomGroup(config.bottom_group);
            }

        }

        // Restore shortcuts
        this.restoreShortcuts();

        // Restore the active page
        const active_page_id = getFromLocalStorage(`${this.id}_active_page`);
        const test = `${active_page_id}`;
        if (active_page_id) {
            const page = this.getObjectByUID(test);
            if (page) {
                const category = page.parent;
                this.setCategory(category.id);
                category.setPage(test);
            }
        }
    }

    _addBottomGroup(config) {
        this.bottom_group = new WidgetGroup(config.id, config);
        this.bottom_group.attach(this.bottom_global_container);
        this.bottom_group.callbacks.get('event').register(this._onEvent.bind(this));
    }

    /* ===============================================================================================================*/
    _handleCloseMessage(msg) {
        this.close();
    }

    /* ===============================================================================================================*/
    close() {
        // Terminate the websocket connection
        if (this.websocket) {
            this.websocket.close();
            this.websocket = null;
        }
        this._showDisconnectedOverlay()
    }

    /* ===============================================================================================================*/
    _update(msg) {
        const object = this.getObjectByUID(msg.id);
        if (!object) {
            console.warn(`Object with UID "${msg.id}" not found.`);
            return;
        }
        object.update(msg.data);
    }

    /* ===============================================================================================================*/
    _handleGuiUpdate(message) {
        const messages = message.messages;
        // messages is an object with keys being the IDs of the objects
        for (const [id, message] of Object.entries(messages)) {
            const object = this.getObjectByUID(id);
            if (!object) {
                console.warn(`Object with UID "${id}" not found.`);
                continue;
            }
            // Check if the message is an array, if so, iterate over it
            if (Array.isArray(message)) {
                // console.warn(`Received array message for object "${id}":`, message);
                // If it's an array, we assume it's a list of updates
                for (const item of message) {
                    object.update(item.data);
                }
            } else {
                object.update(message.data);
            }

        }
    }

    /* ===============================================================================================================*/
    _handleMessageForWidget(message) {
        const object = this.getObjectByUID(message.id);
        if (object) {
            object.onMessage(message.data);
        } else {
            console.warn(`Received widget message for unknown object "${message.id}"`);
            console.warn('Message data:', message.data);
        }
    }

    /* ===============================================================================================================*/
    /**
     * This is called when a widget message is directly addressed to this GUI
     * @param message
     */
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

    /* ===============================================================================================================*/
    handleAddMessage(message) {
        const data = message.data;

        if (data.type === 'popup') {
            this._addPopup(data);
            return;
        }

        if (data.type === 'callout') {
            this.addCallout(data);
            return;
        }

        // Get the object we want to add something to
        const parent = this.getObjectByUID(data.parent);

        if (!parent) {
            console.warn(`Received add message for unknown parent "${data.parent}"`);
            return
        }

        console.log('Received add message:', data);
        parent.handleAddMessage(data);
    }

    /* ===============================================================================================================*/
    handleRemoveMessage(message) {
        const data = message.data;

        if (data.type === 'popup') {
            // Check if the popup exists
            if (!this.popups[data.id]) {
                console.warn(`Received remove message for unknown popup "${data.id}"`);
                console.warn('Available popups:', Object.keys(this.popups));
                return;
            }


            this.popups[data.id]?.close();
            delete this.popups[data.id];
            return;
        } else if (data.type === 'callout') {
            // Check if the callout exists
            if (!this.callouts[data.id]) {
                console.warn(`Received remove message for unknown callout "${data.id}"`);
                console.warn('Available callouts:', Object.keys(this.callouts));
                return;
            }

            this.removeCallout(data);
            return;
        }

        const parent = this.getObjectByUID(data.parent);
        if (!parent) {
            console.warn(`Received remove message for unknown parent "${data.parent}"`);
            return;
        }
        parent.handleRemoveMessage(data);
    }

    /* ===============================================================================================================*/
    _addPopup(data) {
        console.log("Adding popup:", data);
        const popup = new Popup(data.id, data.config.config, data.config.group);
        this.popups[data.id] = popup;
        popup.callbacks.get('event').register(this._onEvent.bind(this));
        popup.open();
    }

    /* ===============================================================================================================*/
    addCallout(data) {
        const calloutId = data.id;
        const cfg = data.config.config || {};

        // callback when any button is clicked or “×” is pressed
        const onEvent = (evt) => {
            // evt = { id: calloutId, event: 'button_click'|'close', data: {...} }
            this._onEvent(evt);
        };

        // callback when the callout is actually closed() in JS
        const onClose = (id) => {
            delete this.callouts[id];
        };

        // instantiate & store
        console.warn('addCallout', data);
        this.callouts[calloutId] = new Callout(calloutId, cfg, onEvent, onClose);
    }


    /* ===============================================================================================================*/
    removeCallout(data) {
        const calloutId = data.id;
        const c = this.callouts[calloutId];
        if (!c) return;
        // this will remove it from DOM and fire its onClose → delete from this.callouts
        c.close();
    }


    /* ===============================================================================================================*/
    /**
     * Call on WebSocket open/close
     */
    setConnectionStatus(connected) {
        if (connected) {
            this.statusIndicator.classList.add('connected');
            const placeholder = this.content.querySelector('.content_placeholder');
            if (placeholder) placeholder.remove();

            this.bottombar.style.display = 'grid';

            if (this.terminal) {
                this.terminal.print('Connected to Server. Welcome!');
            }
        } else {
            if (this.terminal) {
                this.terminal.destroy();
                this.terminal_container.innerHTML = '';
            }
            this.statusIndicator.classList.remove('connected');
            this.msgRateDisplay.textContent = '---';
            this.bottombar.style.display = 'none';

        }
    }

    /* ===============================================================================================================*/
    /**
     * Call this for every incoming message event
     */
    _recordMessage() {
        const now = Date.now();
        // 1) record timestamp
        this.msgTimestamps.push(now);

        // 2) prune anything older than our window
        const cutoff = now - this.msgRateWindow * 1000;
        this.msgTimestamps = this.msgTimestamps.filter(ts => ts >= cutoff);

        // 3) blink indicator for this incoming message
        this._maybeBlink();

        // 4) immediately update the display
        this._updateMessageRate();

        // 5) (re)start a timeout that, once your window has passed
        //    with no new messages, will re-compute & zero out the rate
        if (this._clearRateTimer) {
            clearTimeout(this._clearRateTimer);
        }
        this._clearRateTimer = setTimeout(() => {
            const now2 = Date.now();
            const cutoff2 = now2 - this.msgRateWindow * 1000;
            this.msgTimestamps = this.msgTimestamps.filter(ts => ts >= cutoff2);
            this._updateMessageRate();
            this._clearRateTimer = null;
        }, this.msgRateWindow * 1000);
    }

    /* ===============================================================================================================*/
    /**
     * Recompute and display the messages/sec
     */
    _updateMessageRate() {
        const count = this.msgTimestamps.length;
        const rate = count / this.msgRateWindow;

        if (this._showMessageRate) {
            this.msgRateDisplay.textContent = rate.toFixed(1) + ' M/s';
        }

        // Warning indicator when rate exceeds threshold (works whether text is shown or not)
        if (rate >= this._messageRateWarning) {
            this.statusIndicator.classList.add('rate-warning');
        } else {
            this.statusIndicator.classList.remove('rate-warning');
        }
    }

    /* ===============================================================================================================*/
    /**
     * Blink the status indicator at most once per blinkThrottle ms
     */
    _maybeBlink() {
        const now = Date.now();
        if (now - this._lastBlinkTime < this.blinkThrottle) return;
        this._lastBlinkTime = now;
        this.statusIndicator.classList.add('blink');
        this.statusIndicator.addEventListener(
            'animationend',
            () => this.statusIndicator.classList.remove('blink'),
            {once: true}
        );
    }


    showSplash(imgPath, onDone) {
        const splash = document.createElement('div');
        splash.id = 'splash';

        const img = document.createElement('img');
        img.src = imgPath;
        img.alt = 'Loading…';

        splash.appendChild(img);
        document.body.appendChild(splash);

        img.addEventListener('animationend', (e) => {
            if (e.animationName === 'fadeOut') {
                document.body.removeChild(splash);
                onDone();
            }
        });
    }


    _removeOverlay(id) {
        const o = document.getElementById(id);
        if (o) o.remove();
    }


    _showChooseOverlay() {
        // guard: only one
        if (document.getElementById('choose-overlay')) return;

        const overlay = document.createElement('div');
        overlay.id = 'choose-overlay';
        overlay.classList.add('custom-overlay');
        overlay.innerHTML = `
    <div class="overlay-content">
      <p>There is already an instance of the GUI opened on this machine.<br>
         Do you want to disconnect the other instance?</p>
      <div class="overlay-buttons">
        <button id="disconnect-btn">Use this instance</button>
        <button id="close-btn">Use the other instance</button>
      </div>
    </div>`;
        document.body.appendChild(overlay);

        document.getElementById('disconnect-btn').onclick = () => {
            // send a “disconnect_other” event back to Python
            this.websocket.send({
                type: 'event',
                x: 25,
                id: this.id,
                data: {event: 'disconnect_other', id: this.id}
            });
            this._removeOverlay('choose-overlay');
        };
        document.getElementById('close-btn').onclick = () => {
            this._removeOverlay('choose-overlay');
            this.close()
            this.closeWindow();
        };
    }


    _showDisconnectedOverlay() {
        if (document.getElementById('disconnected-overlay')) return;

        const overlay = document.createElement('div');
        overlay.id = 'disconnected-overlay';
        overlay.classList.add('custom-overlay');
        overlay.innerHTML = `
            <div class="overlay-content disconnected">
      <img src="bilbolab_logo.png" alt="Logo" class="disconnected-logo">
      <p>This GUI instance has been disconnected.</p>
        <p>You can close this window now.</p>
    </div>`;
        document.body.appendChild(overlay);


    }

    // =================================================================================================================
    _handleFrontendChooseMessage(msg) {
        this._showChooseOverlay();
    }

    // =================================================================================================================
    _emergencyStop() {
        // Get the <img> inside the button
        const stopIcon = this.stopButton.querySelector('.stop-icon');
        if (!stopIcon) return;

        // Remove previous animation class if needed
        stopIcon.classList.remove('activated');

        // Force reflow to allow re-triggering animation
        void stopIcon.offsetWidth;

        // Add animation class
        stopIcon.classList.add('activated');

        // Listen for animation end to clean up
        const onAnimationEnd = () => {
            stopIcon.classList.remove('activated');
            stopIcon.removeEventListener('animationend', onAnimationEnd);
        };

        stopIcon.addEventListener('animationend', onAnimationEnd);


        this.showEmergencyStopOverlay();

        const message = {
            type: 'event',
            id: this.id,
            data: {event: 'emergency_stop', id: this.id}
        }

        this.websocket.send(message);
    }

    // =================================================================================================================
    showEmergencyStopOverlay() {
        // 1) create the overlay
        const overlay = document.createElement('div');
        overlay.id = 'emergency-stop-overlay';
        overlay.className = 'emergency-stop-overlay';
        overlay.textContent = 'Emergency Stop!';
        document.body.appendChild(overlay);

        // 2) trigger the fade-in in the next frame
        requestAnimationFrame(() => {
            overlay.classList.add('visible');
        });

        // 3) after 2 s, fade out
        setTimeout(() => {
            overlay.classList.remove('visible');
            // 4) when the fade-out transition ends, remove from DOM
            overlay.addEventListener('transitionend', () => overlay.remove(), {once: true});
        }, 2000);
    }

    // =================================================================================================================
    /**
     * Opens a file picker dialog and sends the selected file back to Python.
     * This method is called from Python via gui.function('openFilePicker', {...})
     *
     * @param {Object} options - Options for the file picker
     * @param {string} options.request_id - Unique ID to match request with response
     * @param {string} options.accept - File type filter (e.g., '.yaml,.yml')
     * @param {string} options.title - Title for the dialog (informational only)
     */
    async openFilePicker(options = {}) {
        const requestId = options.request_id;

        try {
            const fileData = await openFilePicker({
                accept: options.accept || '',
                multiple: false,
                maxSize: options.max_size || 0
            });

            // Send response back to Python
            this.websocket.send({
                type: 'event',
                id: this.id,
                data: {
                    event: 'file_picker_response',
                    request_id: requestId,
                    success: fileData !== null,
                    file: fileData
                }
            });
        } catch (error) {
            console.error('File picker error:', error);
            this.websocket.send({
                type: 'event',
                id: this.id,
                data: {
                    event: 'file_picker_response',
                    request_id: requestId,
                    success: false,
                    error: error.message
                }
            });
        }
    }

    // =================================================================================================================
    /**
     * Triggers a file download on the client.
     * Called from Python via gui.function('downloadFile', {...})
     *
     * @param {Object} options - Options for the download
     * @param {string} options.filename - Name for the downloaded file
     * @param {string} options.content - Base64-encoded file content
     * @param {string} options.mimeType - MIME type of the file
     */
    downloadFile(options = {}) {
        try {
            const { filename, content, mimeType } = options;

            if (!filename || !content) {
                console.error('downloadFile: missing filename or content');
                return;
            }

            // Decode base64 content
            const byteCharacters = atob(content);
            const byteNumbers = new Array(byteCharacters.length);
            for (let i = 0; i < byteCharacters.length; i++) {
                byteNumbers[i] = byteCharacters.charCodeAt(i);
            }
            const byteArray = new Uint8Array(byteNumbers);
            const blob = new Blob([byteArray], { type: mimeType || 'application/octet-stream' });

            // Create download link and trigger click
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();

            // Cleanup
            setTimeout(() => {
                document.body.removeChild(link);
                URL.revokeObjectURL(url);
            }, 100);

            console.log(`Download triggered: ${filename}`);
        } catch (error) {
            console.error('downloadFile error:', error);
        }
    }

    // =================================================================================================================
    /**
     * Copies text to the clipboard.
     * Called from Python via gui.function('copyToClipboard', {...})
     *
     * @param {Object} options
     * @param {string} options.text - The text to copy
     */
    copyToClipboard(options = {}) {
        const text = options.text || '';
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        console.log('Copied to clipboard');
    }

    // =================================================================================================================
    _onWindowKeyDown(e) {

        if (document.activeElement !== document.body) return;

        // Return on F12 because this opens up the console
        if (e.key === 'F12') {
            // e.preventDefault();
            return;
        }

        e.preventDefault();

        switch (e.code) {
            case 'Space':
                if (!this._enableEmergencyStop) break;
                if (!this._emergencyArmed) {
                    this._armEmergencyStop();
                } else {
                    this._triggerEmergencyStop();
                }
                break;
        }


    }

    // -----------------------------------------------------------------------------------------------------------------
    _armEmergencyStop() {
        this._emergencyArmed = true;
        this.stopButton.classList.add('armed');
        // auto-disarm after 3s
        this._armTimeoutId = setTimeout(() => {
            this._disarmEmergencyStop();
        }, 3000);
    }

    // -----------------------------------------------------------------------------------------------------------------
    _disarmEmergencyStop() {
        this._emergencyArmed = false;
        clearTimeout(this._armTimeoutId);
        this.stopButton.classList.remove('armed');
    }

    // -----------------------------------------------------------------------------------------------------------------
    _triggerEmergencyStop() {
        // clear the pending auto-disarm
        this._disarmEmergencyStop();
        // call your existing click handler
        this._emergencyStop();
    }
}

