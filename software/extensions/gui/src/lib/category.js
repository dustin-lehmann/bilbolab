import {ButtonWidget} from './objects/js/buttons.js';
import {ContextMenuItem} from './objects/contextmenu.js';
import {Widget} from './objects/objects.js';
import {WidgetGroup} from './objects/group.js';
import {activeGUI} from './globals.js';
import {Callbacks, isObject, splitPath, writeToLocalStorage} from './helpers.js';
import {Page} from './page.js';


export class CategoryButton extends Widget {
    constructor(id, category, data = {}) {

        super(id, data);
        const CATEGORY_BTN_DEFAULTS = {
            name: '',
            icon: null,
            top_icon: null,
            text_color: 'rgba(255,255,255,0.7)',
        };

        this.configuration = {...CATEGORY_BTN_DEFAULTS, ...this.configuration};

        this.category = category;

        this.callbacks.add('click');

        // build the actual <button> element
        this.element = document.createElement('button');
        this.element.classList.add('category-button', 'not-selected');
        this.element.style.color = this.configuration.text_color;

        // left icon slot
        this.iconSlot = document.createElement('span');
        this.iconSlot.className = 'category-button__icon';
        if (this.configuration.icon) {
            if (/\.(png|jpe?g|svg)$/i.test(this.configuration.icon)) {
                const img = document.createElement('img');
                img.src = this.configuration.icon;
                this.iconSlot.appendChild(img);
            } else {
                this.iconSlot.textContent = this.configuration.icon;
            }
        }
        this.element.appendChild(this.iconSlot);

        // text
        this.textSpan = document.createElement('span');
        this.textSpan.className = 'category-button__text';
        this.textSpan.textContent = this.configuration.name;
        this.element.appendChild(this.textSpan);

        // top-right icon (e.g. ❗)
        if (this.configuration.top_icon) {
            this.topSlot = document.createElement('span');
            this.topSlot.className = 'category-button__top-icon';
            this.topSlot.textContent = this.configuration.top_icon;
            this.element.appendChild(this.topSlot);
        }

        // attach GUI_Object context‐menu machinery + your click handler
        this.assignListeners(this.element);

        // Add to favorites for categories
        const favorites_context_menu_item = new ContextMenuItem('favorites',
            {name: 'Add to favorites', front_icon: '⭐'})

        this.addItemToContextMenu(favorites_context_menu_item);
        favorites_context_menu_item.callbacks.get('click').register(this.onFavoritesClick.bind(this));
    }

    onFavoritesClick() {
        activeGUI.addShortcut(this.category);
    }

    /** required by GUI_Object */
    getElement() {
        return this.element;
    }

    /** retains the old "selected" / "not‐selected" styling */
    setSelected(selected) {
        this.element.classList.toggle('selected', selected);
        this.element.classList.toggle('not-selected', !selected);
    }

    /** fires the usual Category.setCategory */
    onClick() {
        console.log('CategoryButton clicked');
        this.callbacks.get('click').call(this.category);
        activeGUI.setCategory(this.category.id);
        // Save the first page into local storage
        const firstPage = Object.values(this.category.pages)[0];
        if (firstPage) {
            this.category.setPage(firstPage.id);
            writeToLocalStorage(`${activeGUI.id}_active_page`, firstPage.id);
        } else {
            console.warn(`Category "${this.category.id}" has no pages to select.`);
        }
    }

    /** if you ever need to update name / icon at runtime */
    updateConfig(cfg) {
        if (cfg.name != null) this.textSpan.textContent = cfg.name;
        if (cfg.icon != null) this.iconSlot.textContent = cfg.icon;
        if (cfg.top_icon != null) {
            if (!this.topSlot) {
                this.topSlot = document.createElement('span');
                this.topSlot.className = 'category-button__top-icon';
                this.element.appendChild(this.topSlot);
            }
            this.topSlot.textContent = cfg.top_icon;
        }
    }

    assignListeners(element) {
        super.assignListeners(element);
        element.addEventListener('click', this.onClick.bind(this));
    }

    update(data) {
    }

    initializeElement() {
    }

    resize() {
    }
}


class CategoryHeadbar extends WidgetGroup {
    constructor(id, payload = {}) {
        super(id, payload);
    }
}

/* ================================================================================================================== */
export class Category {

    /** @type {Object<string,Page>} */
    pages = {};

    /** @type {Page|null} */
    page = null;

    /** @type {Object<string,Category>} */
    categories = {};

    /** @type {Callbacks} */
    callbacks = null;

    /** @type {Object} */
    configuration = {};

    /** @type {string} */
    id = '';

    /** @type {CategoryButton|null} */
    button = null;

    /** @type {Object<number,HTMLElement|null>} */
    page_buttons = {};

    /** @type {HTMLElement|null} */
    page_grid = null;

    /** @type {HTMLElement|null} */
    content_grid = null;


    /**
     * @param {string} id
     * @param {Object} [configuration={}]
     * @param {Object} [pages={}]         – map of page-definitions
     * @param {Object} [categories={}]    – map of subcategory-definitions
     * @param headbar_payload
     * @param bottom_group_payload
     */
    constructor(id, configuration = {}, pages = {}, categories = {}, headbar_payload = {}, bottom_group_payload = null) {
        this.id = id;

        const default_configuration = {
            name: id,
            collapsed: false,
            color: 'rgba(40,40,40,0.7)',
            text_color: 'rgba(255,255,255,0.7)',
            icon: null,
            top_icon: null,
            number_of_pages: +getComputedStyle(document.documentElement).getPropertyValue('--page_bar-cols'),
            max_pages: +getComputedStyle(document.documentElement).getPropertyValue('--page_bar-cols'),
        };

        this.configuration = {...default_configuration, ...configuration};
        this.parent = null;

        this.callbacks = new Callbacks();
        this.callbacks.add('event');
        this.pages = {};
        this.categories = {};
        this.page = null;

        // main button for this category
        this.button = this._generateButton();

        // slots for page-buttons
        this.page_buttons = {};
        for (let i = 0; i < this.configuration.number_of_pages; i++) {
            this.page_buttons[i] = null;
        }

        // container for page buttons
        this._createPageGrid();

        this.headbar = new CategoryHeadbar(headbar_payload.id, headbar_payload);
        this.headbar.callbacks.get('event').register(this.onEvent.bind(this))

        // Optional per-category bottom group
        if (bottom_group_payload) {
            this.bottom_group = new WidgetGroup(bottom_group_payload.id, bottom_group_payload);
            this.bottom_group.callbacks.get('event').register(this.onEvent.bind(this));
        } else {
            this.bottom_group = null;
        }

        // build out any initially defined pages & categories
        if (Object.keys(pages).length > 0) {
            this.buildPagesFromDefinition(pages);
        }
        if (Object.keys(categories).length > 0) {
            this.buildCategoriesFromDefinition(categories);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    /**
     * Look up something by path, descending into sub-categories first, then pages.
     * Now supports absolute UIDs that include the reserved "categories" keyword.
     * @param {string} path
     * @returns {Category|Page|CategoryHeadbar|null}
     */
    getObjectByPath(path) {
        const [firstSegment, remainder] = splitPath(path);
        if (!firstSegment) return null;

        // if the path explicitly includes the "categories" keyword,
        // treat the next segment as a subcategory ID
        if (firstSegment === 'categories') {
            // e.g. path = "categories/subcat1/…"
            const [catName, nextRemainder] = splitPath(remainder);
            if (!catName) return null;
            const fullKey = `${this.id}/categories/${catName}`;
            const subCat = this.categories[fullKey];
            if (!subCat) return null;
            return nextRemainder
                ? subCat.getObjectByPath(nextRemainder)
                : subCat;
        } else if (firstSegment === 'headbar') {
            if (!remainder) return this.headbar;
            return this.headbar.getObjectByPath(remainder);
        } else if (firstSegment === 'bottom_group') {
            if (!this.bottom_group) return null;
            if (!remainder) return this.bottom_group;
            return this.bottom_group.getObjectByPath(remainder);
        }

        // otherwise fall back to legacy behavior
        const fullKey = `${this.id}/${firstSegment}`;

        // 1) Sub-category?
        const subCat = this.categories[fullKey];
        if (subCat) {
            if (!remainder) return subCat;
            return subCat.getObjectByPath(remainder);
        }

        // 2) Page?
        const page = this.pages[fullKey];
        if (page) {
            if (!remainder) return page;
            return page.getObjectByPath(remainder);
        }

        return null;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    getGUI() {
        if (this.parent instanceof Category) {
            return this.parent.getGUI();
        } else if (this.parent && typeof this.parent.getObjectByUID === 'function') {
            return this.parent;  // Must be the GUI root
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    update(data) {
        console.warn('Category update is not yet implemented.');
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    handleAddMessage(data) {

        const object_type = data.type

        switch (object_type) {
            case 'page':
                this.buildPageFromDefinition(data.config);
                break;
            case 'category':
                this.buildCategoryFromDefinition(data.config);

                const gui = this.getGUI();
                if (gui) {
                    gui.renderCategoryTree();
                }
                break;
            case 'bottom_group_widget':
                if (this.bottom_group) {
                    this.bottom_group.handleAddMessage(data);
                }
                break;
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    handleRemoveMessage(data) {
        const object_type = data.type

        switch (object_type) {
            case 'page':
                const page_id = data.id
                const page = this.pages[page_id]
                if (page) {

                    // Remove the page's button
                    page.button.remove()
                    page.grid.remove()
                    delete this.pages[page_id]

                    // Switch active page
                    if (this.page === page) {
                        // check the length of the this.pages array. If bigger than 0, then choose the first one
                        if (Object.keys(this.pages).length > 0) {
                            this.setPage(Object.keys(this.pages)[0])
                        } else {
                            // if the length is 0, then set the page to null
                            this.setPage(null)
                        }
                    }

                }
                break;
            case 'category':
                const category_id = data.id;
                const category = this.categories[category_id];
                if (category) {
                    // category.content_grid.remove()
                    delete this.categories[category_id];
                    // Switch active category if it was this category

                    if (isObject(category.id, this.getGUI().category.id)) {
                        this.getGUI().setCategory(this.id);
                    }


                    this.getGUI().renderCategoryTree();
                }
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Build multiple pages from a definition map
     * @param {Object<string,*>} pages
     */
    buildPagesFromDefinition(pages) {
        for (const [_, config] of Object.entries(pages)) {
            this.buildPageFromDefinition(config);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Build a single page from its definition and add it
     * @param {{id:string, config:Object, objects:Object, position?:number}} page_definition
     */
    buildPageFromDefinition(page_definition) {
        const new_page = new Page(
            page_definition.id,
            page_definition.config,
            page_definition.objects
        );
        this.addPage(new_page, page_definition.position);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Build multiple subcategories from a definition map
     * @param {Object<string,*>} categories
     */
    buildCategoriesFromDefinition(categories) {
        for (const [_, config] of Object.entries(categories)) {
            this.buildCategoryFromDefinition(config);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Build a single subcategory from its definition and add it
     * @param {{id:string, config:Object, pages:Object, categories:Object, position?:number}} cat_definition
     */
    buildCategoryFromDefinition(cat_definition) {
        const new_category = new Category(
            cat_definition.id,
            cat_definition.config,
            cat_definition.pages || {},
            cat_definition.categories || {},
            cat_definition.headbar || {},
            cat_definition.bottom_group || null
        );
        this.addCategory(new_category, cat_definition.position);
    }


    /* -------------------------------------------------------------------------------------------------------------- */
    _generateButton() {
        return new CategoryButton(this.id,
            this,
            {
                config: {
                    name: this.configuration.name,
                    icon: this.configuration.icon,
                    top_icon: this.configuration.top_icon,
                    text_color: this.configuration.text_color
                }
            }
        );
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _createPageGrid() {
        this.page_grid = document.createElement('div');
        this.page_grid.id = `page_${this.id}_grid`;
        this.page_grid.className = 'page_bar_grid';
    }


    hidePages() {
        Object.values(this.pages).forEach(pg => {
            pg.grid.style.display = 'none';
        });
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Add a ControlGUI_Page to this category
     * @param {Page} page
     * @param {number|null} position
     */
    addPage(page, position = null) {
        if (this.pages[page.id]) {
            console.warn(`Page with ID "${page.id}" already exists in category "${this.id}".`);
            return;
        }

        // find or validate slot
        if (position !== null) {
            if (this.page_buttons[position - 1] !== null) {
                console.warn(`Position ${position} already used in category "${this.id}".`);
                return;
            }
        } else {
            for (let i = 1; i <= this.configuration.number_of_pages; i++) {
                if (this.page_buttons[i - 1] === null) {
                    position = i;
                    break;
                }
            }
            if (position === null) {
                console.warn(`No free page slots in category "${this.id}".`);
                return;
            }
        }

        // wire up button
        this.page_buttons[position - 1] = page.button;
        // const button_element = page.button.getElement();
        // button_element.style.gridRow = '1';
        // button_element.style.gridColumn = String(position);
        // this.page_grid.appendChild(button_element);
        page.button.attach(this.page_grid, [1, position], [1, 1]);
        page.button.on('click', () => this.setPage(page.id));


        // register
        this.pages[page.id] = page;
        page.parent = this;
        page.callbacks.get('event').register(this.onEvent.bind(this));

        // Add the pages grid to my content grid
        if (this.content_grid) {
            // only attach it if it isn't already in the DOM
            if (page.grid.parentNode !== this.content_grid) {
                this.content_grid.appendChild(page.grid);
            }
            Object.assign(page.grid.style, {
                position: 'absolute',
                top: '0',
                left: '0',
                width: '100%',
                height: '100%',
                display: 'none',
            });
        }

        // if first page, show it
        if (this.page === null) {
            this.setPage(page.id);
        }
    }


    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Add a ControlGUI_Category as a nested subcategory
     * @param {Category} category
     * @param {number|null} position   – currently unused for UI
     */
    addCategory(category, position = null) {
        if (this.categories[category.id]) {
            console.warn(`Category with ID "${category.id}" already exists under "${this.id}".`);
            return;
        }
        this.categories[category.id] = category;
        category.parent = this;
        category.callbacks.get('event').register(this.onEvent.bind(this));

    }


    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Render page-buttons into `container` and absolutely‐position all page.grids
     * (unchanged from before)
     */
    buildCategory(page_bar_container, headbar_container, content_grid) {

        const gui = this.getGUI();
        // 1) collapse or show the entire page‐bar row
        if (gui) {
            gui.showPageBar(this.configuration.max_pages > 1);
        }
        // 2) populate (or clear) the page‐bar itself
        page_bar_container.innerHTML = '';
        if (this.configuration.max_pages > 1) {
            page_bar_container.style.display = '';
            page_bar_container.appendChild(this.page_grid);
        } else {
            // we've already hidden the <nav>, but just in case:
            page_bar_container.style.display = 'none';
        }


        // 3) Set the headbar
        headbar_container.innerHTML = '';
        headbar_container.appendChild(this.headbar.element);


        this.content_grid = content_grid;
        this.content_grid.style.position = 'relative';

        Object.values(this.pages).forEach(page => {
            if (page.grid.parentNode !== this.content_grid) {
                this.content_grid.appendChild(page.grid);
                Object.assign(page.grid.style, {
                    position: 'absolute',
                    top: '0',
                    left: '0',
                    width: '100%',
                    height: '100%',
                    display: 'none',
                });
            } else {
                page.grid.style.display = 'none';
            }
        });

        const startId = this.page ? this.page.id : Object.keys(this.pages)[0];
        if (startId) this.setPage(startId);
        else this._renderEmpty(page_bar_container, content_grid);
    }

    _renderEmpty(container, content_grid) {
        content_grid.innerHTML = '';
    }


    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Switch visible page (unchanged)
     * @param {string|Page} pageOrId
     */
    setPage(pageOrId) {
        const id = pageOrId instanceof Page ? pageOrId.id : pageOrId;
        const page = this.pages[id];
        if (!page) {
            console.warn(`Page "${id}" not found in category "${this.id}".`);
            return;
        }

        Object.values(this.pages).forEach(p => {
            p.grid.style.display = 'none';
            p.button.deselect();
        });

        page.grid.style.display = 'grid';
        page.button.select();
        window.dispatchEvent(new Event('resize'));
        this.page = page;

    }


    /* -------------------------------------------------------------------------------------------------------------- */
    onEvent(event) {
        this.callbacks.get('event').call(event);
    }
}

export {CategoryHeadbar};
