import {Widget} from "../objects/objects.js";
import "./map.css"
import {
    Point,
    Line,
    Circle,
    Agent,
    VisionAgent,
    CoordinateSystem,
    MapObjectGroup,
    MAP_OBJECT_MAPPING
} from "./map_objects.js";
import {splitPath} from "../helpers.js";
import {Websocket} from "../websocket.js";


const MAP_DEFAULTS_WS_PORT = 8700

/* === MAP ========================================================================================================== */
export class Map {
    /** @type {HTMLCanvasElement} */ canvas;
    /** @type {CanvasRenderingContext2D} */ context;
    /** @type {object} */ config;
    /** @type {HTMLElement} */ container;
    /** @type {object} */ groups = {};
    /** @type {object} */ objects = {};

    // === view state ===
    /** @type {number} */ cw = 0;          // canvas px width
    /** @type {number} */ ch = 0;          // canvas px height
    /** @type {number} */ baseScale = 1;   // px per world-unit at zoom=1
    /** @type {number} */ zoom = 1;        // user zoom factor
    /** @type {[number, number]} */ viewCenter = [0, 0];   // initial_display_center
    /** @type {[number, number]} */ offset = [0, 0];       // pan offset in world units
    /** @type {boolean} */ dragging = false;
    /** @type {[number, number]} */ dragStartScreen = [0, 0];
    /** @type {[number, number]} */ dragStartOffset = [0, 0];

    _rafId = null;
    _lastTs = 0;
    _frameInterval = 0; // ms per frame

    websocket_connected = false;

    // === cursor state ===
    /** @type {string} */ _cursorType = 'default';  // 'default', 'circle', 'crosshair', 'none'
    /** @type {object} */ _cursorOptions = {};
    /** @type {[number, number] | null} */ _mouseWorldPos = null;  // current mouse position in world coords
    /** @type {[number, number] | null} */ _mouseScreenPos = null; // current mouse position in screen coords

    /* == CONSTRUCTOR ============================================================================================== */
    constructor(id, container, payload = {}) {

        const defaults = {

            /* Geometry */
            limits: {x: [0, 3], y: [0, 3]},
            origin: [0, 0],
            rotation: 0,  // in degrees

            /* Coordinate System */
            coordinate_system_size: 0.5,  // in m
            coordinate_system_alpha: 0.9,
            coordinate_system_width: 3, // px

            /* General Styling */
            map_border_width: 1,                  // px
            map_border_color: [1, 1, 1, 1],
            map_border_radius: 0.1,               // in world units
            map_color: [1, 1, 1, 0],

            background_color: [0, 0, 0, 0],

            /* Grid */
            show_grid: false,
            show_grid_coordinates: true,
            adaptive_grid: false,
            major_grid_size: 1,
            minor_grid_size: 0.5,

            major_grid_width: 2,                  // px
            major_grid_style: 'solid',
            major_grid_color: [0.5, 0.5, 0.5, 1],

            minor_grid_width: 1,                  // px
            minor_grid_style: 'dotted',
            minor_grid_color: [0.5, 0.5, 0.5, 1],

            /* Tiling */
            tiles: true,
            tile_size: 0.5,
            tile_colors: [[0.3, 0.3, 0.3, 1], [28 / 255, 27 / 255, 43 / 255, 0.6]],
            tile_border_width: 1,                 // px
            tile_border_color: [0, 0, 0, 1],
            show_tile_coordinates: true,

            /* Ticks / labels */
            ticks_color: [1, 1, 1, 1],            // label color (RGBA 0..1)
            ticks_bar_color: [0, 0, 0, 0.4],      // bar bg under ticks (RGBA 0..1)
            ticks_bar_size_px: 22,                // thickness of left/bottom bars
            ticks_padding_px: 4,                  // inner padding for text
            min_label_px: 20,                     // minimal spacing between labels (px)

            /* Behaviour */
            allow_zoom: true,
            allow_drag: true,
            allow_rotate: false,                  // user-rotate not implemented

            /* Display */
            initial_display_center: [1.5, 1.5],
            initial_display_zoom: 0.75,

            zoom_limits: [0.75, 3],
            /* Overlay */
            enable_overlay: true,
            overlay_type: 'side',  // Can be 'side' or 'full' or 'external'

            /* Rendering */
            fps: 30,
        };

        this.id = id;
        this.config = {...defaults, ...(payload.config || {})};
        this.initializeContainer(container);

        this.canvas = this.initializeCanvas();
        this.context = this.canvas.getContext('2d');

        // initialize view
        this.viewCenter = [...this.config.initial_display_center];
        this.setZoom(this.config.initial_display_zoom ?? 1);

        // sizing + listeners
        this.updateCanvasSizeAndScale();
        this.attachInteractions();

        // Overlays
        this.prepareOverlays();

        // Objects and Groups from Config
        this.buildObjectsFromPayload(payload.objects);
        this.buildGroupsFromPayload(payload.groups);

        // Websocket connection
        this._wsHost = payload.websocket.host;
        this._wsPort = payload.websocket.port;
        this.websocket = new Websocket({host: this._wsHost, port: this._wsPort});
        this.websocket.on('message', this._onWebsocketMessage.bind(this));
        this.websocket.on('connected', this._onWebsocketConnected.bind(this));
        this.websocket.on('close', this._onWebsocketDisconnected.bind(this))

        this.websocket.connect()


        // first draw
        this.drawMap();

        this.startRenderLoop();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    initializeContainer(widget_container) {
        this.container = document.createElement('div');
        this.container.classList.add('map-overall-container');
        widget_container.appendChild(this.container);

        this.map_container = document.createElement('div');
        this.map_container.classList.add('map-container');
        this.container.appendChild(this.map_container);
    }

    /* == CANVAS METHODS ============================================================================================ */
    initializeCanvas() {
        const canvas = document.createElement('canvas');
        canvas.id = 'map_canvas';
        canvas.classList.add('map-new-canvas');
        this.map_container.appendChild(canvas);
        return canvas;
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    // Convert [r,g,b,a] in 0..1 to CSS rgba()
    arrayToColor(arr) {
        const [r, g, b, a] = arr ?? [0, 0, 0, 1];
        const R = Math.round(r * 255);
        const G = Math.round(g * 255);
        const B = Math.round(b * 255);
        const A = Math.max(0, Math.min(1, a));
        return `rgba(${R},${G},${B},${A})`;
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    // World size & helpers
    get worldWidth() {
        return (this.config.limits.x[1] - this.config.limits.x[0]);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    get worldHeight() {
        return (this.config.limits.y[1] - this.config.limits.y[0]);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    get origin() {
        return this.config.origin || [0, 0];
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    // compute baseScale (px per world unit) so that at zoom=1 the entire map fits within the container
    computeBaseScale() {
        if (this.worldWidth <= 0 || this.worldHeight <= 0 || this.cw === 0 || this.ch === 0) return 1;
        // Use Math.min to ensure the constraining dimension fits (entire map visible)
        return Math.min(this.cw / this.worldWidth, this.ch / this.worldHeight);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    updateCanvasSizeAndScale() {
        // set canvas pixel size to CSS box size
        this.cw = this.map_container.clientWidth || 0;
        this.ch = this.map_container.clientHeight || 0;
        this.canvas.width = this.cw;
        this.canvas.height = this.ch;
        // background (outside the map rectangle)
        this.canvas.style.backgroundColor = this.arrayToColor(this.config.background_color);
        this.baseScale = this.computeBaseScale();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    get scale() {
        return this.baseScale * (this.zoom || 1);
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    // Zoom limits helpers
    getZoomLimits() {
        // Accepts [min, max] where either may be null or undefined
        const zl = this.config.zoom_limits ?? [null, null];
        let [min, max] = Array.isArray(zl) ? zl : [null, null];

        // normalize to numbers or null
        min = (min === null || min === undefined || Number.isNaN(+min)) ? null : +min;
        max = (max === null || max === undefined || Number.isNaN(+max)) ? null : +max;

        // if both present but swapped, fix the order
        if (min !== null && max !== null && min > max) [min, max] = [max, min];

        return [min, max];
    }

    clampZoom(z) {
        let [min, max] = this.getZoomLimits();
        if (min !== null) z = Math.max(min, z);
        if (max !== null) z = Math.min(max, z);
        return z;
    }

    setZoom(z) {
        this.zoom = this.clampZoom(z);
    }


    /* -------------------------------------------------------------------------------------------------------------- */
    attachInteractions() {
        // Resize observer
        new ResizeObserver(() => {
            this.updateCanvasSizeAndScale();
            this.drawMap();
        }).observe(this.map_container);

        // Dragging
        if (this.config.allow_drag) {
            this.container.classList.remove('grabbing'); // ensure clean state
            this.container.style.cursor = 'grab';
            this.canvas.addEventListener('mousedown', (e) => {
                this.dragging = true;
                this.dragStartScreen = [e.clientX, e.clientY];
                this.dragStartOffset = [...this.offset];
                this.container.classList.add('grabbing');
            });
            window.addEventListener('mousemove', (e) => {
                if (!this.dragging) return;
                const dx = e.clientX - this.dragStartScreen[0];
                const dy = e.clientY - this.dragStartScreen[1];
                const [dox, doy] = this.screenDeltaToWorldDelta(dx, dy);

                // natural panning (drag right -> map right, drag up -> map up)
                this.offset = [
                    this.dragStartOffset[0] - dox,
                    this.dragStartOffset[1] - doy
                ];
                this.drawMap();
            });
            window.addEventListener('mouseup', () => {
                if (!this.dragging) return;
                this.dragging = false;
                this.container.classList.remove('grabbing');
            });
        }

        // Zooming (wheel)
        if (this.config.allow_zoom) {
            this.canvas.addEventListener('wheel', (e) => {
                e.preventDefault();
                const factor = 1 - e.deltaY * 0.001;
                const next = (this.zoom || 1) * factor;
                this.setZoom(next);           // <-- clamp to zoom_limits
                this.drawMap();
            }, {passive: false});
        }

        // Click listener (left click)
        this.canvas.addEventListener('click', (e) => {
            // Don't trigger click if we were dragging
            if (this._wasDragging) {
                this._wasDragging = false;
                return;
            }
            const rect = this.canvas.getBoundingClientRect();
            const sx = e.clientX - rect.left;
            const sy = e.clientY - rect.top;
            const worldPos = this.canvasPointToWorld(sx, sy);
            this.on_click(worldPos.x, worldPos.y);
        });

        // Double click listener
        this.canvas.addEventListener('dblclick', (e) => {
            const rect = this.canvas.getBoundingClientRect();
            const sx = e.clientX - rect.left;
            const sy = e.clientY - rect.top;
            const worldPos = this.canvasPointToWorld(sx, sy);
            this.on_double_click(worldPos.x, worldPos.y);
        });

        // Right click listener (context menu)
        this.canvas.addEventListener('contextmenu', (e) => {
            e.preventDefault(); // Prevent default context menu
            const rect = this.canvas.getBoundingClientRect();
            const sx = e.clientX - rect.left;
            const sy = e.clientY - rect.top;
            const worldPos = this.canvasPointToWorld(sx, sy);
            this.on_right_click(worldPos.x, worldPos.y);
        });

        // Middle click listener
        this.canvas.addEventListener('mousedown', (e) => {
            if (e.button === 1) { // Middle mouse button
                e.preventDefault();
                const rect = this.canvas.getBoundingClientRect();
                const sx = e.clientX - rect.left;
                const sy = e.clientY - rect.top;
                const worldPos = this.canvasPointToWorld(sx, sy);
                this.on_middle_click(worldPos.x, worldPos.y);
            }
        });

        // Prevent middle click default behavior (auto-scroll)
        this.canvas.addEventListener('auxclick', (e) => {
            if (e.button === 1) {
                e.preventDefault();
            }
        });

        // Track if we dragged (to prevent click after drag)
        this.canvas.addEventListener('mousedown', () => {
            this._wasDragging = false;
        });
        window.addEventListener('mousemove', (e) => {
            if (this.dragging) {
                this._wasDragging = true;
            }
        });

        // Double-tap (touch) detection — fires on_double_click for two quick taps
        this._lastTapTime = 0;
        this._lastTapX = 0;
        this._lastTapY = 0;
        const DOUBLE_TAP_MS = 300;
        const DOUBLE_TAP_DISTANCE = 30; // px

        // Long-press (touch) listener — fires after 500 ms hold without moving
        this._longPressTimer = null;
        this._longPressFired = false;
        const LONG_PRESS_MS = 500;
        const LONG_PRESS_MOVE_THRESHOLD = 10; // px

        this.canvas.addEventListener('touchstart', (e) => {
            if (e.touches.length !== 1) return;
            const touch = e.touches[0];
            this._longPressStartX = touch.clientX;
            this._longPressStartY = touch.clientY;
            this._longPressFired = false;

            this._longPressTimer = setTimeout(() => {
                const rect = this.canvas.getBoundingClientRect();
                const sx = this._longPressStartX - rect.left;
                const sy = this._longPressStartY - rect.top;
                const worldPos = this.canvasPointToWorld(sx, sy);
                this._longPressFired = true;
                this.on_long_press(worldPos.x, worldPos.y);
            }, LONG_PRESS_MS);
        }, {passive: true});

        this.canvas.addEventListener('touchmove', (e) => {
            if (this._longPressTimer && e.touches.length === 1) {
                const touch = e.touches[0];
                const dx = touch.clientX - this._longPressStartX;
                const dy = touch.clientY - this._longPressStartY;
                if (Math.sqrt(dx * dx + dy * dy) > LONG_PRESS_MOVE_THRESHOLD) {
                    clearTimeout(this._longPressTimer);
                    this._longPressTimer = null;
                }
            }
        }, {passive: true});

        this.canvas.addEventListener('touchend', (e) => {
            if (this._longPressTimer) {
                clearTimeout(this._longPressTimer);
                this._longPressTimer = null;
            }

            // Double-tap detection (skip if long-press already fired)
            if (!this._longPressFired && e.changedTouches.length === 1) {
                const touch = e.changedTouches[0];
                const now = Date.now();
                const dx = touch.clientX - this._lastTapX;
                const dy = touch.clientY - this._lastTapY;
                const dist = Math.sqrt(dx * dx + dy * dy);

                if (now - this._lastTapTime < DOUBLE_TAP_MS && dist < DOUBLE_TAP_DISTANCE) {
                    // Double tap detected
                    e.preventDefault();
                    const rect = this.canvas.getBoundingClientRect();
                    const sx = touch.clientX - rect.left;
                    const sy = touch.clientY - rect.top;
                    const worldPos = this.canvasPointToWorld(sx, sy);
                    this.on_double_click(worldPos.x, worldPos.y);
                    this._lastTapTime = 0; // reset to avoid triple-tap
                } else {
                    this._lastTapTime = now;
                    this._lastTapX = touch.clientX;
                    this._lastTapY = touch.clientY;
                }
            }
        });

        this.canvas.addEventListener('touchcancel', () => {
            if (this._longPressTimer) {
                clearTimeout(this._longPressTimer);
                this._longPressTimer = null;
            }
        });

        // Mouse move listener for cursor position tracking
        this.canvas.addEventListener('mousemove', (e) => {
            const rect = this.canvas.getBoundingClientRect();
            const sx = e.clientX - rect.left;
            const sy = e.clientY - rect.top;
            this._mouseScreenPos = [sx, sy];
            const worldPos = this.canvasPointToWorld(sx, sy);
            this._mouseWorldPos = [worldPos.x, worldPos.y];
        });

        // Clear mouse position when leaving canvas
        this.canvas.addEventListener('mouseleave', () => {
            this._mouseScreenPos = null;
            this._mouseWorldPos = null;
        });
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Called when the map is left-clicked. Override this method or use it as a callback.
     * @param {number} x - World x coordinate of the click
     * @param {number} y - World y coordinate of the click
     */
    on_click(x, y) {
        console.log(`Map left-clicked at world coordinates: x=${x.toFixed(3)}, y=${y.toFixed(3)}`);
        const message = {
            type: 'event',
            data: {
                type: 'click',
                x: x,
                y: y,
            },
        }

        this.websocket.send(message);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Called when the map is double-clicked. Override this method or use it as a callback.
     * @param {number} x - World x coordinate of the double-click
     * @param {number} y - World y coordinate of the double-click
     */
    on_double_click(x, y) {

        const message = {
            type: 'event',
            data: {
                type: 'double_click',
                x: x,
                y: y,
            },
        }
        this.websocket.send(message);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Called on a long-press (touch hold). Override this method or use it as a callback.
     * @param {number} x - World x coordinate of the long-press
     * @param {number} y - World y coordinate of the long-press
     */
    on_long_press(x, y) {
        const message = {
            type: 'event',
            data: {
                type: 'long_press',
                x: x,
                y: y,
            },
        }
        this.websocket.send(message);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Called when the map is right-clicked. Override this method or use it as a callback.
     * @param {number} x - World x coordinate of the right-click
     * @param {number} y - World y coordinate of the right-click
     */
    on_right_click(x, y) {
        const message = {
            type: 'event',
            data: {
                type: 'right_click',
                x: x,
                y: y,
            },
        }
        this.websocket.send(message);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Called when the map is middle-clicked. Override this method or use it as a callback.
     * @param {number} x - World x coordinate of the middle-click
     * @param {number} y - World y coordinate of the middle-click
     */
    on_middle_click(x, y) {
        const message = {
            type: 'event',
            data: {
                type: 'middle_click',
                x: x,
                y: y,
            },
        }
        this.websocket.send(message);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Change the cursor displayed on the map.
     * @param {string} type - Cursor type: 'default', 'circle', 'crosshair', 'none'
     * @param {object} options - Options for the cursor (depends on type)
     *   For 'circle': { color: [r,g,b,a], size: radiusInWorldUnits, fillColor: [r,g,b,a] (optional), lineWidth: px }
     *   For 'crosshair': { color: [r,g,b,a], size: sizeInWorldUnits, lineWidth: px }
     *   Common options:
     *     - showCoordinates: boolean - Show x,y coordinates next to cursor (lower right, .1f format)
     *     - coordinatesColor: [r,g,b,a] - Color for coordinates text (defaults to cursor color)
     */
    change_cursor(type, options = {}) {
        this._cursorType = type;
        this._cursorOptions = options;

        // Update the actual CSS cursor based on type
        // Apply to both container and canvas to ensure cursor is hidden
        if (type === 'default') {
            const defaultCursor = this.config.allow_drag ? 'grab' : 'default';
            this.container.style.cursor = defaultCursor;
            this.canvas.style.cursor = defaultCursor;
            this.map_container.style.cursor = defaultCursor;
        } else if (type === 'none') {
            this.container.style.cursor = 'none';
            this.canvas.style.cursor = 'none';
            this.map_container.style.cursor = 'none';
        } else {
            // For custom cursors (circle, crosshair), hide the system cursor
            this.container.style.cursor = 'none';
            this.canvas.style.cursor = 'none';
            this.map_container.style.cursor = 'none';
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    /**
     * Draw the custom cursor at the current mouse position.
     * Called during the render loop after all other elements are drawn.
     */
    drawCursor() {
        if (this._cursorType === 'default' || this._cursorType === 'none') return;
        if (!this._mouseWorldPos) return;

        const ctx = this.context;
        const [wx, wy] = this._mouseWorldPos;

        ctx.save();
        this.applyWorldTransform(ctx);

        if (this._cursorType === 'circle') {
            const color = this._cursorOptions.color || [1, 0, 0, 1];
            const fillColor = this._cursorOptions.fillColor || null;
            const size = this._cursorOptions.size || 0.1;  // radius in world units
            const lineWidth = (this._cursorOptions.lineWidth || 2) / this.scale;

            // Draw fill if specified
            if (fillColor) {
                ctx.beginPath();
                ctx.arc(wx, wy, size, 0, 2 * Math.PI);
                ctx.fillStyle = this.arrayToColor(fillColor);
                ctx.fill();
            }

            // Draw outline
            ctx.beginPath();
            ctx.arc(wx, wy, size, 0, 2 * Math.PI);
            ctx.strokeStyle = this.arrayToColor(color);
            ctx.lineWidth = lineWidth;
            ctx.stroke();

        } else if (this._cursorType === 'crosshair') {
            const color = this._cursorOptions.color || [1, 1, 1, 1];
            const size = this._cursorOptions.size || 0.1;  // half-length in world units
            const lineWidth = (this._cursorOptions.lineWidth || 2) / this.scale;

            ctx.strokeStyle = this.arrayToColor(color);
            ctx.lineWidth = lineWidth;

            // Horizontal line
            ctx.beginPath();
            ctx.moveTo(wx - size, wy);
            ctx.lineTo(wx + size, wy);
            ctx.stroke();

            // Vertical line
            ctx.beginPath();
            ctx.moveTo(wx, wy - size);
            ctx.lineTo(wx, wy + size);
            ctx.stroke();
        }

        ctx.restore();

        // Draw coordinates if enabled (in screen space for consistent size)
        if (this._cursorOptions.showCoordinates && this._mouseScreenPos) {
            const [sx, sy] = this._mouseScreenPos;
            const coordColor = this._cursorOptions.coordinatesColor || this._cursorOptions.color || [1, 1, 1, 1];
            const coordText = `${wx.toFixed(this._cursorOptions.coordinatesPrecision || 2)}, ${wy.toFixed(this._cursorOptions.coordinatesPrecision || 2)}`;

            ctx.save();
            ctx.setTransform(1, 0, 0, 1, 0, 0); // Reset to screen space

            ctx.font = '10px monospace';
            ctx.fillStyle = this.arrayToColor(coordColor);
            ctx.textAlign = 'left';
            ctx.textBaseline = 'top';

            // Position at lower right of cursor (offset by 8px)
            const offsetX = 8;
            const offsetY = 8;
            ctx.fillText(coordText, sx + offsetX, sy + offsetY);

            ctx.restore();
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    // Convert a screen delta (px, px) to world delta (units, units) respecting rotation and y-flip
    screenDeltaToWorldDelta(dx, dy) {
        const k = this.scale;            // px per world unit
        if (k === 0) return [0, 0];
        // base mapping used in old map (no rotation): [dx/k, -dy/k]
        const vx = dx / k;
        const vy = -dy / k;

        const theta = (this.config.rotation || 0) * Math.PI / 180;
        if (theta === 0) return [vx, vy];

        // Apply inverse rotation to convert screen-based delta into world axes
        const c = Math.cos(-theta);
        const s = Math.sin(-theta);
        const wx = c * vx - s * vy;
        const wy = s * vx + c * vy;
        return [wx, wy];
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    // Push a world→canvas transform onto the context:
    //  1) translate to canvas center,
    //  2) scale (y-up),
    //  3) rotate by config.rotation,
    //  4) translate by negative center & pan offset
    applyWorldTransform(ctx) {
        const theta = (this.config.rotation || 0) * Math.PI / 180;
        const [cx, cy] = this.viewCenter;
        const [ox, oy] = this.offset;

        ctx.translate(this.cw / 2, this.ch / 2);
        ctx.scale(this.scale, -this.scale);   // y-up
        ctx.rotate(theta);
        ctx.translate(-(cx + ox), -(cy + oy));
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    // Rounded-rect path in world units
    buildRoundedRectPath(x, y, w, h, r) {
        const radius = Math.max(0, Math.min(r, Math.min(w, h) / 2));
        const x2 = x + w, y2 = y + h;
        const p = new Path2D();
        p.moveTo(x + radius, y);
        p.lineTo(x2 - radius, y);
        p.arc(x2 - radius, y + radius, radius, -Math.PI / 2, 0);
        p.lineTo(x2, y2 - radius);
        p.arc(x2 - radius, y2 - radius, radius, 0, Math.PI / 2);
        p.lineTo(x + radius, y2);
        p.arc(x + radius, y2 - radius, radius, Math.PI / 2, Math.PI);
        p.lineTo(x, y + radius);
        p.arc(x + radius, y + radius, radius, Math.PI, 1.5 * Math.PI);
        p.closePath();
        return p;
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    // Draw the outside-only border: stroke a slightly bigger rect so inner edge aligns with map edge
    strokeOutsideBorder(ctx, x, y, w, h, r, strokePx, strokeStyle) {
        if (!strokePx || strokePx <= 0) return;
        const grow = (strokePx / this.scale) / 2; // grow by half stroke in world units
        const path = this.buildRoundedRectPath(x - grow, y - grow, w + 2 * grow, h + 2 * grow, Math.max(0, r + grow));
        const worldLine = strokePx / this.scale;
        ctx.save();
        ctx.lineWidth = worldLine;
        ctx.strokeStyle = strokeStyle;
        ctx.stroke(path);
        ctx.restore();
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    // Draw grid (major & minor) in world coords within limits, clipped to map
    drawGrid(ctx) {
        if (!this.config.show_grid) return;

        const {x: [xmin, xmax], y: [ymin, ymax]} = this.config.limits;
        const major = this.config.major_grid_size || 1;
        const minor = this.config.minor_grid_size || 0.5;

        const majorColor = this.arrayToColor(this.config.major_grid_color);
        const minorColor = this.arrayToColor(this.config.minor_grid_color);

        const drawLines = (step, widthPx, style, color) => {
            if (!step || step <= 0) return;

            const worldLineWidth = widthPx / this.scale;
            const dash = (style === 'dotted') ? [2 / this.scale, 2 / this.scale] : [];

            // Vertical lines
            const startX = Math.ceil((xmin - this.origin[0]) / step) * step + this.origin[0];
            const endX = Math.floor((xmax - this.origin[0]) / step) * step + this.origin[0];

            ctx.save();
            ctx.setLineDash(dash);
            ctx.lineWidth = worldLineWidth;
            ctx.strokeStyle = color;
            for (let x = startX; x <= endX + 1e-9; x += step) {
                ctx.beginPath();
                ctx.moveTo(x, ymin);
                ctx.lineTo(x, ymax);
                ctx.stroke();
            }

            // Horizontal lines
            const startY = Math.ceil((ymin - this.origin[1]) / step) * step + this.origin[1];
            const endY = Math.floor((ymax - this.origin[1]) / step) * step + this.origin[1];
            for (let y = startY; y <= endY + 1e-9; y += step) {
                ctx.beginPath();
                ctx.moveTo(xmin, y);
                ctx.lineTo(xmax, y);
                ctx.stroke();
            }
            ctx.restore();
        };

        // minor first, then major on top
        drawLines(minor, this.config.minor_grid_width || 1, this.config.minor_grid_style, minorColor);
        drawLines(major, this.config.major_grid_width || 2, this.config.major_grid_style, majorColor);
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    // Draw checkerboard tiles, starting from origin, clipped to map rounded rectangle
    drawTiles(ctx) {
        if (!this.config.tiles) return;

        const size = this.config.tile_size || 1;
        const {x: [xmin, xmax], y: [ymin, ymax]} = this.config.limits;

        const c0 = this.arrayToColor(this.config.tile_colors?.[0] || [0.3, 0.3, 0.3, 1]);
        const c1 = this.arrayToColor(this.config.tile_colors?.[1] || [0.5, 0.5, 0.5, 1]);
        const borderColor = this.arrayToColor(this.config.tile_border_color || [0, 0, 0, 1]);
        const borderPx = this.config.tile_border_width ?? 0;
        const worldBorder = borderPx / this.scale;

        const x0 = this.origin[0], y0 = this.origin[1];

        const iMin = Math.floor((xmin - x0) / size);
        const iMax = Math.floor((xmax - x0) / size);
        const jMin = Math.floor((ymin - y0) / size);
        const jMax = Math.floor((ymax - y0) / size);

        for (let i = iMin; i <= iMax; i++) {
            for (let j = jMin; j <= jMax; j++) {
                const x = x0 + i * size;
                const y = y0 + j * size;
                const isAlt = ((i + j) & 1) === 1;
                ctx.fillStyle = isAlt ? c1 : c0;
                ctx.fillRect(x, y, size, size);

                if (borderPx > 0) {
                    ctx.save();
                    ctx.lineWidth = worldBorder;
                    ctx.strokeStyle = borderColor;
                    ctx.strokeRect(x, y, size, size);
                    ctx.restore();
                }
            }
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    // Utility: convert a world point to canvas px
    worldPointToCanvas(wx, wy) {
        const theta = (this.config.rotation || 0) * Math.PI / 180;
        const [cx, cy] = this.viewCenter;
        const [ox, oy] = this.offset;

        let x = wx - (cx + ox);
        let y = wy - (cy + oy);

        const ct = Math.cos(theta), st = Math.sin(theta);
        const xr = ct * x - st * y;
        const yr = st * x + ct * y;

        const sx = xr * this.scale + this.cw / 2;
        const sy = -yr * this.scale + this.ch / 2;

        return {x: sx, y: sy};
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    // Utility: convert canvas px to world coordinates (inverse of worldPointToCanvas)
    canvasPointToWorld(sx, sy) {
        const theta = (this.config.rotation || 0) * Math.PI / 180;
        const [cx, cy] = this.viewCenter;
        const [ox, oy] = this.offset;

        // Reverse the screen transform
        const xr = (sx - this.cw / 2) / this.scale;
        const yr = -(sy - this.ch / 2) / this.scale;

        // Reverse the rotation
        const ct = Math.cos(-theta), st = Math.sin(-theta);
        const x = ct * xr - st * yr;
        const y = st * xr + ct * yr;

        // Add back the center and offset
        const wx = x + (cx + ox);
        const wy = y + (cy + oy);

        return {x: wx, y: wy};
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    // Draw coordinate axes at origin (red x, green y)
    drawCoordinateSystem(ctx) {
        const L = this.config.coordinate_system_size || 1;
        const alpha = (this.config.coordinate_system_alpha ?? 0.5);
        const widthPx = (this.config.coordinate_system_width ?? 2);
        const [ox, oy] = this.origin;

        const worldLine = widthPx / this.scale;
        const head = 8 / this.scale; // arrowhead size in world units

        // X axis (red)
        ctx.save();
        ctx.lineWidth = worldLine;
        ctx.strokeStyle = `rgba(255,0,0,${alpha})`;
        ctx.fillStyle = `rgba(255,0,0,${alpha})`;
        ctx.beginPath();
        ctx.moveTo(ox, oy);
        ctx.lineTo(ox + L, oy);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(ox + L, oy);
        ctx.lineTo(ox + L - head, oy + head / 2);
        ctx.lineTo(ox + L - head, oy - head / 2);
        ctx.closePath();
        ctx.fill();
        ctx.restore();

        // Y axis (green)
        ctx.save();
        ctx.lineWidth = worldLine;
        ctx.strokeStyle = `rgba(0,180,0,${alpha})`;
        ctx.fillStyle = `rgba(0,180,0,${alpha})`;
        ctx.beginPath();
        ctx.moveTo(ox, oy);
        ctx.lineTo(ox, oy + L);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(ox, oy + L);
        ctx.lineTo(ox - head / 2, oy + L - head);
        ctx.lineTo(ox + head / 2, oy + L - head);
        ctx.closePath();
        ctx.fill();
        ctx.restore();

        // origin dot
        ctx.save();
        const r = 3 / this.scale;
        ctx.beginPath();
        ctx.arc(ox, oy, r, 0, 2 * Math.PI);
        ctx.fillStyle = 'rgba(0,0,0,0.9)';
        ctx.fill();
        ctx.restore();
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    // Draw the semi-transparent bars and labels along the inner bottom & left canvas edges.
    drawEdgeLabels({useTiles}) {
        const ctx = this.context;
        if (!ctx) return;

        // === config / helpers ===
        const ticksColor = this.arrayToColor(this.config.ticks_color || [1, 1, 1, 1]);
        const barSize = this.config.ticks_bar_size_px ?? 22;
        const pad = this.config.ticks_padding_px ?? 4;
        const minLabelPx = this.config.min_label_px ?? 50;

        const stepBase = useTiles ? (this.config.tile_size || 1)
            : (this.config.major_grid_size || 1);
        if (!stepBase || stepBase <= 0) return;

        const {x: [xmin, xmax], y: [ymin, ymax]} = this.config.limits;
        const [ox, oy] = this.origin;

        // Axis -> color
        const BAR_COLORS = {
            x: "rgba(139,0,0,0.3)",     // darkred-ish
            y: "rgba(0,100,0,0.3)",     // darkgreen-ish
        };

        // Which world axis is more horizontal on screen at current rotation?
        const theta = (this.config.rotation || 0) * Math.PI / 180;
        const c = Math.cos(theta);
        const s = Math.sin(theta);

        // Screen delta per +1 world on each axis (from worldPointToCanvas math):
        // ex: Δsx = +c, Δsy = -s ; ey: Δsx = -s, Δsy = -c   (ignoring scale)
        const horizMagnitudeX = Math.abs(c);
        const horizMagnitudeY = Math.abs(s);

        const bottomAxis = (horizMagnitudeX >= horizMagnitudeY) ? "x" : "y";
        const leftAxis = (bottomAxis === "x") ? "y" : "x";

        // Helpers to compute aligned ranges/ticks
        const computeRangeAligned = (min, max, originAxis, step) => {
            if (useTiles) {
                const start = Math.ceil((min - originAxis) / step) * step + originAxis;
                const end = Math.floor((max - originAxis) / step) * step + originAxis;
                return [start, end];
            } else {
                const start = Math.ceil(min / step) * step;
                const end = Math.floor(max / step) * step;
                return [start, end];
            }
        };
        const snapToGrid = (val, originAxis, step) => {
            if (useTiles) {
                const k = Math.round((val - originAxis) / step);
                return originAxis + k * step;
            } else {
                const k = Math.round(val / step);
                return k * step;
            }
        };
        const buildOutwardValues = (start, end, anchor, step, originAxisForTiles) => {
            const vals = [];
            let anchorVal = anchor;
            if (anchorVal < start - 1e-9 || anchorVal > end + 1e-9) {
                const base = useTiles ? originAxisForTiles : 0;
                const left = Math.floor((anchor - base) / step) * step + base;
                const right = left + step;
                const cand = [];
                if (left >= start - 1e-9 && left <= end + 1e-9) cand.push(left);
                if (right >= start - 1e-9 && right <= end + 1e-9) cand.push(right);
                if (cand.length === 0) return [];
                anchorVal = cand.reduce((best, v) =>
                    (Math.abs(v - anchor) < Math.abs(best - anchor) ? v : best), cand[0]);
            }
            vals.push(+anchorVal.toFixed(12));

            let i = 1;
            while (true) {
                const L = anchorVal - i * step;
                const R = anchorVal + i * step;
                let any = false;
                if (L >= start - 1e-9) {
                    vals.push(+L.toFixed(12));
                    any = true;
                }
                if (R <= end + 1e-9) {
                    vals.push(+R.toFixed(12));
                    any = true;
                }
                if (!any) break;
                i++;
            }
            return vals;
        };

        const decimalsFromStep = (step) => {
            const s = Math.abs(step);
            if (!isFinite(s) || s <= 0) return 0;
            const str = s.toString();
            if (str.indexOf('e-') !== -1) return Math.min(6, parseInt(str.split('e-')[1], 10));
            const parts = str.split('.');
            return parts[1] ? Math.min(6, parts[1].length) : 0;
        };

        const formatWorld = (val, step) => val.toFixed(decimalsFromStep(step));

        // Current world center (to stabilize projections)
        const cxWorld = this.viewCenter[0] + this.offset[0];
        const cyWorld = this.viewCenter[1] + this.offset[1];

        // Compute stride (# of base steps to skip) using proper screen-axis projection
        const computeStride = (axis, screenAxis /* "x" for bottom, "y" for left */) => {
            // Two world points one base-step apart along the chosen world axis
            const a = axis === "x"
                ? this.worldPointToCanvas(cxWorld, cyWorld)
                : this.worldPointToCanvas(cxWorld, cyWorld);
            const b = axis === "x"
                ? this.worldPointToCanvas(cxWorld + stepBase, cyWorld)
                : this.worldPointToCanvas(cxWorld, cyWorld + stepBase);

            const spacingPx = Math.max(1, Math.abs(
                screenAxis === "x" ? (b.x - a.x) : (b.y - a.y)
            ));
            return Math.max(1, Math.ceil(minLabelPx / spacingPx));
        };

        // === Start drawing in screen space ===
        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);

        // Bars with axis-based colors
        ctx.fillStyle = BAR_COLORS[bottomAxis];
        ctx.fillRect(0, this.ch - barSize, this.cw, barSize);  // bottom
        ctx.fillStyle = BAR_COLORS[leftAxis];
        ctx.fillRect(0, 0, barSize, this.ch);                   // left

        // Clip to the bars so labels stay inside
        const clip = new Path2D();
        clip.rect(0, this.ch - barSize, this.cw, barSize);
        clip.rect(0, 0, barSize, this.ch);
        ctx.clip(clip);

        // Common text styling
        ctx.fillStyle = ticksColor;
        ctx.font = "12px Roboto, Arial, sans-serif";

        // ========== Bottom bar (shows bottomAxis) ==========
        (axis => {
            const stride = computeStride(axis, "x");
            const [start, end] = (axis === "x")
                ? computeRangeAligned(xmin, xmax, ox, stepBase)
                : computeRangeAligned(ymin, ymax, oy, stepBase);
            if (end < start) return;

            const anchorWorld = useTiles
                ? (axis === "x" ? ox : oy)
                : 0;

            const snappedAnchor = snapToGrid(anchorWorld, axis === "x" ? ox : oy, stepBase);
            const baseVals = buildOutwardValues(
                start, end, snappedAnchor, stepBase, axis === "x" ? ox : oy
            );
            if (baseVals.length === 0) return;

            // Keep each stride-th tick (relative to snapped anchor)
            const idxOf = v => {
                const base = useTiles ? (axis === "x" ? ox : oy) : 0;
                const anchorBase = Math.round((snappedAnchor - base) / stepBase) * stepBase;
                return Math.round((v - base - anchorBase) / stepBase);
            };
            const filtered = baseVals.filter(v => Math.abs(idxOf(v)) % stride === 0);

            // Project to screen X
            const candidates = filtered.map(val => {
                const p = (axis === "x")
                    ? this.worldPointToCanvas(val, cyWorld)
                    : this.worldPointToCanvas(cxWorld, val);
                return {val, px: p.x, isAnchor: Math.abs(val - snappedAnchor) <= 1e-9};
            }).filter(c => c.px >= -80 && c.px <= this.cw + 80);

            if (!candidates.length) return;

            // Greedy placement, anchor-aware if visible
            candidates.sort((a, b) => a.px - b.px);
            const anchorIdx = candidates.findIndex(c => c.isAnchor);
            let kept = [];
            if (anchorIdx === -1) {
                let last = -Infinity;
                for (const c of candidates) {
                    if (c.px - last >= minLabelPx - 0.5) {
                        kept.push(c);
                        last = c.px;
                    }
                }
            } else {
                kept.push(candidates[anchorIdx]);
                // right
                let lastR = candidates[anchorIdx].px;
                for (let i = anchorIdx + 1; i < candidates.length; i++) {
                    const c = candidates[i];
                    if (c.px - lastR >= minLabelPx - 0.5) {
                        kept.push(c);
                        lastR = c.px;
                    }
                }
                // left
                let lastL = candidates[anchorIdx].px;
                for (let i = anchorIdx - 1; i >= 0; i--) {
                    const c = candidates[i];
                    if (lastL - c.px >= minLabelPx - 0.5) {
                        kept.push(c);
                        lastL = c.px;
                    }
                }
                kept.sort((a, b) => a.px - b.px);
            }

            // Render labels
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            const yPx = this.ch - barSize / 2;
            for (const {val, px} of kept) {
                const label = useTiles
                    ? formatWorld(val, stepBase)   // show world values even for tiles
                    : formatWorld(val, stepBase);
                ctx.fillText(String(label), px, yPx);
            }
        })(bottomAxis);

        // ========== Left bar (shows leftAxis) ==========
        (axis => {
            const stride = computeStride(axis, "y");
            const [start, end] = (axis === "y")
                ? computeRangeAligned(ymin, ymax, oy, stepBase)
                : computeRangeAligned(xmin, xmax, ox, stepBase);
            if (end < start) return;

            const anchorWorld = useTiles
                ? (axis === "y" ? oy : ox)
                : 0;

            const snappedAnchor = snapToGrid(anchorWorld, axis === "y" ? oy : ox, stepBase);
            const baseVals = buildOutwardValues(
                start, end, snappedAnchor, stepBase, axis === "y" ? oy : ox
            );
            if (baseVals.length === 0) return;

            const idxOf = v => {
                const base = useTiles ? (axis === "y" ? oy : ox) : 0;
                const anchorBase = Math.round((snappedAnchor - base) / stepBase) * stepBase;
                return Math.round((v - base - anchorBase) / stepBase);
            };
            const filtered = baseVals.filter(v => Math.abs(idxOf(v)) % stride === 0);

            // Project to screen Y
            const candidates = filtered.map(val => {
                const p = (axis === "y")
                    ? this.worldPointToCanvas(cxWorld, val)
                    : this.worldPointToCanvas(val, cyWorld);
                return {val, py: p.y, isAnchor: Math.abs(val - snappedAnchor) <= 1e-9};
            }).filter(c => c.py >= -80 && c.py <= this.ch + 80);

            if (!candidates.length) return;

            candidates.sort((a, b) => a.py - b.py);
            const anchorIdx = candidates.findIndex(c => c.isAnchor);
            let kept = [];
            if (anchorIdx === -1) {
                let last = -Infinity;
                for (const c of candidates) {
                    if (c.py - last >= minLabelPx - 0.5) {
                        kept.push(c);
                        last = c.py;
                    }
                }
            } else {
                kept.push(candidates[anchorIdx]);
                // downward
                let lastD = candidates[anchorIdx].py;
                for (let i = anchorIdx + 1; i < candidates.length; i++) {
                    const c = candidates[i];
                    if (c.py - lastD >= minLabelPx - 0.5) {
                        kept.push(c);
                        lastD = c.py;
                    }
                }
                // upward
                let lastU = candidates[anchorIdx].py;
                for (let i = anchorIdx - 1; i >= 0; i--) {
                    const c = candidates[i];
                    if (lastU - c.py >= minLabelPx - 0.5) {
                        kept.push(c);
                        lastU = c.py;
                    }
                }
                kept.sort((a, b) => a.py - b.py);
            }

            // Render labels
            ctx.textAlign = "right";
            ctx.textBaseline = "middle";
            const xPx = barSize - pad;
            for (const {val, py} of kept) {
                const label = useTiles
                    ? formatWorld(val, stepBase)   // show world values even for tiles
                    : formatWorld(val, stepBase);
                ctx.fillText(String(label), xPx, py);
            }
        })(leftAxis);

        ctx.restore();
    }

    /* -------------------------------------------------------------------------------------------------------------- */

    // Handy: screen-space extents of the rotated map
    getMapScreenExtents(xmin, ymin, xmax, ymax) {
        const pts = [
            this.worldPointToCanvas(xmin, ymin),
            this.worldPointToCanvas(xmax, ymin),
            this.worldPointToCanvas(xmax, ymax),
            this.worldPointToCanvas(xmin, ymax),
        ];
        const left = Math.min(...pts.map(p => p.x));
        const right = Math.max(...pts.map(p => p.x));
        const top = Math.min(...pts.map(p => p.y));
        const bottom = Math.max(...pts.map(p => p.y));
        return {left, right, top, bottom};
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    drawMap() {
        const ctx = this.context;
        if (!ctx) return;


        // Check if the rotation is 0, 90, 180, 270, otherwise throw an error
        if (this.config.rotation !== 0 && this.config.rotation !== 90 && this.config.rotation !== 180 && this.config.rotation !== 270) {
            throw new Error("Rotation must be 0, 90, 180, or 270 degrees.");
        }

        // keep scale up to date if container changed
        this.updateCanvasSizeAndScale();

        // clear canvas
        ctx.save();
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.clearRect(0, 0, this.cw, this.ch);
        ctx.restore();

        const {x: [xmin, xmax], y: [ymin, ymax]} = this.config.limits;
        const W = xmax - xmin;
        const H = ymax - ymin;

        // --- World layer (everything is drawn in world units with a single transform) ---
        ctx.save();
        this.applyWorldTransform(ctx);

        // 1) Map background fill (rounded) — this is the map face area
        const mapFill = this.arrayToColor(this.config.map_color);
        const mapStroke = this.arrayToColor(this.config.map_border_color);
        const borderPx = this.config.map_border_width ?? 0;
        const radius = Math.max(0, this.config.map_border_radius || 0);

        const facePath = this.buildRoundedRectPath(xmin, ymin, W, H, radius);

        // fill face
        ctx.save();
        ctx.fillStyle = mapFill;
        ctx.fill(facePath);
        ctx.restore();

        // 2) Clip to rounded map face for tiles & grid (so tiles are also clipped by rounded corners)
        ctx.save();
        ctx.clip(facePath);

        // 3) Tiles (checkerboard)
        this.drawTiles(ctx);

        // 4) Grid (minor, major)
        this.drawGrid(ctx);

        // remove clipping for axes & border
        ctx.restore();

        // 6) Outside-only border (so it doesn’t overlap tiles/grid)
        this.strokeOutsideBorder(ctx, xmin, ymin, W, H, radius, borderPx, mapStroke);

        this.drawCoordinateSystem(ctx);

        // Draw all objects
        this.drawObjects();

        // Done with world drawing
        ctx.restore();

        // Draw custom cursor (on top of everything, in its own transform)
        this.drawCursor();

        // 7) Edge labels (tile or grid coordinates) on the canvas edges inside bars
        const showTileCoords = this.config.tiles && this.config.show_tile_coordinates;
        const showGridCoords = this.config.show_grid && this.config.show_grid_coordinates;
        if (showTileCoords || showGridCoords) {
            this.drawEdgeLabels({useTiles: !!showTileCoords});
        }
    }

    /* === OVERLAYS ================================================================================================= */
    prepareOverlays() {
        // 1. Add the Button
        this.overlayButton = document.createElement("button");
        this.overlayButton.id = "overlayButton";
        this.overlayButton.className = "overlayButton";
        this.overlayButton.textContent = 'Objects';
        // this.container.appendChild(this.overlayButton);

        // Add a click callback to the button
        this.overlayButton.addEventListener('click', () => {
            this.showObjectsOverlay();
        });

        // 2. Prepare the objects overlay
        if (this.config.overlay_type === 'side') {
            this.objectsOverlay = document.createElement("div");
            this.objectsOverlay.id = "objectsOverlay";
            this.objectsOverlay.className = "objects-overlay-side";
            this.container.appendChild(this.objectsOverlay);
        } else {
            this.objectsOverlay = document.createElement("div");
            this.objectsOverlay.id = "objectsOverlay";
            this.objectsOverlay.className = "objects-overlay";
            this.container.appendChild(this.objectsOverlay);
        }

        // Add the close button to the objects overlay
        const closeButton = document.createElement("button");
        closeButton.id = "closeButton";
        closeButton.className = "overlay-close-button";
        this.objectsOverlay.appendChild(closeButton);

        closeButton.addEventListener('click', () => {
            this.hideObjectsOverlay();
        })

        this.hideObjectsOverlay();

        // Info Overlay which shows when clicking onto an object
        this.infoOverlay = document.createElement("div");
        this.infoOverlay.id = "infoOverlay";
        this.infoOverlay.className = "info-overlay";
        this.container.appendChild(this.infoOverlay);

        this.hideInfoOverlay();


        // Connection indicator
        this.connectionIndicator = document.createElement("div");
        this.connectionIndicator.id = "connectionIndicator";
        this.connectionIndicator.className = "map-connection-indicator";
        this.container.appendChild(this.connectionIndicator);

        // Pop-out button
        this.popoutButton = document.createElement("button");
        this.popoutButton.className = "map-popout-button";
        this.popoutButton.title = "Pop Out";
        this.popoutButton.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>`;
        this.container.appendChild(this.popoutButton);

        this.popoutButton.addEventListener('click', () => {
            const host = this._wsHost || 'localhost';
            const port = this._wsPort || '8700';
            const url = new URL('/map-popup.html', window.location.origin);
            url.searchParams.set('id', this.id);
            url.searchParams.set('host', host);
            url.searchParams.set('port', port);
            url.searchParams.set('title', `Map: ${this.id}`);
            window.open(url.href, '_blank', 'width=1000,height=800,resizable=yes');
        });
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    showObjectsOverlay() {
        // Show the overlay
        if (this.config.overlay_type === 'side') {
            this.objectsOverlay.style.display = 'block';
        } else {
            this.objectsOverlay.style.display = 'block';
        }

        // Hide the button
        this.overlayButton.style.display = 'none';

    }

    /* -------------------------------------------------------------------------------------------------------------- */
    hideObjectsOverlay() {
        if (this.config.overlay_type === 'side') {
            this.objectsOverlay.style.display = 'none';
        } else {
            this.objectsOverlay.style.display = 'none';
        }

        // Show the button
        this.overlayButton.style.display = 'block';
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    showInfoOverlay(object) {
        // Show the overlay
        this.infoOverlay.style.display = 'block';
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    hideInfoOverlay() {
        this.infoOverlay.style.display = 'none';
    }

    /* === OBJECTS ==================================================================================================== */
    addObject(object) {
        // Check if the object is already in the dict
        if (this.objects[object.id]) {
            console.warn(`Object with id ${object.id} already exists.`)
            return;
        }

        object.parent = this;
        // Add the object to the dict
        this.objects[object.id] = object;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    addObjectFromPayload(payload) {

    }

    /* -------------------------------------------------------------------------------------------------------------- */

    /* -------------------------------------------------------------------------------------------------------------- */
    removeObject(object) {
        if (!object) return;

        // If a group instance was passed, remove it from groups
        if (object instanceof MapObjectGroup) {
            if (!this.groups[object.id]) {
                console.warn(`Group with id ${object.id} not found on map.`);
                return;
            }
            if (typeof object.destroy === 'function') object.destroy();
            delete this.groups[object.id];
            object.parent = null;
            // this.drawMap();
            return;
        }

        // Otherwise treat it as a regular map object
        if (!this.objects[object.id]) {
            console.warn(`Object with id ${object.id} not found on map.`);
            return;
        }

        if (typeof object.destroy === 'function') object.destroy();
        delete this.objects[object.id];
        object.parent = null;

        // this.drawMap();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    addGroup(group) {
        if (this.groups[group.id]) {
            console.warn(`Group with id ${group.id} already exists.`)
            return;
        }
        group.parent = this;
        this.groups[group.id] = group;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    removeGroup(group) {

    }

    /* -------------------------------------------------------------------------------------------------------------- */

    /* -------------------------------------------------------------------------------------------------------------- */
    getObjectByUID(uid) {
        let key, remainder;

        [key, remainder] = splitPath(uid);

        // Check if key is our id:
        if (!(key === this.id)) {
            console.warn(`Invalid first key ${key} in uid ${uid}. Should be ${this.id}.`);
            return
        }

        if (!remainder) {
            return this;
        }

        // Get the remainder of the path
        [key, remainder] = splitPath(remainder);

        // Restore the full key of the object
        const fullKey = `${this.id}/${key}`;

        const object = this.objects[fullKey];
        if (object) {
            return object;
        }

        const group = this.groups[fullKey];
        if (group) {
            if (remainder) {
                return group.getObjectByPath(remainder);
            } else {
                return group;
            }

        }

        console.warn(`Object with uid ${uid} not found.`);
        console.log(this.objects);
        return null;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    getMap() {
        return this;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    getAllObjectsFlat() {
        // Collect all objects from the map and all descendant groups into one array
        const flat = [];

        // 1) top-level objects
        for (const obj of Object.values(this.objects)) {
            flat.push(obj);
        }

        // 2) objects from groups (MapObjectGroup#getObjects returns a flat dictionary)
        for (const group of Object.values(this.groups)) {
            const groupObjects = group.getObjects(); // { fullId: obj, ... }
            for (const obj of Object.values(groupObjects)) {
                flat.push(obj);
            }
        }

        return flat;
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    drawObjects() {
        // Gather everything
        const list = this.getAllObjectsFlat()
            // only draw visible ones
            .filter(o => (o?.config?.visible ?? true));

        // Sort by layer (low first => drawn earlier => underneath).
        // Tie-break by id for stable ordering.
        list.sort((a, b) => {
            const la = +((a.config && a.config.layer) ?? 0);
            const lb = +((b.config && b.config.layer) ?? 0);
            if (la !== lb) return la - lb;
            return String(a.id).localeCompare(String(b.id));
        });

        // Draw in order
        for (const obj of list) {
            obj.draw();
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    buildObjectsFromPayload(objects) {
        for (const [id, payload] of Object.entries(objects)) {
            const type = payload.type;
            const object_type = MAP_OBJECT_MAPPING[type];
            if (!object_type) {
                console.warn(`Unknown object type ${type}.`);
                continue;
            }
            const object = new object_type(payload.id, payload);
            this.addObject(object);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    buildGroupsFromPayload(groups) {
        for (const [id, payload] of Object.entries(groups)) {
            const group = new MapObjectGroup(payload.id, payload);
            this.addGroup(group);
        }
    }

    /* === RENDERING ================================================================================================= */
    startRenderLoop() {
        const fps = Math.max(0, this.config.fps ?? 0);
        if (fps <= 0) return; // disabled
        this._frameInterval = 1000 / fps;

        const tick = (ts) => {
            if (!this._rafId) return; // stopped
            if (!this._lastTs) this._lastTs = ts;

            const elapsed = ts - this._lastTs;
            if (elapsed >= this._frameInterval) {
                // catch up in case of long frames
                this._lastTs = ts - (elapsed % this._frameInterval);
                this.drawMap();
            }
            this._rafId = requestAnimationFrame(tick);
        };

        if (!this._rafId) {
            this._rafId = requestAnimationFrame(tick);
        }
    }

    stopRenderLoop() {
        if (this._rafId) {
            cancelAnimationFrame(this._rafId);
            this._rafId = null;
        }
        this._lastTs = 0;
    }

    setFPS(fps) {
        // update config and restart the loop with the new rate
        this.config.fps = Math.max(0, fps | 0);
        this.stopRenderLoop();
        this.startRenderLoop();
    }


    /* === WEBSOCKET ================================================================================================ */
    _onWebsocketMessage(message) {
        switch (message.type) {
            case 'init':
                this._handleInitMessage(message);
                break;
            case 'update':
                this.handleUpdateMessage(message);
                break;
            case 'update_config':
                this.handleUpdateConfigMessage(message);
                break;
            case 'add':
                this.handleAddMessage(message);
                break;
            case 'remove':
                this.handleRemoveMessage(message);
                break;
            default:
                console.warn(`Unknown message type ${message.type}.`);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _handleInitMessage(message) {
        if (!message.payload) return;
        const payload = message.payload;

        // Apply config from server (merge with defaults)
        if (payload.config) {
            this.config = {...this.config, ...payload.config};
            this.viewCenter = [...(this.config.initial_display_center || this.viewCenter)];
            this.setZoom(this.config.initial_display_zoom ?? this.zoom);
            this.updateCanvasSizeAndScale();
        }

        // Build objects and groups from init payload
        if (payload.objects && Object.keys(payload.objects).length > 0) {
            this.buildObjectsFromPayload(payload.objects);
        }
        if (payload.groups && Object.keys(payload.groups).length > 0) {
            this.buildGroupsFromPayload(payload.groups);
        }

        this.drawMap();
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    handleUpdateMessage(message) {
        for (const [id, payload] of Object.entries(message.data)) {
            const object = this.getObjectByUID(id);
            if (object) {
                object.update(payload);
            }
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    handleUpdateConfigMessage(message) {
        for (const [id, payload] of Object.entries(message.data)) {
            const object = this.getObjectByUID(id);
            if (object) {
                object.updateConfig(payload);
            }
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    handleAddMessage(message) {
        // Get the parent from the message
        const parent = this.getObjectByUID(message.parent);
        if (!parent) {
            console.warn(`Parent object with uid ${message.parent} not found.`);
            return;
        }

        if (parent === this) {
            // Get the object type from the message
            const type = message.payload.type;

            if (type === 'group') {
                const group = new MapObjectGroup(message.payload.id, message.payload);
                this.addGroup(group);
                return;
            }

            const object_type = MAP_OBJECT_MAPPING[type];
            if (!object_type) {
                console.warn(`Unknown object type ${type}.`);
                return
            }
            const object = new object_type(message.payload.id, message.payload);
            this.addObject(object);

        } else {
            parent.handleAddMessage(message);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    handleRemoveMessage(message) {
        // Get the parent from the message
        const parent = this.getObjectByUID(message.parent);
        if (!parent) {
            console.warn(`Parent object with uid ${message.parent} not found.`);
            return;
        }
        if (parent === this) {
            const object = this.getObjectByUID(message.id);
            if (object) {
                this.removeObject(object);
            }
        } else {
            parent.handleRemoveMessage(message);
        }
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _onWebsocketConnected() {
        this.websocket_connected = true;
        this.setConnectionStatus(true);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    _onWebsocketDisconnected() {
        this.websocket_connected = false;
        this.setConnectionStatus(false);
    }

    /* -------------------------------------------------------------------------------------------------------------- */
    setConnectionStatus(status) {
        this.connectionIndicator.style.backgroundColor = status ? 'rgba(0,255,0,0.5)' : 'rgba(255,0,0,0.5)';
    }
}

export class MapWidget extends Widget {
    constructor(id, payload = {}) {
        super(id, payload);

        this.element = this.initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);

        this.map = new Map(payload.map.id, this.element, payload.map || {});


        setTimeout(() => {
            this.map.change_cursor('crosshair', {
                color: [1, 1, 1, 1],
                size: 0.1,                    // Half-length in world units
                showCoordinates: true,
            });
        }, 1000);
    }

    initializeElement() {

        const element = document.createElement("div");
        element.classList.add('gridItem', 'widget', 'map-new-widget');
        return element;
    }

    resize() {
    }

    update(data) {
        return undefined;
    }

    updateConfig(data) {
        return undefined;
    }
}