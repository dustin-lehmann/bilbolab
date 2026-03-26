import {getColor, getVerticalFittingFontSizeSingleContainer, getFittingFontSizeSingleContainer} from "../../helpers.js";
import {Widget} from "../objects.js";
import {ContextMenuItem} from "../contextmenu.js";


/* === STATUS WIDGET ================================================================================================ */
export class StatusWidget extends Widget {
    constructor(id, config = {}) {
        super(id, config);

        const defaults = {
            text_color: '#000',
            title: null,
            font_size: 10,          // interpreted as pixels
            elements: {}            // { key: { label, color, status, label_color, status_color }, … }
        }

        this.configuration = {...defaults, ...this.configuration};
        this._elements = {}
        this.element = this.initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);

        // Add resize listener
        window.addEventListener('resize', () => this.resize());
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    initializeElement() {
        const el = document.createElement('div');
        el.id = this.id;
        el.classList.add('widget', 'highlightable', 'statusWidget');


        // TODO: For now assume elements is static in length, so the number of rows is fixed
        //       (but this could be improved by using a table instead of a div)

        const rowTemplate = Array(Object.keys(this.configuration.elements).length).fill('1fr').join(' ');
        el.style.setProperty('--number-of-rows', rowTemplate);

        for (let i = 0; i < Object.keys(this.configuration.elements).length; i++) {
            const status_element = document.createElement('div');
            status_element.classList.add('statusWidgetElement');
            el.appendChild(status_element);

            // Circle
            const circle = document.createElement('div');
            circle.classList.add('statusCircle');
            circle.style.backgroundColor = getColor(this.configuration.elements[Object.keys(this.configuration.elements)[i]].color);
            status_element.appendChild(circle);

            // Name
            const name = document.createElement('div');
            name.classList.add('statusName');
            name.textContent = "NAME"
            status_element.appendChild(name);

            // Value
            const value = document.createElement('div');
            value.classList.add('statusValue');
            value.textContent = "VALUE"
            status_element.appendChild(value);

            this._elements[Object.keys(this.configuration.elements)[i]] = {
                element: status_element,
                circle: circle,
                name: name,
                value: value,
            };
        }

        return el;
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    /* -------------------------------------------------------------------------------------------------------------- */
    resize() {
        // Loop through all elements and resize them
        for (let i = 0; i < Object.keys(this.configuration.elements).length; i++) {
            const element = this._elements[Object.keys(this.configuration.elements)[i]];

            const font_size = getVerticalFittingFontSizeSingleContainer(element.name, 0, 14, 3);
            element.value.style.fontSize = `${font_size}px`;


        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    configureElement(element = this.element) {
        super.configureElement(element);

        // Loop through all elements and configure them
        const keys = Object.keys(this.configuration.elements);
        for (let i = 0; i < keys.length; i++) {
            const key = keys[i];
            const conf = this.configuration.elements[key];
            const el = this._elements[key];

            el.name.textContent = conf.label;
            el.name.style.color = getColor(conf.label_color);
            el.value.textContent = conf.status;
            el.value.style.color = getColor(conf.status_color);

            // 🔧 Update the dot color on every config change:
            el.circle.style.backgroundColor = getColor(conf.color);
        }
    }


    /* -------------------------------------------------------------------------------------------------------------- */
    assignListeners(element) {
        super.assignListeners(element);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    getElement() {
        return this.element;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    update(data) {
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement(this.element);
    }
}

/* === TEXT WIDGET ================================================================================================== */
export class TextWidget extends Widget {
    constructor(id, payload = {}) {
        super(id, payload);

        const defaults = {
            visible: true,
            color: "transparent",
            text_color: "#000",
            title: "",
            title_horizontal_alignment: "center", // 'left' | 'center' | 'right'
            text: "",
            font_size: 12,                        // px
            font_family: "inherit",
            vertical_alignment: "center",         // 'top' | 'center' | 'bottom'
            horizontal_alignment: "left",         // 'left' | 'center' | 'right'
            font_weight: "normal",
            font_style: "normal",
        };

        this.configuration = {...defaults, ...this.configuration}

        this.element = this.initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);

    }

    initializeElement() {
        const element = document.createElement("div");

        element.id = this.id;
        element.classList.add("widget", "highlightable", "textWidget");

        this.titleElement = document.createElement("div");
        this.titleElement.classList.add("textTitle");

        if (this.configuration.title) {
            element.appendChild(this.titleElement);
        } else {
            element.style.gridTemplateRows = "1fr";
            element.style.gridTemplateAreas = "'content'";
        }

        this.contentContainer = document.createElement("div");
        this.contentContainer.classList.add("contentContainer");
        element.appendChild(this.contentContainer);

        this.content = document.createElement("div");
        this.content.classList.add("textContent");
        this.contentContainer.appendChild(this.content);

        return element;
    }

    configureElement(element) {
        super.configureElement(element);

        this.titleElement.style.textAlign = this.configuration.title_horizontal_alignment;
        this.titleElement.textContent = this.configuration.title;


        // Configure the content container
        this.contentContainer.style.justifyContent = {
            top: "flex-start",
            center: "center",
            bottom: "flex-end",
        }[this.configuration.vertical_alignment] || "flex-start";

        // Configure the text content
        Object.assign(this.content.style, {
            color: getColor(this.configuration.text_color),
            fontSize: `${this.configuration.font_size}px`,       // use px
            fontFamily: this.configuration.font_family,
            fontWeight: this.configuration.font_weight,
            fontStyle: this.configuration.font_style,
            width: "100%",
            textAlign: this.configuration.horizontal_alignment,
            whiteSpace: "pre-line",
            wordBreak: "break-word",
        });

        this.content.innerHTML = this.configuration.text;
    }

    resize() {
    }

    update(data) {
        return undefined;
    }

    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement(this.element);
    }
}

export class InputWidget extends Widget {
    constructor(id, config = {}) {
        super(id, config);

        const defaults = {
            visible: true,
            color: 'transparent',
            text_color: '#000',
            inputFieldColor: '#fff',
            inputFieldtext_color: '#000',
            inputFieldFontSize: 11,
            inputFieldAlign: 'center',
            title: '',
            titlePosition: 'top',
            value: '',
            tooltip: null,
            inputFieldWidth: '100%',
            inputFieldPosition: 'center',
        };

        this.configuration = {...defaults, ...this.configuration};
        this._prevValue = this.configuration.value;
        this._tooltipEl = null;
        this._tooltipTimeout = null; // ⬅️ For auto-hiding temporary tooltip

        this.element = this._initializeElement();
        this.configureElement(this.element);
    }

    _initializeElement() {
        const el = document.createElement('div');
        el.id = this.id;
        el.classList.add('widget', 'highlightable', 'textInputWidget');
        return el;
    }

    configureElement(element) {
        super.configureElement(element);
        const c = this.configuration;


        element.dataset.titlePosition = c.title_position;
        element.style.display = c.visible ? '' : 'none';

        element.style.backgroundColor = getColor(c.color);
        element.style.color = getColor(c.text_color);

        element.style.setProperty('--ti-field-bg', getColor(c.inputFieldColor));
        element.style.setProperty('--ti-field-color', getColor(c.inputFieldtext_color));
        const fontSizeVal = typeof c.inputFieldFontSize === 'number'
            ? `${c.inputFieldFontSize}pt`
            : c.inputFieldFontSize;
        element.style.setProperty('--ti-input-font-size', fontSizeVal);
        element.style.setProperty('--ti-input-text-align', c.inputFieldAlign);

        const displayValue = (c.value === null || c.value === 'null') ? '' : c.value;

        let html = '';
        if (c.title) {
            html += `<span class="tiTitle">${c.title}</span>`;
        }
        html += `
            <div class="tiInputContainer">
                <input
                    class="tiInput"
                    type="text"
                    value="${displayValue}"
                    autocomplete="off"
                    autocapitalize="none"
                    spellcheck="false"
                />
            </div>
        `;
        element.innerHTML = html;

        const input = element.querySelector('.tiInput');
        const container = element.querySelector('.tiInputContainer');

        if (c.inputFieldWidth !== null) {
            input.style.width = c.inputFieldWidth;
        } else {
            input.style.width = '';
        }

        if (c.inputFieldPosition === 'center') {
            input.style.display = 'block';
            input.style.marginLeft = 'auto';
            input.style.marginRight = 'auto';
        } else if (c.inputFieldPosition === 'right') {
            input.style.display = 'block';
            input.style.marginLeft = 'auto';
            input.style.marginRight = '4px';
        } else {
            input.style.marginLeft = '';
            input.style.marginRight = '';
        }

        this.assignListeners(this.element);
    }

    update(data) {

    }

    assignListeners(el) {
        super.assignListeners(el);
        const input = el.querySelector('.tiInput');
        const container = el.querySelector('.tiInputContainer');

        const commit = () => {
            const v = input.value.trim();
            this.callbacks.get('event').call({
                event: 'text_input_commit',
                id: this.id,
                data: {value: v}
            });
        };

        input.addEventListener('keydown', e => {
            if (e.key === 'Enter') {
                e.preventDefault();
                commit();
                input.blur();
            }
        });
        input.addEventListener('blur', () => {
            if (this.configuration.commit_on_blur && input.value.trim() !== '') {
                commit();
            } else {
                const prev = this._prevValue;
                input.value = (prev === null || prev === 'null') ? '' : prev;
            }
            this._hideTooltip();
        });

        container.addEventListener('mouseenter', () => this._showTooltip());
        container.addEventListener('mouseleave', () => this._hideTooltip());
        window.addEventListener('scroll', () => this._hideTooltip(), true);
        window.addEventListener('resize', () => this._hideTooltip());
    }

    // _showTooltip(text = null, autoHide = false) { // ⬅️ added args
    _showTooltip(text = null, autoHide = false, isError = false) { // ⬅️ new param
        const content = text || this.configuration.tooltip;
        if (!content) return;

        if (!this._tooltipEl) {
            this._tooltipEl = document.createElement('div');
            this._tooltipEl.classList.add('tiTooltipFloating');
            document.body.appendChild(this._tooltipEl);
        }

        // Adjust class for error
        this._tooltipEl.classList.toggle('tiTooltipFloatingError', isError); // ⬅️

        this._tooltipEl.textContent = content;
        const container = this.element.querySelector('.tiInputContainer');
        const rect = container.getBoundingClientRect();
        const tip = this._tooltipEl;

        tip.style.visibility = 'hidden';
        tip.style.opacity = '0';
        tip.style.position = 'absolute';
        tip.style.left = '0';
        tip.style.top = '0';

        document.body.appendChild(tip);
        const tipRect = tip.getBoundingClientRect();

        const top = Math.max(8, rect.top - tipRect.height - 6) + window.scrollY;
        const left = rect.left + (rect.width - tipRect.width) / 2 + window.scrollX;

        Object.assign(tip.style, {
            top: `${top}px`,
            left: `${left}px`,
            visibility: 'visible',
            opacity: '1',
            transition: 'opacity 0.15s ease-in-out'
        });

        if (autoHide) {
            clearTimeout(this._tooltipTimeout);
            this._tooltipTimeout = setTimeout(() => this._hideTooltip(), 3000);
        }
    }


    _hideTooltip() {
        if (this._tooltipEl) {
            this._tooltipEl.style.visibility = 'hidden';
            this._tooltipEl.style.opacity = '0';
        }
    }

    _animateAccepted() {
        const el = this.element;
        el.classList.add('accepted');
        el.addEventListener('animationend', () => el.classList.remove('accepted'), {once: true});
    }

    _animateError() {
        const el = this.element;
        el.classList.add('error');
        el.addEventListener('animationend', () => el.classList.remove('error'), {once: true});
    }

    validateInput({valid, value, message}) {
        const input = this.element.querySelector('.tiInput');

        if (valid) {
            input.value = (value === null || value === 'null') ? '' : value;
            this._prevValue = value;
            this._animateAccepted();
        } else {
            input.value = (value === null || value === 'null') ? '' : value;
            this._prevValue = value;
            this._animateError();

            if (message) {
                this._showTooltip(message, true, true); // ⬅️ show temporary tooltip
            }
        }
    }

    getElement() {
        return this.element;
    }

    updateConfig(data) {
        Object.assign(this.configuration, data);
        const el = this.element;
        const input = el.querySelector('.tiInput');

        if (data.event === 'revert') {
            input.value = this._prevValue;
            return this._animateError();
        }

        if (data.inputFieldColor !== undefined) {
            el.style.setProperty('--ti-field-bg', getColor(data.inputFieldColor));
        }
        if (data.inputFieldtext_color !== undefined) {
            el.style.setProperty('--ti-field-color', getColor(data.inputFieldtext_color));
        }
        if (data.text_color !== undefined) {
            el.style.color = getColor(data.text_color);
        }

        if (data.inputFieldFontSize !== undefined) {
            const fontSizeVal = typeof this.configuration.inputFieldFontSize === 'number'
                ? `${this.configuration.inputFieldFontSize}px`
                : this.configuration.inputFieldFontSize;
            el.style.setProperty('--ti-input-font-size', fontSizeVal);
        }
        if (data.inputFieldAlign !== undefined) {
            el.style.setProperty('--ti-input-text-align', this.configuration.inputFieldAlign);
        }

        if (data.title_position !== undefined) {
            el.dataset.titlePosition = this.configuration.title_position;
        }

        if (data.value !== undefined) {
            input.value = (data.value === null || data.value === 'null') ? '' : data.value;
            this._prevValue = data.value;
            // this._animateAccepted();
        }

        if (
            data.inputFieldWidth !== undefined ||
            data.inputFieldPosition !== undefined ||
            data.title_position !== undefined
        ) {
            this.configureElement(this.configuration);
        }

        if (data.tooltip !== undefined) {
            this.configuration.tooltip = data.tooltip;
        }
    }

    initializeElement() {
    }

    // InputWidget manages its own tooltip — disable the parent Widget hover tooltip
    // to prevent duplicate tooltips on hover.
    setupHoverTooltip() {}

    resize() {
    }
}

/**
 * DigitalNumberWidget with serializable color_ranges.
 *
 * color_ranges: Array of rules (first match wins). All fields are serializable.
 * Each rule:
 *  - min?: number   (lower bound; default -Infinity if omitted)
 *  - max?: number   (upper bound; default  Infinity if omitted)
 *  - min_inclusive?: boolean (default true)
 *  - max_inclusive?: boolean (default true)
 *  - color: string | [r,g,b,a] (anything accepted by getColor)
 *
 * Examples:
 *  [
 *    { min: -Infinity, max: -90, color: "#e53935" },     // < = -90 -> red
 *    { min: -0.1, max: 0.1, color: "#43a047" },          // -0.1..0.1 -> green
 *    { min: 90, max: Infinity, color: "#e53935" }        // >= 90 -> red
 *  ]
 */
export class DigitalNumberWidget extends Widget {
    constructor(id, config = {}) {
        super(id, config);

        const defaults = {
            title: '',
            visible: true,
            color: [0, 0, 0, 0],
            text_color: '#fff',
            color_ranges: [],           // <— NEW: default empty (no dynamic coloring)
            min_value: 0,
            max_value: 100,
            value: 0,
            increment: 1,
            title_position: 'top', // 'top' or 'left'
            value_color: null,     // static override for text_color if no range matches
            show_unused_digits: true,
            title_is_latex: false,
        };

        this.configuration = {...defaults, ...this.configuration, ...config};

        this.element = this.initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);
        this.setValue(this.configuration.value);
        setTimeout(() => this.resize(), 250);
        // this.resize();
    }

    // ---------- Helpers for color range logic ----------

    static normalizeRule(rule) {
        return {
            min: (rule.min ?? -Infinity),
            max: (rule.max ?? Infinity),
            min_inclusive: rule.min_inclusive !== false, // default true
            max_inclusive: rule.max_inclusive !== false, // default true
            color: rule.color
        };
    }

    static valueInRule(v, r) {
        const lowerOk = r.min_inclusive ? v >= r.min : v > r.min;
        const upperOk = r.max_inclusive ? v <= r.max : v < r.max;
        return lowerOk && upperOk;
    }

    static pickColorForValue(value, ranges, fallback) {
        if (!Array.isArray(ranges) || ranges.length === 0) return fallback;
        for (const raw of ranges) {
            const r = DigitalNumberWidget.normalizeRule(raw);
            if (DigitalNumberWidget.valueInRule(value, r)) return getColor(r.color) || fallback;
        }
        return fallback;
    }

    // ---------------------------------------------------

    initializeElement() {
        const el = document.createElement('div');
        el.id = this.id;
        el.classList.add('widget', 'digitalNumber');

        el.dataset.titlePosition = this.configuration.title_position;

        el.style.backgroundColor = getColor(this.configuration.color);
        el.style.color = getColor(this.configuration.text_color);

        this.title = document.createElement('div');
        this.title.classList.add('title');
        el.appendChild(this.title);
        this.title.textContent = this.configuration.title;

        this.value_container = document.createElement('div');
        this.value_container.classList.add('valueContainer');
        el.appendChild(this.value_container);

        this.value = document.createElement('div');
        this.value.classList.add('value');
        this.value_container.appendChild(this.value);

        return el;
    }

    configureElement(element) {
        super.configureElement(element);

        // Apply static configs that don’t depend on value
        const c = this.configuration;
        element.style.backgroundColor = getColor(c.color);
        element.dataset.titlePosition = c.title_position;
        if (this.title) this.title.textContent = c.title;
    }

    getElement() {
        return this.element;
    }

    updateConfig(data) {
        // Merge and reconfigure element
        this.configuration = {...this.configuration, ...data};
        this.configureElement(this.element);

        // Always reapply current value to refresh formatting & dynamic color
        this.setValue(this.configuration.value);
    }

    update(data) {
        this.setValue(data);
    }

    /**
     * Discrete setter for direct backend calls
     */
    setValue(rawValue) {
        const c = this.configuration;

        // derive formatting info from config
        const inc = +c.increment || 1;
        const decimals = Math.max(0, (inc.toString().split('.')[1] || '').length);

        const minStr = Number(c.min_value).toFixed(decimals);
        const maxStr = Number(c.max_value).toFixed(decimals);
        const maxLen = Math.max(minStr.length, maxStr.length);
        const numericMaxLen = c.min_value < 0 ? maxLen - 1 : maxLen;

        let raw = Math.round((+rawValue) / inc) * inc;

        // fixed-decimal string
        const s = decimals === 0
            ? parseInt(raw, 10).toString()
            : Number(raw).toFixed(decimals);

        // build HTML (with optional leading zeros)
        let html;
        if (!c.show_unused_digits) {
            html = s;
        } else {
            const sign = s[0] === '-' ? '-' : '';
            const digits = sign ? s.slice(1) : s;
            const pad = numericMaxLen - digits.length;
            const zeros = pad > 0 ? '0'.repeat(pad) : '';
            html = sign + `<span class="leadingZero">${zeros}</span>${digits}`;
        }

        // apply to DOM
        this.configuration.value = raw;

        if (this.value) {
            this.value.style.width = `${maxLen}ch`;

            // Dynamic color selection: range color → value_color → text_color
            const fallback = c.value_color || c.text_color;
            const dynamic = DigitalNumberWidget.pickColorForValue(raw, c.color_ranges, fallback);
            this.value.style.color = getColor(dynamic);

            this.value.innerHTML = html;
        }
    }

    assignListeners(el) {
        super.assignListeners(el);
    }

    resize() {
        getFittingFontSizeSingleContainer(this.value_container, 0, 0, 100, 0);
    }
}


export class DigitalClockWidget extends Widget {
    constructor(id, config = {}) {
        super(id, config);

        const defaults = {
            visible: true,
            color: [0, 0, 0, 0],
            text_color: '#fff',

            // Relative timer formatting (fixed width)
            // Supported tokens: HH, mm, ss, S, SS, SSS (subset)
            display_format: 'HH:mm:ss.SS',

            // persisted state
            running: false,

            // value in seconds, OR null => placeholder
            value: null,

            // increment = discrete step size in seconds (important!)
            increment: 0.1,

            allow_negative: false,
        };

        this.configuration = {...defaults, ...this.configuration, ...config};

        this._timer = null;
        this._lastRendered = null;

        // Monotonic/perf-based timing:
        // baseSeconds = accumulated seconds at last start (or stopped value)
        // t0 = performance.now() when started; elapsed is quantized by increment
        this._t0 = null;
        this._baseSeconds = this._coerceSeconds(this.configuration.value);

        this.element = this.initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);

        if (this.configuration.running && this._baseSeconds !== null) this._startInternal();
        else this._renderFromState();

        setTimeout(() => this.resize(), 250);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    initializeElement() {
        const el = document.createElement('div');
        el.id = this.id;
        el.classList.add('widget', 'highlightable', 'digitalClockWidget');

        el.style.backgroundColor = getColor(this.configuration.color);
        el.style.color = getColor(this.configuration.text_color);

        this.value_container = document.createElement('div');
        this.value_container.classList.add('dcValueContainer');
        el.appendChild(this.value_container);

        this.value = document.createElement('div');
        this.value.classList.add('dcValue');
        this.value_container.appendChild(this.value);

        return el;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    configureElement(element = this.element) {
        super.configureElement(element);

        const c = this.configuration;
        element.style.display = c.visible ? '' : 'none';
        element.style.backgroundColor = getColor(c.color);
        element.style.color = getColor(c.text_color);

        // Sync internal base from config.value (null allowed)
        const cfgValue = this._coerceSeconds(c.value);
        this._baseSeconds = cfgValue;

        // Normalize invalid running state: cannot run with null value
        if (c.running && cfgValue === null) {
            this.configuration.running = false;
        }

        // Apply running state
        if (this.configuration.running) this._startInternal();
        else this._stopInternal(false);

        this._renderFromState();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    assignListeners(el) {
        super.assignListeners(el);
        window.addEventListener('resize', () => this.resize());
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    resize() {
        if (this.value_container) {
            getFittingFontSizeSingleContainer(this.value_container, 0, 0, 100, 0);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    update(data) {
        // Supports:
        // - number => seconds
        // - null => placeholder
        // - { value } / { running } / { value, running }
        if (typeof data === 'number' || data === null) {
            this.set(data);
            return;
        }
        if (!data || typeof data !== 'object') return;

        if (Object.prototype.hasOwnProperty.call(data, 'value')) this.set(data.value);
        if (Object.prototype.hasOwnProperty.call(data, 'running')) (data.running ? this.start() : this.stop());
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement(this.element);
    }

    // ===== Public API (callable from python via self.function) =====

    start() {
        // If placeholder -> starting begins at 0.0 (or keep if already numeric)
        if (this._baseSeconds === null) {
            this._baseSeconds = 0.0;
            this.configuration.value = 0.0;
        }

        this.configuration.running = true;
        this._startInternal();
    }

    stop() {
        // Freeze BEFORE flipping running-dependent logic
        this._stopInternal(true);
        this.configuration.running = false;
    }

    reset() {
        this.stop();
        this.set(0);
    }

    /**
     * @param {number|null} seconds number => set base seconds, null => placeholder
     */
    set(seconds) {
        const v = this._coerceSeconds(seconds);

        // Setting null => placeholder, always stopped
        if (v === null) {
            this._stopInternal(false);
            this._baseSeconds = null;
            this.configuration.value = null;
            this.configuration.running = false;
            this._t0 = null;
            this._renderFromState();
            return;
        }

        const q = this._quantize(v);

        // If currently running, keep running but rebase from now
        const wasRunning = !!this.configuration.running;

        this._baseSeconds = q;
        this.configuration.value = q;

        if (wasRunning) {
            this._t0 = performance.now();
            this._startInternal(); // ensures interval matches increment
        }

        this._renderFromState();
    }

    /**
     * Set to local wall clock time-of-day (seconds since midnight).
     */
    setToWallClockNow() {
        const now = new Date();
        const seconds =
            now.getHours() * 3600 +
            now.getMinutes() * 60 +
            now.getSeconds() +
            now.getMilliseconds() / 1000;

        this.set(seconds);
    }

    // ===== Internal timing =====

    _startInternal() {
        // cannot run in placeholder mode
        if (this._baseSeconds === null) {
            this.configuration.running = false;
            return this._renderFromState();
        }

        // Restart timer if increment changed
        const desiredMs = this._tickMs();
        const haveTimer = !!this._timer;

        if (haveTimer && this._timerMs === desiredMs) return;

        if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
        }

        // Start from now
        this._t0 = performance.now();
        this._timerMs = desiredMs;

        this._timer = setInterval(() => {
            const s = this._computeSeconds(true);
            this.configuration.value = s; // keep config hot for reloads
            this._renderFromState();
        }, desiredMs);

        const s0 = this._computeSeconds(true);
        this.configuration.value = s0;
        this._renderFromState();
    }

    _stopInternal(writeBackValue = true) {
        // Freeze using internal state regardless of configuration.running
        const frozen = this._computeSeconds(true); // may be null

        if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
        }

        this._t0 = null;

        if (frozen === null) {
            this._baseSeconds = null;
            if (writeBackValue) this.configuration.value = null;
        } else {
            this._baseSeconds = frozen;
            if (writeBackValue) this.configuration.value = frozen;
        }

        this._renderFromState();
    }

    _tickMs() {
        const inc = Number(this.configuration.increment);
        const ms = isFinite(inc) && inc > 0 ? Math.round(inc * 1000) : 100;
        return Math.max(10, ms);
    }

    /**
     * Compute current seconds.
     * If forceCompute=true, uses internal base+t0 even if config.running is false
     * (this fixes stop() freeze bugs).
     */
    _computeSeconds(forceCompute = false) {
        if (this._baseSeconds === null) return null;

        // If not running and not forced, return base
        if (!forceCompute && (!this.configuration.running || this._t0 == null)) {
            return this._baseSeconds;
        }

        // If we don't have a start time, just return base
        if (this._t0 == null) return this._baseSeconds;

        const base = this._baseSeconds || 0;
        const inc = this._incSafe();
        const elapsed = (performance.now() - this._t0) / 1000;

        // Discrete stepping: base + floor(elapsed/inc)*inc
        const steps = Math.floor(elapsed / inc) * inc;
        const s = base + steps;

        return this.configuration.allow_negative ? s : Math.max(0, s);
    }

    _incSafe() {
        const inc = Number(this.configuration.increment);
        return (isFinite(inc) && inc > 0) ? inc : 0.1;
    }

    _quantize(v) {
        const inc = this._incSafe();
        // quantize to nearest increment step
        const q = Math.round(v / inc) * inc;
        // avoid tiny float tails
        return Number(q.toFixed(9));
    }

    // ===== Rendering =====

    _renderFromState() {
        const v = this._computeSeconds(false);

        if (v === null) {
            const placeholder = this._placeholderForFormat(this.configuration.display_format);
            this._renderText(placeholder);
            return;
        }

        const formatted = this._formatSeconds(v, this.configuration.display_format);
        this._renderText(formatted);
    }

    _renderText(text) {
        if (text === this._lastRendered) return;
        this._lastRendered = text;

        if (this.value) {
            this.value.style.width = `${text.length}ch`;
            this.value.textContent = text;
        }
    }

    _placeholderForFormat(fmt) {
        // Replace token runs with same-length dashes; keep separators as-is.
        // Example: "HH:mm:ss.SS" -> "--:--:--.--"
        //          "hh:mm:ss.SS" -> "--:--:--.--"
        //          "HH:mm:ss.SSS" -> "--:--:--.---"
        const s = String(fmt);
        let out = "";
        for (let i = 0; i < s.length; ) {
            const ch = s[i];
            if ("HhmsS".includes(ch)) {
                let j = i + 1;
                while (j < s.length && s[j] === ch) j++;
                out += "-".repeat(j - i);
                i = j;
            } else {
                out += ch;
                i++;
            }
        }
        return out;
    }

    _coerceSeconds(v) {
        if (v === null || v === undefined) return null;
        const n = Number(v);
        if (!isFinite(n)) return null;
        return n;
    }

    _formatSeconds(totalSeconds, fmt) {
        let s = Number(totalSeconds) || 0;
        if (!this.configuration.allow_negative) s = Math.max(0, s);

        const inc = this._incSafe();

        // Since we step by inc, compute frac from quantized time
        const q = this._quantize(s);
        const whole = Math.floor(q);
        const frac = q - whole;

        const HH = String(Math.floor(whole / 3600)).padStart(2, '0');
        const mm = String(Math.floor((whole % 3600) / 60)).padStart(2, '0');
        const ss = String(whole % 60).padStart(2, '0');

        // convert fractional seconds to ms
        const ms = Math.round(frac * 1000);
        const S1 = String(Math.floor(ms / 100));
        const S2 = String(Math.floor(ms / 10)).padStart(2, '0');
        const S3 = String(ms).padStart(3, '0');

        return String(fmt)
            .replace(/SSS/g, S3)
            .replace(/SS/g, S2)
            .replace(/HH/g, HH)
            .replace(/hh/g, HH) // treat hh same for relative timer
            .replace(/mm/g, mm)
            .replace(/ss/g, ss)
            .replace(/S/g, S1);
    }
}


export class TimecodeWidget extends Widget {
    constructor(id, config = {}) {
        super(id, config);

        const defaults = {
            color: [0, 0, 0, 0],
            text_color: '#fff',
            automatic: false,
            fps: 25
        }
    }

    initializeElement() {
    }

    resize() {
    }

    update(data) {
        return undefined;
    }

    updateConfig(data) {
        return undefined;
    }

    set(timecode) {

    }
}


export class LineScrollTextWidget extends Widget {
    constructor(id, payload = {}) {
        super(id, payload);

        const defaults = {
            background_color: [0, 0, 0, 0],
            font_size: 7,               // pt
            text_color: [1, 1, 1, 0.8], // rgba
            include_time_stamp: true,
            auto_scroll_threshold: 100   // px from bottom
        };

        this.configuration = {...defaults, ...this.configuration};
        this.element = this.initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);


        const clear_terminal_context_menu_item = new ContextMenuItem('clear', {
            name: 'Clear',
            front_icon: '🗑️',
        })
        this.addItemToContextMenu(clear_terminal_context_menu_item);
        clear_terminal_context_menu_item.callbacks.get('click').register(this.clear.bind(this));

        // Loop through this.data.lines and add them to the widget
        if (this.data.lines) {
            for (const line of this.data.lines) {
                this.addLine(line.text, line.color);
            }
        }
        this.scrollDown();

    }


    initializeElement() {
        const el = document.createElement("div");
        el.id = this.id;
        el.classList.add("widget", 'highlightable', "lineScrollTextWidget");
        return el;
    }

    configureElement(el) {
        super.configureElement(el);
        const c = this.configuration;

        // Base styling
        el.style.backgroundColor = getColor(c.background_color);
        el.style.fontSize = `${c.font_size}pt`;
        el.style.color = getColor(c.text_color);

        // Layout
        el.style.overflowY = "auto";
        el.style.display = "flex";
        el.style.flexDirection = "column";
        el.style.padding = "4px";
    }

    /**
     * Add a line of text. If scroll is within `auto_scroll_threshold`
     * of the bottom, it jumps to the bottom.
     * @param {string} text
     * @param {string|array|null} color
     */
    addLine(text, color = null) {
        const c = this.configuration;
        const lineEl = document.createElement("div");
        lineEl.classList.add("lineScrollLine");

        // timestamp
        let content = text;
        if (c.include_time_stamp) {
            const now = new Date();
            const hh = String(now.getHours()).padStart(2, "0");
            const mm = String(now.getMinutes()).padStart(2, "0");
            const ss = String(now.getSeconds()).padStart(2, "0");
            content = `[${hh}:${mm}:${ss}] ${content}`;
        }
        lineEl.textContent = content;

        // color override?
        lineEl.style.color = color ? getColor(color) : getColor(c.text_color);

        // append
        this.element.appendChild(lineEl);

        // auto-scroll
        const {scrollTop, clientHeight, scrollHeight} = this.element;
        if (scrollTop + clientHeight >= scrollHeight - c.auto_scroll_threshold) {
            this.element.scrollTop = scrollHeight;
        }
    }

    /**
     * Clear all lines
     */
    clear() {
        this.element.innerHTML = "";
    }

    /**
     * Optional update API: if data.text exists, append it,
     * if data.clear===true, clear instead.
     */
    update(data) {
        if (data.clear) {
            this.clear();
        } else if (data.text != null) {
            this.addLine(data.text, data.color);
        }
    }

    updateConfig(data) {
        this.configuration = {...this.configuration, ...data};
        this.configureElement(this.element);
    }

    getElement() {
        return this.element;
    }

    assignListeners(element) {
        super.assignListeners(element);
    }

    scrollDown() {
        this.element.scrollTop = this.element.scrollHeight;
    }

    resize() {
    }
}
