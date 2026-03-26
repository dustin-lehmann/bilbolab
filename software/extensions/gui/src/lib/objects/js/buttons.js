import {Widget} from "../objects.js";
import {
    getColor, shadeColor, interpolateColors, Callbacks, getVerticalFittingFontSizeSingleContainer,
    getFittingFontSizeSingleContainer
} from "../../helpers.js";

export class ButtonWidget extends Widget {
    constructor(id, data = {}) {
        super(id, data);

        const default_configuration = {
            visible: true,
            color: 'rgba(50,50,50,0.81)',
            text_color: '#ffffff',
            font_size: 10,              // in pt
            text: '',
            text_position: 'center',    // 'center' | 'top' | 'bottom'
            icon: '',                   // main icon
            icon_size: 40,              // in pt
            top_icon: '',               // small corner icon
            top_icon_alignment: 'right',// 'left' | 'right'
            top_icon_size: 10,          // in pt
            border_style: 'solid',      // 'solid' | 'dashed' | 'dotted' | 'double'
            border_width: 2,            // in px
            adjust_icon_size: true,     // adjust icon size to fit text size
            image: null,                // background image (URL/base64)
            image_width: '100%',        // max width of the bg image relative to the button
            image_height: '100%',       // max height of the bg image relative to the button
            image_opacity: 1.0,         // opacity of the background image (0..1)
        };

        this.configuration = {...default_configuration, ...this.configuration};

        // Long-click, double-click, and press-feedback state (unchanged) …
        this.longClickTimer = null;
        this.longClickThreshold = 800;
        this.longClickFired = false;

        this.clickTimer = null;
        this.clickDelay = 200;

        this.minPressDuration = 100;
        this._pressedTimestamp = 0;
        this._removePressedTimeout = null;

        // timing for touch double-tap
        this.doubleTapThreshold = 300;     // ms, you can tweak this up/down
        this.lastTapTime = 0;
        this.tapTimeout = null;

        // Create the button element
        this.element = document.createElement('div');
        this.element.id = this.id;

        this.configureElement(this.element);
        this.assignListeners(this.element);

        this.callbacks.add('click');
        this.callbacks.add('rightclick');
    }

    _escapeAttr(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    configureElement(element) {
        super.configureElement(element);

        const {
            text,
            icon,
            icon_size,
            top_icon,
            top_icon_alignment,
            top_icon_size,
            text_position,
            color,
            text_color,
            font_size,
            border_style,
            border_width,
            visible,
            image,
            image_width,
            image_height,
            image_opacity,
        } = this.configuration;

        // Set inline styles for colors, font, border
        element.style.backgroundColor = getColor(color);
        element.style.color = getColor(text_color);

        if (text_position === 'center') {
            element.style.fontSize = `${font_size}pt`;
        }

        element.style.borderStyle = border_style;
        element.style.borderWidth = `${border_width}px`;

        // Set visibility
        element.style.display = visible ? '' : 'none';

        // Custom properties for CSS sizing
        element.style.setProperty('--icon-size', `${icon_size}pt`);
        element.style.setProperty('--top-icon-size', `${top_icon_size}pt`);
        element.style.setProperty('--image-width', image_width || '100%');
        element.style.setProperty('--image-height', image_height || '100%');

        // Data attributes for CSS selectors
        element.dataset.textPosition = text_position;
        element.dataset.topIconAlignment = top_icon_alignment;

        // Build inner HTML
        let html = '';

        // Background image layer (non-interactive, behind content)
        if (image) {
            const esc = this._escapeAttr(image);
            const opStyle = image_opacity < 1 ? ` style="opacity:${image_opacity}"` : '';
            html += `
                <div class="buttonBg" aria-hidden="true"${opStyle}>
                    <img class="buttonBgImg" src="${esc}" alt="">
                </div>
            `;
        }

        if (top_icon) {
            html += `<div class="buttonTopIcon">${top_icon}</div>`;
        }
        if (icon) {
            html += `<div class="buttonIcon">${icon}</div>`;
        }
        html += `<div class="buttonLabel">${this._escapeAttr(text)}</div>`;

        element.classList.add('widget', 'highlightable', 'buttonItem');
        if (image) element.classList.add('hasImage');
        element.innerHTML = html;
    }

    _adjustIconSize() {
        // wait until DOM has laid out sizes
        const iconDiv = this.element.querySelector('.buttonIcon');
        requestAnimationFrame(() => {
            // getFittingFontSizeSingleContainer(iconDiv, 10, 10, 50, 5);
            const size = getFittingFontSizeSingleContainer(iconDiv, 0, 0, 100, 0);
        });
    }

    getElement() {
        return this.element;
    }

    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement(this.element);
    }

    update(data) {
        // your update logic…
    }

    assignListeners(element) {
        super.assignListeners(element);
        // ─────── DESKTOP: single vs. double click ───────
        element.addEventListener('click', (event) => {
            if (event.button !== 0) return;
            if (this.longClickFired) {
                this.longClickFired = false;
                return;
            }
            if (event.detail === 1) {
                this.clickTimer = setTimeout(() => {
                    this.handleClick();
                    this.clickTimer = null;
                }, this.clickDelay);
            } else if (event.detail === 2) {
                if (this.clickTimer) {
                    clearTimeout(this.clickTimer);
                    this.clickTimer = null;
                }
            }
        });

        element.addEventListener('dblclick', () => {
            if (this.clickTimer) {
                clearTimeout(this.clickTimer);
                this.clickTimer = null;
            }
            this.handleDoubleClick();
        });

        // ─────── DESKTOP: long-press with mouse ───────
        element.addEventListener('mousedown', (event) => {
            if (event.button !== 0) return;
            this.longClickFired = false;
            this.longClickTimer = setTimeout(() => {
                this.handleLongClick();
                this.longClickFired = true;
            }, this.longClickThreshold);
        });
        ['mouseup', 'mouseleave'].forEach(evt =>
            element.addEventListener(evt, (event) => {
                if (event.button !== 0) return;
                if (this.longClickTimer) {
                    clearTimeout(this.longClickTimer);
                    this.longClickTimer = null;
                }
            })
        );

        // ─────── MOBILE: long-press ───────
        element.addEventListener('touchstart', (event) => {
            // Prevent default
            event.preventDefault();
            element.classList.add('pressed');

            this.longClickFired = false;
            this.longClickTimer = setTimeout(() => {
                this.handleLongClick();
                this.longClickFired = true;
            }, this.longClickThreshold);
        }, {passive: false});
        ['touchend', 'touchcancel'].forEach(evt =>
            element.addEventListener(evt, () => {
                element.classList.remove('pressed');
                if (this.longClickTimer) {
                    clearTimeout(this.longClickTimer);
                    this.longClickTimer = null;
                }
            })
        );

        // ─────── MOBILE: single-tap vs. double-tap ───────
        element.addEventListener('touchend', (event) => {
            // if long-press just fired, swallow
            if (this.longClickFired) {
                this.longClickFired = false;
                return;
            }

            // stop the built-in click firing
            event.preventDefault();

            const now = Date.now();
            if (this.lastTapTime && (now - this.lastTapTime) < this.doubleTapThreshold) {
                // double-tap!
                clearTimeout(this.tapTimeout);
                this.tapTimeout = null;
                this.lastTapTime = 0;
                this.handleDoubleClick();
            } else {
                // first tap: wait to see if a second comes
                this.lastTapTime = now;
                this.tapTimeout = setTimeout(() => {
                    this.handleClick();
                    this.tapTimeout = null;
                    this.lastTapTime = 0;
                }, this.doubleTapThreshold);
            }
        }, {passive: false});

        // if touch is cancelled, clean up pending single-tap
        element.addEventListener('touchcancel', (event) => {
            if (this.tapTimeout) {
                clearTimeout(this.tapTimeout);
                this.tapTimeout = null;
                this.lastTapTime = 0;
            }
        }, {passive: false});

        // ─────── PRESSED-FEEDBACK (pointer events) ───────
        element.addEventListener('pointerdown', (evt) => {
            if (!evt.isPrimary) return;
            if (evt.pointerType === 'mouse' && evt.button !== 0) return;

            this._pressedTimestamp = performance.now();
            if (this._removePressedTimeout) {
                clearTimeout(this._removePressedTimeout);
                this._removePressedTimeout = null;
            }
            element.classList.add('pressed');
        });

        element.addEventListener('pointerup', () => {
            const elapsed = performance.now() - this._pressedTimestamp;
            const rem = this.minPressDuration - elapsed;
            if (rem > 0) {
                this._removePressedTimeout = setTimeout(() => {
                    element.classList.remove('pressed');
                    this._removePressedTimeout = null;
                }, rem);
            } else {
                element.classList.remove('pressed');
            }
        });

        element.addEventListener('pointerleave', () => {
            if (this._removePressedTimeout) {
                clearTimeout(this._removePressedTimeout);
                this._removePressedTimeout = null;
            }
            element.classList.remove('pressed');
        });
    }

    handleClick() {
        this.callbacks.get('event').call({id: this.id, event: 'click', data: {}});
        this.callbacks.get('click').call();
        this.emit('click');
    }

    handleDoubleClick() {
        this.callbacks.get('event').call({id: this.id, event: 'doubleClick', data: {}});
    }

    handleLongClick() {
        this.callbacks.get('event').call({id: this.id, event: 'longClick', data: {}});
    }

    handleRightClick(event) {
        this.callbacks.get('event').call({id: this.id, event: 'rightClick', data: {}});
        this.callbacks.get('rightclick').call({event: event});
    }

    openUrl(url, features) {
        if (url) {
            const fullUrl = new URL(url, window.location.origin);
            window.open(fullUrl.href, '_blank', features || 'noopener');
        }
    }

    initializeElement() {
    }

    resize() {
        this._adjustIconSize();
    }
}


// === MULTI STATE BUTTON ==============================================================================================

export class MultiStateButtonWidget extends Widget {
    constructor(id, config = {}) {
        super(id, config);

        const defaults = {
            visible: true,
            color: [0.2, 0.3, 0.4],
            text_color: '#fff',
            states: [],
            state_index: 0,
            text: '',
            title: '',
            font_size: 14,
            title_font_size: 14
        };

        this.configuration = {...defaults, ...this.configuration};
        this.element = this.initializeElement();
        this.configureElement(this.element);
        this._attachIndicatorListeners();
        this.assignListeners(this.element);

        this.callbacks.add('click');

    }

    /* ============================================================================================================== */
    initializeElement() {
        const element = document.createElement('button');
        element.id = this.id;
        element.classList.add('widget', 'buttonItem', 'highlightable', 'multiStateButton');

        this.title = document.createElement('div');
        this.title.classList.add('title');
        this.title.textContent = this.configuration.title;
        element.appendChild(this.title);

        this.state = document.createElement('div');
        this.state.classList.add('state');
        element.appendChild(this.state);

        this.indicators = document.createElement('div');
        this.indicators.classList.add('indicators');
        element.appendChild(this.indicators);

        // Add indicators dynamically
        this.configuration.states.forEach((stateName, i) => {
            const indicator = document.createElement('div');
            indicator.classList.add('msbIndicator');
            indicator.dataset.index = i;
            indicator.dataset.tooltip = stateName;
            this.indicators.appendChild(indicator);
        })

        return element;
    }

    /* ============================================================================================================== */
    configureElement(element) {
        super.configureElement(element);

        // clamp index
        this.configuration.state_index = Math.max(0, Math.min(this.configuration.states.length - 1, this.configuration.state_index));
        // derive label
        this.configuration.state = this.configuration.states.length ? this.configuration.states[this.configuration.state_index] : '';

        this.state.textContent = this.configuration.state;


        if (!this.configuration.visible) this.element.style.display = 'none';
        this.element.style.color = getColor(this.configuration.text_color);
        this.element.style.backgroundColor = getColor(this._getCurrentColor());

        // Mark all indicators as inactive
        this.indicators.querySelectorAll('.msbIndicator').forEach(indicator => {
            indicator.classList.remove('active');
        })
        // Mark the correct indicator as active
        const activeIndicator = this.indicators.querySelector(`.msbIndicator[data-index="${this.configuration.state_index}"]`);
        if (activeIndicator) {
            activeIndicator.classList.add('active');
        }

        this.resize();
    }

    /* ============================================================================================================== */
    assignListeners(el) {
        super.assignListeners(el);
        el.addEventListener('click', () => this._handleClick());
    }

    /* ============================================================================================================== */


    getElement() {
        return this.element;
    }

    /* ============================================================================================================== */
    /** returns either a single color or the per-state color */
    _getCurrentColor() {
        const {color, state_index, states} = this.configuration;

        if (!Array.isArray(color)) {
            return color;
        }

        // Check if it's an array of strings (like ['#fff', '#000'])
        if (typeof color[0] === 'string') {
            return color[state_index % color.length];
        }

        // Check if it's an array of arrays (like [[r,g,b], [r,g,b]])
        if (Array.isArray(color[0])) {
            return color[state_index % color.length];
        }

        // If it's just a single color as array of floats (like [r, g, b])
        if (typeof color[0] === 'number') {
            return color;
        }

        // Fallback (should not happen)
        return [0.5, 0.5, 0.5]; // default grey
    }

    /* ============================================================================================================== */

    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement(this.element);
        this._attachIndicatorListeners();
    }

    /* ============================================================================================================== */
    update(data) {


    }


    /* ============================================================================================================== */
    _attachIndicatorListeners() {
        this.element.querySelectorAll('.msbIndicator').forEach(dot => {
            dot.addEventListener('click', e => {
                e.stopPropagation();
                const idx = parseInt(dot.getAttribute('data-index'), 10);
                this._handleIndicatorClick(idx);
            });
        });
    }

    /* ============================================================================================================== */
    _handleClick() {
        this.callbacks.get('event').call({
            id: this.id,
            event: 'click',
            data: {},
        });

        this.callbacks.get('click').call();
    }

    /* ============================================================================================================== */
    _handleIndicatorClick(idx) {
        this.callbacks.get('event').call({
            id: this.id,
            event: 'indicatorClick',
            data: {index: idx},
        });
    }

    /* ============================================================================================================== */

    resize() {
        getFittingFontSizeSingleContainer(this.state,
            0,
            0,
            this.configuration.font_size, 3);

        getFittingFontSizeSingleContainer(this.title,
            0,
            0,
            100, 0);
    }
}