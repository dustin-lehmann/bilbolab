// import {Widget} from "../objects.js";
// import {formatNumberWithIncrement, getColor} from "../../helpers.js";
//
// /* ================================================================================================================== */
// export class TableCell {
//
//     /** @type {string} */
//     column = undefined;
//     /** @type {string} */
//     row = undefined;
//     /** @type {Table} */
//     table = undefined;
//     /** @type {string} */
//     id = undefined;
//
//     /** @type {object} */
//     overrides = {};
//
//     /** @type {typeof TableColumn} */
//     static column_type;
//
//     constructor(id, row, column, value, config = {}) {
//         this.id = id;
//         this.row = row;
//         this.column = column;
//         this.configuration = config;
//         this.value = value;
//         this.element = null;
//     }
//
//     /** Merge: column defaults/config + parent(TableColumn) config + cell overrides */
//     _getMergedStyleConfig() {
//         const colObj = this.table?.columns?.[this.column];
//         const colCfg = colObj?.configuration ?? {};
//         const overrides = this.configuration ?? {};
//
//         // The column already merged its own defaults into column.configuration.
//         // We just let cell overrides win.
//         return {...colCfg, ...overrides};
//     }
//
//     draw_cell(container) {
//         this.element = document.createElement('td');
//         this.element.textContent = '--';
//         this.element.style.border = '0.5px solid #999999';
//         this.element.style.textAlign = 'center';
//         this.element.style.padding = '1px';
//         container.appendChild(this.element);
//     }
//
//     update(value) {
//         this.value = value;
//         this.element.textContent = value;
//     }
// }
//
//
// export class TableColumn {
//     constructor(id, config = {}) {
//
//         const defaults = {
//             width: "auto", // "auto" | "100px" | 0.3 (30%) | "30%"
//             title: "",
//             title_color: [1, 1, 1, 0.8],
//             title_font_size: 11,
//             title_font_family: "sans-serif",
//             title_font_align: "center",
//             background_color: [0, 0, 0, 0],
//             enabled: true,
//         };
//
//         this.id = id;
//         this.configuration = {...defaults, ...config};
//         this.table = null;
//     }
//
//     /**
//      * Convert width config into a CSS width string usable on <col>/<th>.
//      * Supports:
//      *  - "auto"
//      *  - "100px" (or any CSS length)
//      *  - 0.5 => "50%"
//      *  - "50%"
//      */
//     get_css_width() {
//         const w = this.configuration?.width;
//
//         if (w === undefined || w === null) return "auto";
//
//         // number: treat as percentage ratio if 0..1
//         if (typeof w === "number") {
//             if (!Number.isFinite(w)) return "auto";
//             if (w <= 0) return "0px"; // allow collapsing
//             if (w > 0 && w <= 1) return `${w * 100}%`;
//             // if someone passes 120 -> assume px
//             return `${w}px`;
//         }
//
//         if (typeof w === "string") {
//             const s = w.trim().toLowerCase();
//             if (!s || s === "auto") return "auto";
//             // allow "50%"
//             if (s.endsWith("%")) return s;
//             // allow "100px", "12rem", "10ch", etc.
//             return w.trim();
//         }
//
//         return "auto";
//     }
//
//     draw_header_cell(parent) {
//         const cell = document.createElement("th");
//
//         cell.textContent = this.configuration.title;
//         cell.style.fontSize = `${this.configuration.title_font_size}pt`;
//         cell.style.fontFamily = this.configuration.title_font_family;
//         cell.style.textAlign = this.configuration.title_font_align;
//         cell.style.color = getColor(this.configuration.title_color);
//         cell.style.backgroundColor = getColor(this.configuration.background_color);
//         cell.style.fontWeight = "bold";
//         cell.style.border = "1px solid #aaaaaa";
//
//         const cssW = this.get_css_width();
//         if (cssW !== "auto") cell.style.width = cssW;
//
//         parent.appendChild(cell);
//     }
// }
//
// /* ------------------------------------------------------------------------------------------------------------------ */
// export class TextColumn extends TableColumn {
//     constructor(id, config = {}) {
//         super(id, config);
//
//         this.defaults = {
//             text_color: [1, 1, 1, 0.8],
//             font_size: 10,  // pt
//             font_family: 'sans-serif',
//             font_align: 'left',  // left, center, right
//         }
//
//         this.configuration = {...this.defaults, ...this.configuration};
//     }
// }
//
// export class TextCell extends TableCell {
//     static column_type = TextColumn;
//
//     constructor(id, row, column, value, config = {}) {
//         super(id, row, column, value, config);
//
//     }
//
//     draw_cell(container) {
//         this.element = document.createElement("td");
//
//         const cfg = this._getMergedStyleConfig();
//
//         // content
//         const text = this.value;
//         this.element.textContent = (text !== undefined && text !== null) ? String(text) : "";
//
//         // base cell style
//         this.element.style.border = "0.5px solid #999999";
//         this.element.style.padding = "1px";
//         this.element.style.verticalAlign = "middle";
//
//         // apply column/cell style
//         this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
//         this.element.style.color = getColor(cfg.text_color ?? [1, 1, 1, 0.8]);
//         this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
//         this.element.style.fontFamily = cfg.font_family ?? "sans-serif";
//         this.element.style.textAlign = cfg.font_align ?? "left";
//
//         // Optional extras (supported only if present in overrides/column config)
//         if (cfg.font_weight !== undefined) this.element.style.fontWeight = String(cfg.font_weight);
//         if (cfg.padding !== undefined) this.element.style.padding = String(cfg.padding);
//         if (cfg.border !== undefined) this.element.style.border = String(cfg.border);
//         if (cfg.white_space !== undefined) this.element.style.whiteSpace = String(cfg.white_space);
//         if (cfg.overflow !== undefined) this.element.style.overflow = String(cfg.overflow);
//         if (cfg.text_overflow !== undefined) this.element.style.textOverflow = String(cfg.text_overflow);
//
//         container.appendChild(this.element);
//     }
//
//     update(value) {
//         this.value = value;
//         if (!this.element) return;
//
//         const cfg = this._getMergedStyleConfig();
//
//         // Update text
//         this.element.textContent = (value !== undefined && value !== null) ? String(value) : "";
//
//         // If overrides can change dynamically, re-apply style every update
//         this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
//         this.element.style.color = getColor(cfg.text_color ?? [1, 1, 1, 0.8]);
//         this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
//         this.element.style.fontFamily = cfg.font_family ?? "sans-serif";
//         this.element.style.textAlign = cfg.font_align ?? "left";
//
//         if (cfg.font_weight !== undefined) this.element.style.fontWeight = String(cfg.font_weight);
//         if (cfg.padding !== undefined) this.element.style.padding = String(cfg.padding);
//         if (cfg.border !== undefined) this.element.style.border = String(cfg.border);
//         if (cfg.white_space !== undefined) this.element.style.whiteSpace = String(cfg.white_space);
//         if (cfg.overflow !== undefined) this.element.style.overflow = String(cfg.overflow);
//         if (cfg.text_overflow !== undefined) this.element.style.textOverflow = String(cfg.text_overflow);
//     }
// }
//
// /* ------------------------------------------------------------------------------------------------------------------ */
// export class TextInputColumn extends TableColumn {
//     constructor(id, config = {}) {
//         super(id, config);
//
//         this.defaults = {
//             input_color: [1, 1, 1, 0.8],
//             text_color: [1, 1, 1, 0.8],
//             font_size: 10,
//             font_family: 'sans-serif',
//             font_align: 'left',
//             interactive: true,
//         }
//         this.configuration = {...this.defaults, ...this.configuration};
//     }
// }
//
//
// /* ------------------------------------------------------------------------------------------------------------------ */
// export class TextInputCell extends TableCell {
//     static column_type = TextInputColumn;
//
//     constructor(id, row, column, value, config = {}) {
//         super(id, row, column, value, config);
//
//         /** @type {HTMLInputElement|null} */
//         this.input = null;
//
//         // last backend-accepted value
//         this._committedValue = (value !== undefined && value !== null) ? String(value) : "";
//
//         // used to avoid re-firing commit for the same value
//         this._lastSentValue = null;
//     }
//
//     _commit() {
//         if (!this.input) return;
//
//         const next = this.input.value;
//
//         console.log(`Committing ${next} from UI`);
//
//         // no-op if unchanged vs committed
//         if (next === this._committedValue) {
//             this.input.value = this._committedValue;
//             this.input.blur();
//             return;
//         }
//
//         // prevent spamming same value while waiting
//         if (this._lastSentValue === next) {
//             this.input.blur();
//             return;
//         }
//
//         this._lastSentValue = next;
//
//         // fire event upward; table/tablewidget should listen to this and send to backend
//         // (keeps this cell generic)
//         const payload = {
//             row_id: this.row,
//             column_id: this.column,
//             value: next,
//             cell_id: this.id,
//         };
//
//         this.accept(next);
//         // // preferred: callback provided in config
//         // if (typeof this.configuration?.on_commit === "function") {
//         //     this.configuration.on_commit(payload);
//         // } else if (typeof this.table?.on_cell_input === "function") {
//         //     // optional hook you may add on Table
//         //     this.table.on_cell_input(payload);
//         // } else if (typeof this.table?.widget?.callbacks?.get?.("event")?.call === "function") {
//         //     // optional hook if you attach widget reference
//         //     this.table.widget.callbacks.get("event").call({
//         //         id: this.table.widget.id,
//         //         event: "input",
//         //         data: payload,
//         //     });
//         // } else {
//         //     // as last resort, dispatch a DOM event on the input
//         //     this.input.dispatchEvent(new CustomEvent("table:input", {detail: payload, bubbles: true}));
//         // }
//
//         // UI state while waiting for backend: keep focus behavior sane
//         this.input.blur();
//     }
//
//     accept(value) {
//         // backend accepted value
//         const v = (value !== undefined && value !== null) ? String(value) : "";
//         this._lastSentValue = null;
//
//         if (!this.input) return;
//
//         this.update(v);
//
//         // accept animation
//         this.input.classList.remove("error");
//         this.input.classList.add("accepted");
//         this.input.addEventListener(
//             "animationend",
//             () => this.input && this.input.classList.remove("accepted"),
//             {once: true}
//         );
//     }
//
//     reject() {
//         // backend rejected: revert to committed
//         this._lastSentValue = null;
//
//         if (!this.input) return;
//
//         this.input.value = this._committedValue;
//
//         // reject animation
//         this.input.classList.remove("accepted");
//         this.input.classList.add("error");
//         this.input.addEventListener(
//             "animationend",
//             () => this.input && this.input.classList.remove("error"),
//             {once: true}
//         );
//     }
//
//     draw_cell(container) {
//         this.element = document.createElement("td");
//         this.element.classList.add("table-cell-input");
//
//         const cfg = this._getMergedStyleConfig();
//
//
//         this.element.style.border = "0.5px solid #999999";
//         this.element.style.padding = "1px";
//         this.element.style.verticalAlign = "middle";
//
//         this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
//         this.element.style.color = getColor(cfg.text_color ?? [0, 0, 0, 1]);
//         this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
//         this.element.style.fontFamily = cfg.font_family ?? "sans-serif";
//         this.element.style.textAlign = cfg.font_align ?? "left";
//
//         if (cfg.font_weight !== undefined) this.element.style.fontWeight = String(cfg.font_weight);
//         if (cfg.border !== undefined) this.element.style.border = String(cfg.border);
//         if (cfg.padding !== undefined) this.element.style.padding = String(cfg.padding);
//         if (cfg.white_space !== undefined) this.element.style.whiteSpace = String(cfg.white_space);
//         if (cfg.overflow !== undefined) this.element.style.overflow = String(cfg.overflow);
//         if (cfg.text_overflow !== undefined) this.element.style.textOverflow = String(cfg.text_overflow);
//
//         // Build input
//         this.input = document.createElement("input");
//         this.input.type = "text";
//         this.input.classList.add("tableInput");
//         this.input.value = this._committedValue;
//
//         // let CSS do most of the work; keep only what must follow overrides
//         if (cfg.input_color) this.input.style.borderColor = getColor(cfg.input_color);
//         else this.input.style.borderColor = ""; // fall back to css
//
//         // Enter => commit
//         this.input.addEventListener("keydown", (e) => {
//             if (e.key === "Enter") {
//                 e.preventDefault();
//                 this._commit();
//             } else if (e.key === "Escape") {
//                 e.preventDefault();
//                 // user cancels locally (no backend)
//                 this.input.value = this._committedValue;
//                 this.input.blur();
//             }
//         });
//
//         // Blur => revert to committed (same as old behavior)
//         this.input.addEventListener("blur", () => {
//             if (!this.input) return;
//             this.input.value = this._committedValue;
//         });
//
//         this.element.appendChild(this.input);
//         container.appendChild(this.element);
//     }
//
//     update(value) {
//         // This is for plain table updates (not accept/reject).
//         // If you want "backend sets value" to be treated as accepted, call accept(value) instead.
//         this.value = value;
//
//         if (!this.element || !this.input) return;
//
//         // this.input.value = (value !== undefined && value !== null) ? String(value) : "";
//         this.input.value = value;
//         this._committedValue = value;
//
//         // const cfg = this._getMergedStyleConfig();
//         // this._applyTdStyle(this.element, cfg);
//         // this._applyInputStyle(this.input, cfg);
//
//         // // do NOT overwrite user typing if focused
//         // const hasFocus = (document.activeElement === this.input);
//         // if (!hasFocus) {
//         //     const v = (value !== undefined && value !== null) ? String(value) : "";
//         //     this._committedValue = v;
//         //     this.input.value = v;
//         // }
//     }
// }
//
//
// /* ------------------------------------------------------------------------------------------------------------------ */
// export class NumberColumn extends TableColumn {
//     constructor(id, config = {}) {
//         super(id, config);
//
//         this.defaults = {
//             increment: 0.1,
//             align: 'right',  // left, center, right,
//             font_size: 10,
//         }
//         this.configuration = {...this.defaults, ...this.configuration};
//
//     }
// }
//
// /* ------------------------------------------------------------------------------------------------------------------ */
//
// /* ------------------------------------------------------------------------------------------------------------------ */
// export class NumberCell extends TableCell {
//     static column_type = NumberColumn;
//
//     constructor(id, row, column, value, config = {}) {
//         super(id, row, column, value, config);
//
//         this._lastFormatted = "";
//     }
//
//
//     draw_cell(container) {
//         this.element = document.createElement("td");
//
//         const cfg = this._getMergedStyleConfig();
//         // Base cell style
//         this.element.style.border = "0.5px solid #999999";
//         this.element.style.padding = "1px";
//         this.element.style.verticalAlign = "middle";
//
//         // Numeric look & alignment
//         this.element.style.textAlign = cfg.align ?? "right";
//         this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
//
//         // Monospace + stable digit widths if available
//         // (tabular-nums works on many fonts; monospace guarantees fixed width anyway)
//         this.element.style.fontFamily =
//             cfg.font_family ?? "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace";
//         this.element.style.fontVariantNumeric = "tabular-nums";
//         this.element.style.fontFeatureSettings = '"tnum" 1';
//
//         // Colors (support overrides)
//         this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
//         if (cfg.text_color) this.element.style.color = getColor(cfg.text_color);
//
//         // Initial content
//         const initial = this.value;
//
//         const formatted = formatNumberWithIncrement(initial, cfg.increment)
//         this._lastFormatted = formatted;
//         this.element.textContent = formatted;
//
//         // Optional extras
//         if (cfg.font_weight !== undefined) this.element.style.fontWeight = String(cfg.font_weight);
//         if (cfg.padding !== undefined) this.element.style.padding = String(cfg.padding);
//         if (cfg.border !== undefined) this.element.style.border = String(cfg.border);
//
//         container.appendChild(this.element);
//     }
//
//     update(value) {
//         this.value = value;
//         if (!this.element) return;
//
//         const cfg = this._getMergedStyleConfig();
//
//         // Re-apply style (in case overrides changed)
//         this.element.style.textAlign = cfg.align ?? "right";
//         this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
//         this.element.style.fontFamily =
//             cfg.font_family ?? "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace";
//         this.element.style.fontVariantNumeric = "tabular-nums";
//         this.element.style.fontFeatureSettings = '"tnum" 1';
//         this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
//         if (cfg.text_color) this.element.style.color = getColor(cfg.text_color);
//         if (cfg.font_weight !== undefined) this.element.style.fontWeight = String(cfg.font_weight);
//         if (cfg.padding !== undefined) this.element.style.padding = String(cfg.padding);
//         if (cfg.border !== undefined) this.element.style.border = String(cfg.border);
//
//         const formatted = formatNumberWithIncrement(value, cfg.increment);
//         if (formatted !== this._lastFormatted) {
//             this._lastFormatted = formatted;
//             this.element.textContent = formatted;
//         }
//     }
// }
//
// /* ------------------------------------------------------------------------------------------------------------------ */
// export class ButtonColumn extends TableColumn {
//     constructor(id, config = {}) {
//         super(id, config);
//
//         this.defaults = {
//             button_color: [0.4, 0.4, 0.2, 0.8],
//             text_color: [1, 1, 1, 1],
//             font_size: 10,
//             font_family: 'sans-serif',
//             font_align: 'center',
//             active: true,
//         }
//         this.configuration = {...this.defaults, ...this.configuration};
//     }
// }
//
// /* ------------------------------------------------------------------------------------------------------------------ */
//
// /* ------------------------------------------------------------------------------------------------------------------ */
// export class ButtonCell extends TableCell {
//     static column_type = ButtonColumn;
//
//     // value is the button text
//     constructor(id, row, column, value, config = {}) {
//         super(id, row, column, value, config);
//
//         /** @type {HTMLButtonElement|null} */
//         this.button = null;
//     }
//
//     draw_cell(container) {
//         this.element = document.createElement("td");
//         this.element.classList.add("table-cell-button");
//
//         const cfg = this._getMergedStyleConfig();
//
//         // td styling (match your other cells)
//         this.element.style.border = "0.5px solid #999999";
//         this.element.style.padding = "1px";
//         this.element.style.verticalAlign = "middle";
//
//         this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
//         if (cfg.text_color) this.element.style.color = getColor(cfg.text_color);
//         this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
//         this.element.style.fontFamily = cfg.font_family ?? "sans-serif";
//         this.element.style.textAlign = cfg.font_align ?? "center";
//
//         if (cfg.font_weight !== undefined) this.element.style.fontWeight = String(cfg.font_weight);
//         if (cfg.border !== undefined) this.element.style.border = String(cfg.border);
//         if (cfg.padding !== undefined) this.element.style.padding = String(cfg.padding);
//         if (cfg.white_space !== undefined) this.element.style.whiteSpace = String(cfg.white_space);
//         if (cfg.overflow !== undefined) this.element.style.overflow = String(cfg.overflow);
//         if (cfg.text_overflow !== undefined) this.element.style.textOverflow = String(cfg.text_overflow);
//
//         // create button
//         this.button = document.createElement("button");
//         this.button.classList.add("tableButton");
//         this.button.textContent = (this.value !== undefined && this.value !== null) ? String(this.value) : "";
//
//         // button colors
//         this.button.style.backgroundColor = getColor(cfg.button_color ?? [0.2, 0.2, 0.2, 0.8]);
//         this.button.style.color = getColor(cfg.text_color ?? [1, 1, 1, 1]);
//         this.button.style.fontSize = `${cfg.font_size ?? 12}pt`;
//         this.button.style.fontFamily = cfg.font_family ?? "sans-serif";
//         this.button.style.textAlign = cfg.font_align ?? "center";
//
//         // active/disabled
//         const active = (cfg.active !== undefined) ? !!cfg.active : true;
//         this.button.disabled = !active;
//         if (!active) this.button.classList.add("tableButton--disabled");
//
//         // click handler
//         this.button.addEventListener("click", (e) => {
//             if (!active) return;
//
//             // little pressed feedback (CSS uses :active too, but this helps for programmatic)
//             this.button.classList.add("pressed");
//             setTimeout(() => this.button && this.button.classList.remove("pressed"), 120);
//
//             console.log(`ButtonCell (${this.row}, ${this.column}) pressed`)
//
//
//         });
//
//         this.element.appendChild(this.button);
//         container.appendChild(this.element);
//     }
//
//     update(value) {
//         this.value = value;
//         if (!this.element || !this.button) return;
//
//         const cfg = this._getMergedStyleConfig();
//
//         // update text
//         this.button.textContent = (value !== undefined && value !== null) ? String(value) : "";
//
//         // in case overrides changed
//         this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
//         this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
//         this.element.style.fontFamily = cfg.font_family ?? "sans-serif";
//         this.element.style.textAlign = cfg.font_align ?? "center";
//         if (cfg.text_color) this.element.style.color = getColor(cfg.text_color);
//
//         this.button.style.backgroundColor = getColor(cfg.button_color ?? [0.2, 0.2, 0.2, 0.8]);
//         this.button.style.color = getColor(cfg.text_color ?? [1, 1, 1, 1]);
//         this.button.style.fontSize = `${cfg.font_size ?? 12}pt`;
//         this.button.style.fontFamily = cfg.font_family ?? "sans-serif";
//
//         const active = (cfg.active !== undefined) ? !!cfg.active : true;
//         this.button.disabled = !active;
//         this.button.classList.toggle("tableButton--disabled", !active);
//     }
// }
//
// /* ------------------------------------------------------------------------------------------------------------------ */
// export class CheckboxColumn extends TableColumn {
//     constructor(id, config = {}) {
//         super(id, config);
//         this.defaults = {
//             checkbox_color: [1, 1, 1, 0.7],
//             checkmark_color: [0, 0, 0, 1],
//             checkmark_type: 'cross',
//             checkbox_alignment: 'center',  // left, center, right
//             active: true,
//         }
//         this.configuration = {...this.defaults, ...this.configuration};
//     }
// }
//
// /* ------------------------------------------------------------------------------------------------------------------ */
//
// /* ------------------------------------------------------------------------------------------------------------------ */
// export class CheckboxCell extends TableCell {
//     static column_type = CheckboxColumn;
//
//     constructor(id, row, column, value, config = {}) {
//         super(id, row, column, value, config);
//
//         /** @type {HTMLInputElement|null} */
//         this.input = null;
//
//         /** @type {HTMLSpanElement|null} */
//         this.box = null;
//
//         /** @type {HTMLLabelElement|null} */
//         this.label = null;
//
//         // normalized state
//         this._checked = this._toBool(value);
//
//         // prevents feedback-loops when we update the DOM from code
//         this._suppressChange = false;
//     }
//
//     _toBool(v) {
//         if (v === true) return true;
//         if (v === false) return false;
//         if (v === 1) return true;
//         if (v === 0) return false;
//
//         if (typeof v === "string") {
//             const s = v.trim().toLowerCase();
//             if (["1", "true", "yes", "y", "on", "checked"].includes(s)) return true;
//             if (["0", "false", "no", "n", "off", "unchecked", ""].includes(s)) return false;
//         }
//
//         return !!v;
//     }
//
//     _applyTdStyle(td, cfg) {
//         td.style.border = "0.5px solid #999999";
//         td.style.padding = "1px";
//         td.style.verticalAlign = "middle";
//         td.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
//
//         const align = cfg.checkbox_alignment ?? "center";
//         td.style.textAlign = (align === "left" || align === "right") ? align : "center";
//
//         if (cfg.border !== undefined) td.style.border = String(cfg.border);
//         if (cfg.padding !== undefined) td.style.padding = String(cfg.padding);
//     }
//
//     _applyBoxStyle(box, cfg) {
//         const boxColor = getColor(cfg.checkbox_color ?? [1, 1, 1, 0.7]);
//         const markColor = getColor(cfg.checkmark_color ?? [0, 0, 0, 1]);
//         const markType = (cfg.checkmark_type ?? "check").toString().trim().toLowerCase();
//
//         box.style.setProperty("--checkbox-color", boxColor);
//         box.style.setProperty("--checkmark-color", markColor);
//         box.dataset.mark = markType; // "check" | "cross" | "dot"
//     }
//
//     _setVisualState(checked, active) {
//         if (!this.label) return;
//         this.label.classList.toggle("is-checked", !!checked);
//         this.label.classList.toggle("is-disabled", !active);
//     }
//
//     /**
//      * Called exactly once per user toggle (no double logs).
//      * Default behavior: update the UI immediately, then call your hook.
//      */
//     on_change(checked) {
//         // If your architecture is "backend authoritative", you can remove the optimistic update
//         // and only call this.update(...) once the backend confirms.
//         console.log(`CheckboxCell (${this.row}, ${this.column}) => ${checked}`);
//
//         // optimistic UI update so it visually flips immediately
//         this.update(checked);
//
//         // Example payload:
//         // const payload = { row_id: this.row, column_id: this.column, value: checked, cell_id: this.id };
//         // this.table?.widget?.callbacks?.get?.("event")?.call({ id: this.table.widget.id, event: "checkbox", data: payload });
//     }
//
//     draw_cell(container) {
//         this.element = document.createElement("td");
//         this.element.classList.add("table-cell-checkbox");
//
//         const cfg = this._getMergedStyleConfig();
//         this._applyTdStyle(this.element, cfg);
//
//         this.label = document.createElement("label");
//         this.label.classList.add("tableCheckbox");
//
//         // input drives the state; label click toggles it automatically (no manual click handler needed)
//         this.input = document.createElement("input");
//         this.input.type = "checkbox";
//         this.input.checked = this._checked;
//
//         const active = (cfg.active !== undefined) ? !!cfg.active : true;
//         this.input.disabled = !active;
//
//         this.box = document.createElement("span");
//         this.box.classList.add("tableCheckbox__box");
//         this._applyBoxStyle(this.box, cfg);
//
//         // initial visual sync
//         this._setVisualState(this._checked, active);
//
//         // SINGLE source of truth for toggles: the input's change event.
//         this.input.addEventListener("change", () => {
//             if (this._suppressChange) return;
//
//             const next = !!this.input.checked;
//
//             // avoid duplicate work if something weird triggers change twice
//             if (next === this._checked) return;
//
//             this._checked = next;
//
//             // keep visuals in sync immediately (so it always flips)
//             this._setVisualState(next, !this.input.disabled);
//
//             this.on_change(next);
//         });
//
//         this.label.appendChild(this.input);
//         this.label.appendChild(this.box);
//         this.element.appendChild(this.label);
//         container.appendChild(this.element);
//     }
//
//     update(value) {
//         this.value = value;
//         if (!this.element || !this.input || !this.box) return;
//
//         const cfg = this._getMergedStyleConfig();
//         this._applyTdStyle(this.element, cfg);
//         this._applyBoxStyle(this.box, cfg);
//
//         const active = (cfg.active !== undefined) ? !!cfg.active : true;
//         this.input.disabled = !active;
//
//         const next = this._toBool(value);
//
//         // if no actual change, just ensure visuals/disabled state are correct
//         if (next === this._checked && this.input.checked === next) {
//             this._setVisualState(next, active);
//             return;
//         }
//
//         // programmatic update: set checked without re-entering on_change
//         this._suppressChange = true;
//         this.input.checked = next;
//         this._suppressChange = false;
//
//         this._checked = next;
//         this._setVisualState(next, active);
//     }
// }
//
//
// /* ------------------------------------------------------------------------------------------------------------------ */
// export class SelectColumn extends TableColumn {
//     constructor(id, config = {}) {
//         super(id, config);
//         this.defaults = {
//             select_color: [0.8, 0.8, 0.8, 0.7],
//             text_color: [0.8, 0.8, 0.8, 0.7],
//             font_size: 12,
//             options: {},
//             font_family: 'sans-serif',
//             font_align: 'center',
//             active: true,
//         }
//         this.configuration = {...this.defaults, ...this.configuration};
//     }
// }
//
// /* ------------------------------------------------------------------------------------------------------------------ */
// export class SelectCell extends TableCell {
//     static column_type = SelectColumn;
//
//     constructor(id, row, column, value, config = {}) {
//         super(id, row, column, value, config);
//
//         /** @type {HTMLSelectElement|null} */
//         this.select = null;
//
//         // last backend-accepted value (store as string id)
//         this._committedValue = (value !== undefined && value !== null) ? String(value) : "";
//
//         // used to avoid re-firing commit for the same value
//         this._lastSentValue = null;
//
//         // remember last "in-progress" selection while focused (for Esc revert)
//         this._editingValue = this._committedValue;
//     }
//
//     on_select(value) {
//         console.log(`Selected value: ${value}`);
//     }
//
//     _commit() {
//         if (!this.select) return;
//
//         const next = this.select.value;
//
//         console.log(`Committing ${next} from UI`);
//
//         // no-op if unchanged vs committed
//         if (next === this._committedValue) {
//             this.select.value = this._committedValue;
//             this.select.blur();
//             return;
//         }
//
//         // prevent spamming same value while waiting
//         if (this._lastSentValue === next) {
//             this.select.blur();
//             return;
//         }
//
//         this._lastSentValue = next;
//
//         // placeholder hook (do not modify this function per your request)
//         this.on_select(next);
//
//         // optimistic accept animation like TextInputCell
//         this.accept(next);
//
//         this.select.blur();
//     }
//
//     accept(value) {
//         const v = (value !== undefined && value !== null) ? String(value) : "";
//         this._lastSentValue = null;
//
//         if (!this.select) return;
//
//         this.update(v);
//
//         // accept animation
//         this.select.classList.remove("error");
//         this.select.classList.add("accepted");
//         this.select.addEventListener(
//             "animationend",
//             () => this.select && this.select.classList.remove("accepted"),
//             {once: true}
//         );
//     }
//
//     reject() {
//         this._lastSentValue = null;
//
//         if (!this.select) return;
//
//         // revert to committed
//         this.select.value = this._committedValue;
//
//         // reject animation
//         this.select.classList.remove("accepted");
//         this.select.classList.add("error");
//         this.select.addEventListener(
//             "animationend",
//             () => this.select && this.select.classList.remove("error"),
//             {once: true}
//         );
//     }
//
//     _rebuildOptions(cfg) {
//         if (!this.select) return;
//
//         const optionsObj = cfg.options ?? {};
//         this.select.innerHTML = "";
//
//         // options are {id: label}
//         for (const [id, label] of Object.entries(optionsObj)) {
//             const opt = document.createElement("option");
//             opt.value = String(id);
//             opt.textContent = (label !== undefined && label !== null) ? String(label) : "";
//             this.select.appendChild(opt);
//         }
//
//         // if current committed value isn't present, keep select value empty
//         this.select.value = this._committedValue;
//     }
//
//     draw_cell(container) {
//         this.element = document.createElement("td");
//         this.element.classList.add("table-cell-select");
//
//         const cfg = this._getMergedStyleConfig();
//
//         // td styling (match others)
//         this.element.style.border = "0.5px solid #999999";
//         this.element.style.padding = "1px";
//         this.element.style.verticalAlign = "middle";
//
//         this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
//         this.element.style.color = getColor(cfg.text_color ?? [0, 0, 0, 1]);
//         this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
//         this.element.style.fontFamily = cfg.font_family ?? "sans-serif";
//         this.element.style.textAlign = cfg.font_align ?? "center";
//
//         if (cfg.font_weight !== undefined) this.element.style.fontWeight = String(cfg.font_weight);
//         if (cfg.border !== undefined) this.element.style.border = String(cfg.border);
//         if (cfg.padding !== undefined) this.element.style.padding = String(cfg.padding);
//         if (cfg.white_space !== undefined) this.element.style.whiteSpace = String(cfg.white_space);
//         if (cfg.overflow !== undefined) this.element.style.overflow = String(cfg.overflow);
//         if (cfg.text_overflow !== undefined) this.element.style.textOverflow = String(cfg.text_overflow);
//
//         // Build select
//         this.select = document.createElement("select");
//         this.select.classList.add("tableSelect");
//
//         // base colors
//         if (cfg.select_color) this.select.style.borderColor = getColor(cfg.select_color);
//         else this.select.style.borderColor = ""; // fall back to css
//
//         // active/disabled
//         const active = (cfg.active !== undefined) ? !!cfg.active : true;
//         this.select.disabled = !active;
//         if (!active) this.select.classList.add("tableSelect--disabled");
//         else this.select.classList.remove("tableSelect--disabled");
//
//         // options
//         this._rebuildOptions(cfg);
//
//         // initial value
//         this.select.value = this._committedValue;
//
//         // focus bookkeeping
//         this.select.addEventListener("focus", () => {
//             if (!this.select) return;
//             this._editingValue = this.select.value;
//         });
//
//         // Change => commit immediately (like usual selects)
//         this.select.addEventListener("change", () => {
//             this._commit();
//         });
//
//         // Keyboard handling: Enter commits, Escape rejects (local)
//         this.select.addEventListener("keydown", (e) => {
//             if (e.key === "Enter") {
//                 e.preventDefault();
//                 this._commit();
//             } else if (e.key === "Escape") {
//                 e.preventDefault();
//                 if (!this.select) return;
//                 this.select.value = this._committedValue;
//                 this.select.blur();
//             }
//         });
//
//         // Blur => revert to committed (same behavior pattern as TextInputCell)
//         this.select.addEventListener("blur", () => {
//             if (!this.select) return;
//             this.select.value = this._committedValue;
//         });
//
//         this.element.appendChild(this.select);
//         container.appendChild(this.element);
//     }
//
//     update(value) {
//         this.value = value;
//         if (!this.element || !this.select) return;
//
//         const cfg = this._getMergedStyleConfig();
//
//         // re-apply td style (in case overrides changed)
//         this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
//         this.element.style.color = getColor(cfg.text_color ?? [0, 0, 0, 1]);
//         this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
//         this.element.style.fontFamily = cfg.font_family ?? "sans-serif";
//         this.element.style.textAlign = cfg.font_align ?? "center";
//
//         if (cfg.font_weight !== undefined) this.element.style.fontWeight = String(cfg.font_weight);
//         if (cfg.border !== undefined) this.element.style.border = String(cfg.border);
//         if (cfg.padding !== undefined) this.element.style.padding = String(cfg.padding);
//         if (cfg.white_space !== undefined) this.element.style.whiteSpace = String(cfg.white_space);
//         if (cfg.overflow !== undefined) this.element.style.overflow = String(cfg.overflow);
//         if (cfg.text_overflow !== undefined) this.element.style.textOverflow = String(cfg.text_overflow);
//
//         // active/disabled may change
//         const active = (cfg.active !== undefined) ? !!cfg.active : true;
//         this.select.disabled = !active;
//         this.select.classList.toggle("tableSelect--disabled", !active);
//
//         // options may change over time
//         this._rebuildOptions(cfg);
//
//         // set committed value
//         const v = (value !== undefined && value !== null) ? String(value) : "";
//         this._committedValue = v;
//         this.select.value = v;
//     }
// }
//
//
// /* ------------------------------------------------------------------------------------------------------------------ */
// export class MultiSelectColumn extends TableColumn {
//     constructor(id, config = {}) {
//         super(id, config);
//         this.defaults = {
//             select_color: [0.8, 0.8, 0.8, 0.7],
//             text_color: [0.8, 0.8, 0.8, 0.7],
//             font_size: 12,
//             options: {},              // {id: label}
//             font_family: "sans-serif",
//             font_align: "left",
//             active: true,
//
//             // display behavior
//             max_labels_inline: 2,     // show up to N labels; otherwise show "X selected"
//             placeholder: "Select…",
//         };
//         this.configuration = {...this.defaults, ...this.configuration};
//     }
// }
//
// export class MultiSelectCell extends TableCell {
//     static column_type = MultiSelectColumn;
//
//     constructor(id, row, column, value, config = {}) {
//         super(id, row, column, value, config);
//
//         /** @type {HTMLDivElement|null} */
//         this.root = null;
//         /** @type {HTMLButtonElement|null} */
//         this.button = null;
//
//         // Menu is portaled to document.body (so it won't be clipped by widget/table overflow)
//         /** @type {HTMLDivElement|null} */
//         this.menu = null;
//
//         this._committed = this._normValue(value); // array of string ids
//         this._editing = [...this._committed];
//         this._lastSent = null;
//         this._open = false;
//
//         // click outside root+menu => commit
//         this._outsideClickHandler = (e) => {
//             if (!this.root || !this.menu) return;
//             const t = e.target;
//             if (!this.root.contains(t) && !this.menu.contains(t)) {
//                 this._commit();
//             }
//         };
//
//         // keep menu aligned during scroll/resize
//         this._onReposition = () => {
//             if (this._open) this._positionMenu();
//         };
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     _normValue(v) {
//         if (Array.isArray(v)) return v.map(x => String(x));
//         if (v === undefined || v === null) return [];
//         if (typeof v === "string") {
//             const s = v.trim();
//             if (!s) return [];
//             return s.split(",").map(x => x.trim()).filter(Boolean).map(String);
//         }
//         return [String(v)];
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     on_select(values) {
//         console.log(`Selected values: ${values}`);
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     _ensureMenuExists() {
//         if (this.menu) return;
//
//         this.menu = document.createElement("div");
//         // Important: give it a "portal" class so CSS applies outside the table
//         this.menu.classList.add("tableMultiSelect__menu", "tableMultiSelect__menu--portal");
//
//         // JS positions it; CSS handles look
//         this.menu.style.position = "fixed";
//         this.menu.style.zIndex = "99999";
//         this.menu.style.display = "none";
//
//         // allow keyboard focus inside menu if you later want it (optional)
//         this.menu.tabIndex = -1;
//
//         document.body.appendChild(this.menu);
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     _labelFor(id, optionsObj) {
//         const lbl = optionsObj?.[id];
//         return (lbl !== undefined && lbl !== null) ? String(lbl) : String(id);
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     _summaryText(cfg) {
//         const optionsObj = cfg.options ?? {};
//         const ids = this._editing;
//
//         if (!ids.length) return cfg.placeholder ?? "Select…";
//
//         const maxInline = Number(cfg.max_labels_inline ?? 2);
//         const labels = ids.map(id => this._labelFor(id, optionsObj));
//
//         if (labels.length <= maxInline) return labels.join(", ");
//         return `${labels.length} selected`;
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     _renderMenu() {
//         if (!this.menu || !this.button) return;
//
//         const cfg = this._getMergedStyleConfig();
//         const optionsObj = cfg.options ?? {};
//         const active = (cfg.active !== undefined) ? !!cfg.active : true;
//
//         // button summary
//         this.button.textContent = this._summaryText(cfg);
//         this.button.disabled = !active;
//         this.button.classList.toggle("tableMultiSelect__button--disabled", !active);
//
//         // menu items
//         this.menu.innerHTML = "";
//         const idsInSet = new Set(this._editing);
//
//         for (const [idRaw, label] of Object.entries(optionsObj)) {
//             const id = String(idRaw);
//
//             const item = document.createElement("label");
//             item.classList.add("tableMultiSelect__item");
//
//             const cb = document.createElement("input");
//             cb.type = "checkbox";
//             cb.checked = idsInSet.has(id);
//             cb.disabled = !active;
//
//             const txt = document.createElement("span");
//             txt.classList.add("tableMultiSelect__label");
//             txt.textContent = (label !== undefined && label !== null) ? String(label) : id;
//
//             cb.addEventListener("change", () => {
//                 const set = new Set(this._editing);
//
//                 if (cb.checked) set.add(id);
//                 else set.delete(id);
//
//                 const nextArr = Array.from(set);
//                 this._editing = nextArr;
//
//                 // update summary immediately
//                 this.button.textContent = this._summaryText(cfg);
//
//                 // keep menu positioned if its height changes
//                 this._positionMenu();
//
//                 // trigger immediately on each toggle (dedup via signature)
//                 const sig = [...nextArr].sort().join("|");
//                 if (this._lastSent !== sig) {
//                     this._lastSent = sig;
//
//                     // fire hook immediately
//                     this.on_select([...nextArr]);
//
//                     // optimistic: treat as committed so outside-click commit won't re-fire
//                     this._committed = [...nextArr];
//                 }
//             });
//
//             item.appendChild(cb);
//             item.appendChild(txt);
//             this.menu.appendChild(item);
//         }
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     _positionMenu() {
//         if (!this.button || !this.menu) return;
//
//         const rect = this.button.getBoundingClientRect();
//         const gap = 4;
//
//         // show invisibly to measure size
//         const prevDisplay = this.menu.style.display;
//         const prevVis = this.menu.style.visibility;
//         this.menu.style.visibility = "hidden";
//         this.menu.style.display = "block";
//
//         // match button width at minimum
//         const minW = Math.max(140, rect.width);
//         this.menu.style.minWidth = `${minW}px`;
//
//         const menuRect = this.menu.getBoundingClientRect();
//         const vw = window.innerWidth || document.documentElement.clientWidth;
//         const vh = window.innerHeight || document.documentElement.clientHeight;
//
//         // default: below, left aligned
//         let left = rect.left;
//         let top = rect.bottom + gap;
//
//         // clamp horizontally
//         if (left + menuRect.width > vw - 8) left = Math.max(8, vw - 8 - menuRect.width);
//         if (left < 8) left = 8;
//
//         // flip above if needed
//         if (top + menuRect.height > vh - 8) {
//             const above = rect.top - gap - menuRect.height;
//             if (above >= 8) top = above;
//             else top = Math.max(8, vh - 8 - menuRect.height);
//         }
//
//         this.menu.style.left = `${left}px`;
//         this.menu.style.top = `${top}px`;
//
//         // restore visibility; keep open state
//         this.menu.style.visibility = prevVis || "";
//         this.menu.style.display = this._open ? "block" : (prevDisplay || "none");
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     _openMenu() {
//         if (!this.root || !this.button) return;
//         if (this._open) return;
//
//         this._ensureMenuExists();
//         this._open = true;
//
//         this.root.classList.add("is-open");
//
//         this._renderMenu();
//         this._positionMenu();
//         if (this.menu) this.menu.style.display = "block";
//
//         // commit on outside click
//         document.addEventListener("mousedown", this._outsideClickHandler, true);
//
//         // keep anchored on scroll/resize (capture scroll from any container)
//         window.addEventListener("resize", this._onReposition, true);
//         window.addEventListener("scroll", this._onReposition, true);
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     _close() {
//         if (!this.root) return;
//         if (!this._open) return;
//
//         this._open = false;
//         this.root.classList.remove("is-open");
//
//         if (this.menu) this.menu.style.display = "none";
//
//         document.removeEventListener("mousedown", this._outsideClickHandler, true);
//         window.removeEventListener("resize", this._onReposition, true);
//         window.removeEventListener("scroll", this._onReposition, true);
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     _toggleMenu() {
//         this._open ? this._close() : this._openMenu();
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     _commit() {
//
//         const next = [...this._editing].sort().join("|");
//         const committed = [...this._committed].sort().join("|");
//
//         if (next === committed) {
//             this._close();
//             return;
//         }
//         if (this._lastSent === next) {
//             this._close();
//             return;
//         }
//
//         this._lastSent = next;
//
//         // placeholder hook (do not add anything else to it)
//         this.on_select([...this._editing]);
//
//         // optimistic accept animation + state update
//         this.accept([...this._editing]);
//
//         this._close();
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     accept(value) {
//         const v = this._normValue(value);
//         this._lastSent = null;
//
//         this.update(v);
//
//         if (!this.button) return;
//         this.button.classList.remove("error");
//         this.button.classList.add("accepted");
//         this.button.addEventListener(
//             "animationend",
//             () => this.button && this.button.classList.remove("accepted"),
//             {once: true}
//         );
//     }
//
//     /* -------------------------------------------------------------------------------------------------------------- */
//     reject() {
//         this._lastSent = null;
//         this._editing = [...this._committed];
//
//         const cfg = this._getMergedStyleConfig();
//         if (this.button) this.button.textContent = this._summaryText(cfg);
//         if (this._open) this._renderMenu();
//
//         if (!this.button) return;
//         this.button.classList.remove("accepted");
//         this.button.classList.add("error");
//         this.button.addEventListener(
//             "animationend",
//             () => this.button && this.button.classList.remove("error"),
//             {once: true}
//         );
//     }
//
//     draw_cell(container) {
//         this.element = document.createElement("td");
//         this.element.classList.add("table-cell-multiselect");
//
//         const cfg = this._getMergedStyleConfig();
//
//         // td styling
//         this.element.style.border = "0.5px solid #999999";
//         this.element.style.padding = "1px";
//         this.element.style.verticalAlign = "middle";
//         this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
//         this.element.style.color = getColor(cfg.text_color ?? [0, 0, 0, 1]);
//         this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
//         this.element.style.fontFamily = cfg.font_family ?? "sans-serif";
//         this.element.style.textAlign = cfg.font_align ?? "left";
//
//         // root
//         this.root = document.createElement("div");
//         this.root.classList.add("tableMultiSelect");
//
//         // focusable so focusout works for keyboard users
//         this.root.tabIndex = 0;
//
//         // button
//         this.button = document.createElement("button");
//         this.button.type = "button";
//         this.button.classList.add("tableMultiSelect__button");
//         if (cfg.select_color) this.button.style.borderColor = getColor(cfg.select_color);
//
//         this.button.addEventListener("click", (e) => {
//             e.preventDefault();
//             const active = (cfg.active !== undefined) ? !!cfg.active : true;
//             if (!active) return;
//             this._toggleMenu();
//         });
//
//         // keyboard: Enter toggles, Esc cancels, ArrowDown opens
//         this.button.addEventListener("keydown", (e) => {
//             if (e.key === "Enter") {
//                 e.preventDefault();
//                 this._toggleMenu();
//             } else if (e.key === "Escape") {
//                 e.preventDefault();
//                 this._close();
//             } else if (e.key === "ArrowDown") {
//                 e.preventDefault();
//                 this._openMenu();
//             }
//         });
//
//         // commit when focus leaves the in-cell control AND the portaled menu
//         this.root.addEventListener("focusout", (e) => {
//             const next = e.relatedTarget;
//             if (!this.root) return;
//
//             // If focus goes into the portaled menu, don't commit
//             if (this.menu && next && this.menu.contains(next)) return;
//
//             const leftRoot = (!next || !this.root.contains(next));
//             const leftMenu = (!this.menu || !next || !this.menu.contains(next));
//             if (leftRoot && leftMenu) {
//                 this._commit();
//             }
//         });
//
//         this.root.appendChild(this.button);
//         this.element.appendChild(this.root);
//         container.appendChild(this.element);
//
//         // initial state
//         this._editing = [...this._committed];
//         this.button.textContent = this._summaryText(cfg);
//     }
//
//     update(value) {
//         this.value = value;
//
//         if (!this.element || !this.root || !this.button) return;
//
//         const cfg = this._getMergedStyleConfig();
//
//         // re-apply td styling
//         this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
//         this.element.style.color = getColor(cfg.text_color ?? [0, 0, 0, 1]);
//         this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
//         this.element.style.fontFamily = cfg.font_family ?? "sans-serif";
//         this.element.style.textAlign = cfg.font_align ?? "left";
//
//         // committed value updates from backend
//         this._committed = this._normValue(value);
//         this._editing = [...this._committed];
//
//         // refresh button/menu
//         this.button.textContent = this._summaryText(cfg);
//         if (this._open) {
//             this._renderMenu();
//             this._positionMenu();
//         }
//     }
// }
//
// /* ------------------------------------------------------------------------------------------------------------------ */
// export class SliderColumn extends TableColumn {
//     constructor(id, config = {}) {
//         super(id, config);
//         this.defaults = {
//             slider_color: [0.8, 0.8, 0.8, 0.7],   // bar + base color
//             text_color: [0.8, 0.8, 0.8, 1],
//             background_opacity: 0.12,       // same color as bar, but transparent
//             min_value: 0,
//             max_value: 100,
//             increment: 1,
//             text_align: "center",           // left | center | right
//             font_size: 9,
//             font_family: "monospace",
//             active: true,                   // optional: disable interaction
//             padding: "1px",                 // keep consistent with other cells (optional)
//             border: "0.5px solid #999999",      // optional
//         };
//         this.configuration = {...this.defaults, ...this.configuration};
//     }
// }
//
// export class SliderCell extends TableCell {
//     static column_type = SliderColumn;
//
//     constructor(id, row, column, value, config = {}) {
//         super(id, row, column, value, config);
//
//         /** @type {HTMLDivElement|null} */
//         this.sliderEl = null;
//         /** @type {HTMLDivElement|null} */
//         this.fillEl = null;
//         /** @type {HTMLSpanElement|null} */
//         this.valueEl = null;
//
//         this._dragging = false;
//         this._lastValue = null;
//         this._pointerId = null;
//
//         this._min = 0;
//         this._max = 100;
//         this._inc = 1;
//         this._decimals = 0;
//         this._valueType = "int";
//     }
//
//     on_value_change(value) {
//         // Hook for your table/widget to forward to backend
//         console.log(`SliderCell (${this.row}, ${this.column}) => ${value}`);
//     }
//
//     _computeNumberMeta(cfg) {
//         const inc = parseFloat(cfg.increment ?? 1);
//         const decimals = Math.max(0, (inc.toString().split(".")[1] || "").length);
//         const valueType = (inc % 1 === 0) ? "int" : "float";
//         return {inc, decimals, valueType};
//     }
//
//     _clampSnap(v) {
//         let x = Number(v);
//         if (!Number.isFinite(x)) x = this._min;
//
//         // clamp
//         x = Math.max(this._min, Math.min(this._max, x));
//
//         // snap to increment
//         x = Math.round(x / this._inc) * this._inc;
//         if (this._valueType === "int") x = Math.round(x);
//         else x = parseFloat(x.toFixed(this._decimals));
//
//         // re-clamp after rounding edge cases
//         x = Math.max(this._min, Math.min(this._max, x));
//         return x;
//     }
//
//     _pctFromValue(v) {
//         const denom = (this._max - this._min);
//         if (!denom) return 0;
//         return Math.min(1, Math.max(0, (v - this._min) / denom));
//     }
//
//     _formatValue(v) {
//         return (this._valueType === "int") ? Number(v).toFixed(0) : Number(v).toFixed(this._decimals);
//     }
//
//     _applyTdStyle(td, cfg) {
//         td.style.border = cfg.border ?? "0.5px solid #999999";
//         td.style.padding = cfg.padding ?? "1px";
//         td.style.verticalAlign = "middle";
//         td.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
//         td.style.color = getColor(cfg.text_color ?? [0.8, 0.8, 0.8, 1]);
//         td.style.fontSize = `${cfg.font_size ?? 12}pt`;
//         td.style.fontFamily = cfg.font_family ?? "monospace";
//         td.style.textAlign = "left"; // internal layout handles text alignment
//
//         if (cfg.font_weight !== undefined) td.style.fontWeight = String(cfg.font_weight);
//         if (cfg.white_space !== undefined) td.style.whiteSpace = String(cfg.white_space);
//         if (cfg.overflow !== undefined) td.style.overflow = String(cfg.overflow);
//         if (cfg.text_overflow !== undefined) td.style.textOverflow = String(cfg.text_overflow);
//     }
//
//     _applySliderStyle(cfg) {
//         if (!this.sliderEl || !this.fillEl || !this.valueEl) return;
//
//         const bar = getColor(cfg.slider_color ?? [1, 0, 0, 0.7]);
//
//         // derive "same color but very transparent" background
//         const sc = (cfg.slider_color ?? [1, 0, 0, 0.7]).slice();
//         sc[3] = (cfg.background_opacity !== undefined) ? Number(cfg.background_opacity) : 0.12;
//         const bg = getColor(sc);
//
//         this.sliderEl.style.setProperty("--ts-bar", bar);
//         this.sliderEl.style.setProperty("--ts-bg", bg);
//
//         const align = (cfg.text_align ?? "center").toString().toLowerCase();
//         this.valueEl.dataset.align = (align === "left" || align === "right") ? align : "center";
//
//         // disable interaction if requested
//         const active = (cfg.active !== undefined) ? !!cfg.active : true;
//         this.sliderEl.classList.toggle("is-disabled", !active);
//         this.sliderEl.style.pointerEvents = active ? "auto" : "none";
//         this.sliderEl.style.cursor = active ? "pointer" : "default";
//     }
//
//     _setUIValue(v) {
//         if (!this.fillEl || !this.valueEl) return;
//
//         const pct = this._pctFromValue(v) * 100;
//         this.fillEl.style.width = `${pct}%`;
//         this.valueEl.textContent = this._formatValue(v);
//     }
//
//     _valueFromPointer(clientX) {
//         if (!this.sliderEl) return this._min;
//
//         const rect = this.sliderEl.getBoundingClientRect();
//         const track = rect.width || 1;
//
//         const pos = clientX - rect.left;
//         const rawPct = Math.max(0, Math.min(1, pos / track));
//         const raw = this._min + rawPct * (this._max - this._min);
//
//         return this._clampSnap(raw);
//     }
//
//     _bindPointerHandlers() {
//         if (!this.sliderEl) return;
//
//         const onMove = (e) => {
//             if (!this._dragging) return;
//             const v = this._valueFromPointer(e.clientX);
//
//             // avoid pointless DOM churn
//             if (v === this._lastValue) return;
//
//             this._lastValue = v;
//             this._setUIValue(v);
//         };
//
//         const onUp = (e) => {
//             if (!this._dragging) return;
//
//             this._dragging = false;
//
//             try {
//                 this.sliderEl.releasePointerCapture(this._pointerId);
//             } catch (_) {
//             }
//             this._pointerId = null;
//
//             // send final value
//             const finalValue = (this._lastValue !== null) ? this._lastValue : this._clampSnap(this.value);
//             this.value = finalValue;
//             this.on_value_change(finalValue);
//
//             // small accepted blink like your other controls
//             this.sliderEl.classList.add("accepted");
//             this.sliderEl.addEventListener("animationend", () => {
//                 this.sliderEl && this.sliderEl.classList.remove("accepted");
//             }, {once: true});
//         };
//
//         this.sliderEl.addEventListener("pointerdown", (e) => {
//             if (e.button !== 0) return;
//             e.preventDefault();
//
//             this._dragging = true;
//             this._pointerId = e.pointerId;
//             this.sliderEl.setPointerCapture(e.pointerId);
//
//             const v = this._valueFromPointer(e.clientX);
//             this._lastValue = v;
//             this._setUIValue(v);
//         });
//
//         this.sliderEl.addEventListener("pointermove", onMove);
//         this.sliderEl.addEventListener("pointerup", onUp);
//         this.sliderEl.addEventListener("pointercancel", onUp);
//         this.sliderEl.addEventListener("lostpointercapture", () => {
//             // safety: if capture is lost mid-drag, end drag
//             if (!this._dragging) return;
//             this._dragging = false;
//             this._pointerId = null;
//         });
//     }
//
//     draw_cell(container) {
//         this.element = document.createElement("td");
//         this.element.classList.add("table-cell-slider");
//
//         const cfg = this._getMergedStyleConfig();
//
//         // number meta
//         this._min = Number(cfg.min_value ?? 0);
//         this._max = Number(cfg.max_value ?? 100);
//         const meta = this._computeNumberMeta(cfg);
//         this._inc = meta.inc;
//         this._decimals = meta.decimals;
//         this._valueType = meta.valueType;
//
//         this._applyTdStyle(this.element, cfg);
//
//         // build slider DOM
//         this.sliderEl = document.createElement("div");
//         this.sliderEl.classList.add("tableSlider");
//         this.sliderEl.setAttribute("role", "slider");
//         this.sliderEl.setAttribute("aria-valuemin", String(this._min));
//         this.sliderEl.setAttribute("aria-valuemax", String(this._max));
//
//         // background track (same color as bar but transparent)
//         const bg = document.createElement("div");
//         bg.classList.add("tableSlider__bg");
//
//         // fill bar
//         this.fillEl = document.createElement("div");
//         this.fillEl.classList.add("tableSlider__fill");
//
//         // value label
//         this.valueEl = document.createElement("span");
//         this.valueEl.classList.add("tableSlider__value");
//
//         this.sliderEl.appendChild(bg);
//         this.sliderEl.appendChild(this.fillEl);
//         this.sliderEl.appendChild(this.valueEl);
//
//         this.element.appendChild(this.sliderEl);
//         container.appendChild(this.element);
//
//         // apply style + initial value
//         this._applySliderStyle(cfg);
//
//         const initial = this._clampSnap(this.value ?? this._min);
//         this.value = initial;
//         this._lastValue = initial;
//         this._setUIValue(initial);
//
//         // handlers
//         this._bindPointerHandlers();
//     }
//
//     update(value) {
//         this.value = value;
//
//         if (!this.element || !this.sliderEl) return;
//
//         const cfg = this._getMergedStyleConfig();
//
//         // re-apply td + slider style in case overrides changed
//         this._applyTdStyle(this.element, cfg);
//
//         // update number meta (min/max/inc can change)
//         this._min = Number(cfg.min_value ?? 0);
//         this._max = Number(cfg.max_value ?? 100);
//         const meta = this._computeNumberMeta(cfg);
//         this._inc = meta.inc;
//         this._decimals = meta.decimals;
//         this._valueType = meta.valueType;
//
//         this.sliderEl.setAttribute("aria-valuemin", String(this._min));
//         this.sliderEl.setAttribute("aria-valuemax", String(this._max));
//
//         this._applySliderStyle(cfg);
//
//         const v = this._clampSnap(value ?? this._min);
//         this._lastValue = v;
//         this._setUIValue(v);
//     }
// }
//
//
// /* ------------------------------------------------------------------------------------------------------------------ */
// export class IndicatorColumn extends TableColumn {
//     constructor(id, config = {}) {
//         super(id, config);
//
//         this.defaults = {
//             indicator_color: [1, 1, 1, 0.7], // default circle color
//             text_color: [1, 1, 1, 0.85],
//             label: "",                       // optional default label
//             alignment: "center",             // left | center | right  (group alignment)
//             size_ratio: 0.8,                 // circle diameter relative to cell height
//             gap_px: 6,                       // space between circle and label
//             font_size: 12,
//             font_family: "sans-serif",
//             padding: "1px",
//             border: "0.5px solid #999999",
//         };
//
//         // IMPORTANT: merge defaults into existing column config (like your other columns)
//         this.configuration = {...this.defaults, ...this.configuration, ...config};
//     }
// }
//
// export class IndicatorCell extends TableCell {
//     static column_type = IndicatorColumn;
//
//     constructor(id, row, column, value, config = {}) {
//         super(id, row, column, value, config);
//
//         /** @type {HTMLDivElement|null} */
//         this.wrapEl = null;
//         /** @type {HTMLSpanElement|null} */
//         this.dotEl = null;
//         /** @type {HTMLSpanElement|null} */
//         this.labelEl = null;
//     }
//
//     _applyTdStyle(td, cfg) {
//         td.style.border = cfg.border ?? "0.5px solid #999999";
//         td.style.padding = cfg.padding ?? "1px";
//         td.style.verticalAlign = "middle";
//         td.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
//
//         td.style.color = getColor(cfg.text_color ?? [1, 1, 1, 0.85]);
//         td.style.fontSize = `${cfg.font_size ?? 12}pt`;
//         td.style.fontFamily = cfg.font_family ?? "sans-serif";
//
//         if (cfg.font_weight !== undefined) td.style.fontWeight = String(cfg.font_weight);
//         if (cfg.white_space !== undefined) td.style.whiteSpace = String(cfg.white_space);
//         if (cfg.overflow !== undefined) td.style.overflow = String(cfg.overflow);
//         if (cfg.text_overflow !== undefined) td.style.textOverflow = String(cfg.text_overflow);
//     }
//
//     _normValue(value) {
//         // supports:
//         // - string label
//         // - { color: [r,g,b,a], label: "..." }
//         // - { indicator_color: [...], label: "..." }
//         // - [colorArray, label]  (tuple-like)
//         // - direct color array [r,g,b,a]
//         let color = undefined;
//         let label = undefined;
//
//         if (Array.isArray(value)) {
//             // either color array, or [color,label]
//             if (value.length === 4 && value.every(n => typeof n === "number")) {
//                 color = value;
//             } else if (value.length >= 1 && Array.isArray(value[0])) {
//                 color = value[0];
//                 if (value.length > 1) label = value[1];
//             }
//         } else if (value && typeof value === "object") {
//             if (Array.isArray(value.color)) color = value.color;
//             if (Array.isArray(value.indicator_color)) color = value.indicator_color;
//             if (value.label !== undefined) label = value.label;
//         } else if (typeof value === "string" || typeof value === "number") {
//             // treat as label
//             label = String(value);
//         }
//
//         return {color, label};
//     }
//
//     _applyIndicatorStyle(cfg, value) {
//         if (!this.wrapEl || !this.dotEl || !this.labelEl) return;
//
//         const {color: vColor, label: vLabel} = this._normValue(value);
//
//         const circleColor = getColor(vColor ?? cfg.indicator_color ?? [1, 1, 1, 0.7]);
//         this.dotEl.style.setProperty("--ti-dot", circleColor);
//
//         const gap = Number(cfg.gap_px ?? 6);
//         this.wrapEl.style.setProperty("--ti-gap", `${gap}px`);
//
//         const ratio = Math.max(0.1, Math.min(1.0, Number(cfg.size_ratio ?? 0.8)));
//         this.wrapEl.style.setProperty("--ti-size", String(ratio));
//
//         const align = (cfg.alignment ?? "center").toString().toLowerCase();
//         this.wrapEl.dataset.align = (align === "left" || align === "right") ? align : "center";
//
//         // label: value label wins, else cfg.label
//         const label = (vLabel !== undefined && vLabel !== null) ? String(vLabel) : (cfg.label ?? "");
//         const hasLabel = label.trim().length > 0;
//
//         this.labelEl.textContent = hasLabel ? label : "";
//         this.labelEl.style.display = hasLabel ? "" : "none";
//         this.wrapEl.classList.toggle("has-label", hasLabel);
//     }
//
//     draw_cell(container) {
//         this.element = document.createElement("td");
//         this.element.classList.add("table-cell-indicator");
//
//         const cfg = this._getMergedStyleConfig();
//         this._applyTdStyle(this.element, cfg);
//
//         // content wrapper (circle + optional label)
//         this.wrapEl = document.createElement("div");
//         this.wrapEl.classList.add("tableIndicator");
//
//         this.dotEl = document.createElement("span");
//         this.dotEl.classList.add("tableIndicator__dot");
//
//         this.labelEl = document.createElement("span");
//         this.labelEl.classList.add("tableIndicator__label");
//
//         this.wrapEl.appendChild(this.dotEl);
//         this.wrapEl.appendChild(this.labelEl);
//
//         this.element.appendChild(this.wrapEl);
//         container.appendChild(this.element);
//
//         // initial styling/content
//         this._applyIndicatorStyle(cfg, this.value);
//     }
//
//     update(value) {
//         this.value = value;
//         if (!this.element || !this.wrapEl) return;
//
//         const cfg = this._getMergedStyleConfig();
//         this._applyTdStyle(this.element, cfg);
//         this._applyIndicatorStyle(cfg, value);
//     }
// }
//
// /* ================================================================================================================== */
//
// const COLUMN_MAPPING = {
//     'text': TextColumn,
//     'number': NumberColumn,
//     'slider': SliderColumn,
//     'indicator': IndicatorColumn,
//     'select': SelectColumn,
//     'multi-select': MultiSelectColumn,
//     'button': ButtonColumn,
// };
//
// const CELL_MAPPING = {
//     'text': TextCell,
//     'number': NumberCell,
//     'slider': SliderCell,
//     'indicator': IndicatorCell,
//     'select': SelectCell,
//     'multi-select': MultiSelectCell,
//     'button': ButtonCell,
// }
//
// /* ================================================================================================================== */
// export class TableRow {
//
//     /** @type {Table} */
//     table = undefined;
//     /** @type {string} */
//     id = undefined;
//     /** @type {Array<TableCell>} */
//     cells = [];
//     /** @type {object} */
//     parent = undefined;
//
//     constructor(id, config = {}) {
//         this.id = id;
//         this.configuration = config;
//     }
//
//     clear_cells() {
//         this.cells = [];
//     }
//
//     add_cell(cell) {
//         this.cells.push(cell);
//         cell.table = this.table;
//         return cell;
//     }
//
//     draw_row(container, columns) {
//         this.row_element = document.createElement('tr');
//
//         for (const [column_id, column] of Object.entries(columns)) {
//
//             // Check if there is a cell with the column id in this row
//             const cell = this.cells.find(cell => cell.column === column_id);
//             if (cell) {
//                 cell.draw_cell(this.row_element);
//             } else {
//                 // Make a placeholder cell
//                 console.log('Placeholder cell for column ' + column_id + ' in row ' + this.id + '')
//                 const placeholder = new TableCell(column_id, this.id, column_id, {});
//                 placeholder.draw_cell(this.row_element);
//             }
//
//         }
//         container.appendChild(this.row_element);
//     }
//
//     static from_config(id, config) {
//
//         const row = new TableRow(id, config);
//         const cells = config.cells;
//         for (const [column_id, cell_config] of Object.entries(cells)) {
//             const cell_type = CELL_MAPPING[cell_config.column_type];
//             const cell = new cell_type(cell_config.id,
//                 cell_config.row,
//                 cell_config.column,
//                 cell_config.value,
//                 cell_config.overwrites)
//             row.add_cell(cell);
//
//             // console.log(`Adding Cell of type ${cell_type} to row ${id}`)
//
//         }
//         return row;
//     }
// }
//
// /* ================================================================================================================== */
// export class TableGroup {
//     /** @type {object} */
//     parent = undefined;
//     /** @type {Array} */
//     items = [];
//
//     constructor(id, config = {}) {
//         this.id = id;
//         this.configuration = config;
//     }
// }
//
//
// export class Table extends Widget {
//     /** @type {object} */
//     columns = undefined;
//     /** @type {Array} */
//     items = {};
//
//     header_row = null;
//
//     constructor(id, payload = {}) {
//         super(id, payload);
//
//         this.element = this.initializeElement();
//         this.configureElement(this.element);
//         this.assignListeners(this.element);
//
//
//         this.columns = {};
//
//         this.table_element = null;
//         this.table_head = null;
//         this.table_body = null;
//
//         this._colEls = null;
//         this._colgroup = null;
//
//
//         this.draw(this.table_container);
//         // Build the table from the config
//         const columns = payload.table.columns ? payload.table.columns : {};
//         const rows = payload.table.items ? payload.table.items : {};
//
//         console.log(payload)
//         for (const [column_id, column_config] of Object.entries(columns)) {
//             const column_type = COLUMN_MAPPING[column_config.type];
//             const column = new column_type(column_id, column_config);
//             this.add_column(column);
//         }
//
//         for (const [row_id, row_config] of Object.entries(rows)) {
//             const row = TableRow.from_config(row_config.id, row_config);
//             this.add_row(row);
//         }
//     }
//
//     initializeElement() {
//         const element = document.createElement('div');
//         element.id = this.id;
//         element.classList.add('widget', 'tableWidget');
//
//         // Build the widget header
//         this.title_container = document.createElement('div');
//         element.appendChild(this.title_container);
//
//         // Build the widget content
//         this.table_container = document.createElement('div');
//         element.appendChild(this.table_container);
//
//         return element;
//     }
//
//     configureElement(element) {
//         super.configureElement(element);
//     }
//
//     add_column(column) {
//         if (column.id in this.columns) {
//             console.error(`Column with id ${column.id} already exists.`);
//             return;
//         }
//         this.columns[column.id] = column;
//         column.table = this;
//
//         this._draw_header();
//         this._sync_colgroup(); // <-- important
//     }
//
//     add_row_from_config({id, config}) {
//         const row = TableRow.from_config(id, config);
//         this.add_row(row);
//     }
//
//     delete_row(id) {
//         console.log(`Deleting row ${id}`);
//         const row = this.items[id];
//         if (!row) return;
//
//         row.clear_cells();
//         this.items[id] = undefined;
//         this.table_body.removeChild(row.row_element);
//     }
//
//     add_row(row) {
//         if (!(row instanceof TableRow)) {
//             console.error(`Row must be of type TableRow.`);
//             return;
//         }
//         if (!Array.isArray(row.cells)) {
//             console.error(`Row ${row.id} has no cells array.`);
//             return;
//         }
//
//         // Check if row is already in the table
//         if (row.id in this.items) {
//             console.error(`Row with id ${row.id} already exists.`);
//             return;
//         }
//
//         this.items[row.id] = row;
//         row.table = this;
//         row.cells.forEach(cell => cell.table = this);
//
//         row.draw_row(this.table_body, this.columns);
//     }
//
//     draw() {
//
//
//         this.table_element = document.createElement("table");
//         this.table_element.style.width = "100%";
//         this.table_element.style.borderCollapse = "collapse";
//
//         // If you want "auto" columns to size to content, use table-layout:auto.
//         // But your CSS sets fixed; we keep relying on fixed + explicit widths.
//         // If you ever want to switch dynamically, do:
//         // this.table_element.style.tableLayout = this.configuration.table_layout ?? "fixed";
//
//         this.table_container.classList.add("table-container");
//         this.table_element.classList.add("table");
//         this.table_container.appendChild(this.table_element);
//
//         // --- NEW: colgroup inserted before thead/tbody ---
//         this._colgroup = document.createElement("colgroup");
//         this.table_element.appendChild(this._colgroup);
//
//         this.table_head = document.createElement("thead");
//         this.table_element.appendChild(this.table_head);
//
//         this.table_body = document.createElement("tbody");
//         this.table_element.appendChild(this.table_body);
//
//         this._sync_colgroup(); // in case columns existed before draw
//     }
//
//     _sync_colgroup() {
//         if (!this._colgroup) return;
//
//         // rebuild every time (simple + robust)
//         this._colgroup.innerHTML = "";
//         this._colEls = [];
//
//         for (const [column_id, column] of Object.entries(this.columns)) {
//             const colEl = document.createElement("col");
//
//             const cssW = (typeof column.get_css_width === "function")
//                 ? column.get_css_width()
//                 : "auto";
//
//             // Important behavior with table-layout: fixed:
//             // - width set => respected
//             // - auto/empty => shares remaining space
//             if (cssW !== "auto") {
//                 colEl.style.width = cssW;
//             } else {
//                 // leaving width unset behaves like auto for fixed layout
//                 colEl.style.width = "";
//             }
//
//             this._colgroup.appendChild(colEl);
//             this._colEls.push(colEl);
//         }
//     }
//
//     _draw_header() {
//         if (this.header_row === null) {
//             this.header_row = document.createElement("tr");
//         } else {
//             this.table_head.removeChild(this.header_row);
//             this.header_row = document.createElement("tr");
//         }
//
//         for (const [column_id, column] of Object.entries(this.columns)) {
//             column.draw_header_cell(this.header_row);
//         }
//
//         this.table_head.appendChild(this.header_row);
//
//         // whenever header changes, keep colgroup in sync too
//         this._sync_colgroup();
//     }
//
//
//     get_cell_by_row_and_column(row_id, column_id) {
//         const row = this.items[row_id];
//         if (!row) return null;
//         return row.cells.find(cell => cell.column === column_id);
//     }
//
//
//     update_cell({row, column, value, config}) {
//         const cell = this.get_cell_by_row_and_column(row, column);
//         if (cell) {
//             cell.update(value);
//         } else {
//             console.warn(`Cell ${row}.${column} not found.`);
//         }
//     }
//
//     onMessage(message) {
//         super.onMessage(message);
//
//         switch (message.type) {
//             case 'cell_update': {
//                 console.log(message)
//                 // this.update_cell(message.data.row, message.data.column, message.data.value);
//                 break;
//             }
//             case 'cell_config_update': {
//                 this.update_cell_config(message.data.row, message.data.column, message.data.config);
//                 break;
//             }
//             case 'add_row': {
//                 break;
//             }
//             case 'remove_row': {
//                 break;
//             }
//             case 'add_column': {
//                 break;
//             }
//             case 'remove_column': {
//                 break;
//             }
//         }
//     }
//
//     resize() {
//     }
//
//     update(data) {
//         return undefined;
//     }
//
//     updateConfig(data) {
//         return undefined;
//     }
// }
//
// //
// // /* ================================================================================================================== */
// // export class TableWidget extends Widget {
// //
// //     /** @type {Table} */
// //     table = undefined;
// //
// //     constructor(id, payload = {}) {
// //         super(id, payload);
// //
// //         this.element = this.initializeElement();
// //         this.configureElement(this.element);
// //         this.assignListeners(this.element);
// //
// //         // console.log(payload)
// //         this.table = new Table(this.table_container, payload.table);
// //
// //         // this.table.add_column(new TextColumn('col1', {'title': 'Column 1'}));
// //         // this.table.add_column(new NumberColumn('col2', {'title': 'Number', increment: 0.01, width: 0.1}));
// //         // this.table.add_column(new TextInputColumn('col3', {'title': 'Column 3'}));
// //         // this.table.add_column(new ButtonColumn('col4', {'title': 'Button', width: '80px'}));
// //         // this.table.add_column(new CheckboxColumn('col5', {'title': 'Check', width: 0.07}));
// //         // this.table.add_column(new SliderColumn('col6', {
// //         //     'title': 'Column 6',
// //         //     min_value: 0,
// //         //     max_value: 100,
// //         //     increment: 10,
// //         //     text_align: "center",
// //         //     font_size: 12,
// //         //     font_family: 'monospace'
// //         // }));
// //         //
// //         // this.table.add_column(new IndicatorColumn('col7', {'title': 'Column 7'}));
// //         //
// //         //
// //         // this.table.add_column(new SelectColumn('col8', {
// //         //     'title': 'Column 8',
// //         //     options: {
// //         //         option1: 'Option 1',
// //         //         option2: 'Option 2',
// //         //         option3: 'Option 3'
// //         //     }
// //         // }));
// //         //
// //         //
// //         // this.table.add_column(new MultiSelectColumn('col9', {
// //         //     'title': 'Column 9',
// //         //     options: {
// //         //         option1: 'Option 1',
// //         //         option2: 'Option 2',
// //         //         option3: 'Option 3'
// //         //     }
// //         // }));
// //         //
// //         // // Add 20 rows
// //         // for (let i = 0; i < 20; i++) {
// //         //     const row = new TableRow(`row${i}`);
// //         //     row.add_cell(new TextCell(`cell1`, `row${i}`,
// //         //         `col1`,
// //         //         `Cell ${i}`,
// //         //         {
// //         //             background_color: [i / 20, i / 20, i / 20, 0.8],
// //         //         }));
// //         //     const nc = row.add_cell(
// //         //         new NumberCell(`cell2`, `row${i}`, `col2`, i)
// //         //     )
// //         //
// //         //     const tic = row.add_cell(new TextInputCell(`cell3`, `row${i}`, 'col3', 'a'));
// //         //
// //         //     const bc = row.add_cell(new ButtonCell(`cell4`, `row${i}`, 'col4', `Button ${i}`));
// //         //
// //         //     const cc = row.add_cell(new CheckboxCell(`cell5`, `row${i}`, 'col5', true));
// //         //
// //         //     const sc = row.add_cell(new SliderCell(`cell6`, `row${i}`, 'col6', 50));
// //         //
// //         //     const ic = row.add_cell(new IndicatorCell(`cell7`, `row${i}`, 'col7', [[0, 0.7, 0, 0.8], "E"]))
// //         //
// //         //     const select_cell = row.add_cell(new SelectCell(`cell8`, `row${i}`, 'col8', 'option1'));
// //         //
// //         //     const multiselect_cell = row.add_cell(new MultiSelectCell(`cell9`, `row${i}`, 'col9', null));
// //         //     this.table.add_row(row);
// //         //
// //         //     setInterval(() => {
// //         //         nc.update(Math.random() - 0.5);
// //         //     }, 100);
// //         //
// //         //     // setTimeout(() => {
// //         //     //     tic.reject();
// //         //     // }, 1000);
// //         //
// //         // }
// //     }
// //
// //     /* -------------------------------------------------------------------------------------------------------------- */
// //     initializeElement() {
// //         const element = document.createElement('div');
// //         element.id = this.id;
// //         element.classList.add('widget', 'tableWidget');
// //
// //         // Build the widget header
// //         this.title_container = document.createElement('div');
// //         element.appendChild(this.title_container);
// //
// //         // Build the widget content
// //         this.table_container = document.createElement('div');
// //         element.appendChild(this.table_container);
// //
// //         return element;
// //     }
// //
// //     /* -------------------------------------------------------------------------------------------------------------- */
// //     resize() {
// //     }
// //
// //     /* -------------------------------------------------------------------------------------------------------------- */
// //     update(data) {
// //         return undefined;
// //     }
// //
// //     /* -------------------------------------------------------------------------------------------------------------- */
// //     updateConfig(data) {
// //         return undefined;
// //     }
// //
// //     /* -------------------------------------------------------------------------------------------------------------- */
// //     add_column_from_config(config) {
// //
// //     }
// //
// //     /* -------------------------------------------------------------------------------------------------------------- */
// //     remove_column(column_id) {
// //
// //     }
// //
// //     /* -------------------------------------------------------------------------------------------------------------- */
// //     add_row_from_config(config) {
// //
// //     }
// //
// //     /* -------------------------------------------------------------------------------------------------------------- */
// //     remove_row(row_id) {
// //
// //     }
// //
// //
// //     /* -------------------------------------------------------------------------------------------------------------- */
// //     update_cell(row, column, value) {
// //
// //     }
// //
// //     /* -------------------------------------------------------------------------------------------------------------- */
// //     update_cell_config(row, column, config) {
// //
// //     }
// //
// //     /* -------------------------------------------------------------------------------------------------------------- */
// //     onMessage(message) {
// //         super.onMessage(message);
// //
// //         switch (message.type) {
// //             case 'cell_update': {
// //                 console.log(message)
// //                 // this.update_cell(message.data.row, message.data.column, message.data.value);
// //                 break;
// //             }
// //             case 'cell_config_update': {
// //                 this.update_cell_config(message.data.row, message.data.column, message.data.config);
// //                 break;
// //             }
// //             case 'add_row': {
// //                 break;
// //             }
// //             case 'remove_row': {
// //                 break;
// //             }
// //             case 'add_column': {
// //                 break;
// //             }
// //             case 'remove_column': {
// //                 break;
// //             }
// //         }
// //     }
// //
// //     /* -------------------------------------------------------------------------------------------------------------- */
// //
// //     /* -------------------------------------------------------------------------------------------------------------- */
// // }


import {Widget} from "../objects.js";
import {formatNumberWithIncrement, getColor} from "../../helpers.js";

/* ================================================================================================================== */
export class TableCell {

    /** @type {string} */
    column = undefined;
    /** @type {string} */
    row = undefined;
    /** @type {Table} */
    table = undefined;
    /** @type {string} */
    id = undefined;

    /** @type {object} */
    overrides = {};

    /** @type {typeof TableColumn} */
    static column_type;

    constructor(id, row, column, value, config = {}) {
        this.id = id;
        this.row = row;
        this.column = column;
        this.configuration = config;
        this.value = value;
        this.element = null;
    }

    /** Merge: column defaults/config + parent(TableColumn) config + cell overrides */
    _getMergedStyleConfig() {
        const colObj = this.table?.columns?.[this.column];
        const colCfg = colObj?.configuration ?? {};
        const overrides = this.configuration ?? {};
        return {...colCfg, ...overrides};
    }

    draw_cell(container) {
        this.element = document.createElement('td');
        this.element.textContent = '--';
        this.element.style.border = '0.5px solid #999999';
        this.element.style.textAlign = 'center';
        this.element.style.padding = '1px';
        container.appendChild(this.element);
    }

    update(value) {
        this.value = value;
        this.element.textContent = value;
    }

    destroy() {

    }
}


export class TableColumn {
    constructor(id, config = {}) {

        const defaults = {
            width: "auto", // "auto" | "100px" | 0.3 (30%) | "30%"
            title: "",
            title_color: [1, 1, 1, 0.8],
            title_font_size: 11,
            title_font_family: "sans-serif",
            title_font_align: "center",
            background_color: [0, 0, 0, 0],
            enabled: true,
        };

        this.id = id;
        this.configuration = {...defaults, ...config};
        this.table = null;
    }

    /**
     * Convert width config into a CSS width string usable on <col>/<th>.
     * Supports:
     *  - "auto"
     *  - "100px" (or any CSS length)
     *  - 0.5 => "50%"
     *  - "50%"
     */
    get_css_width() {
        const w = this.configuration?.width;

        if (w === undefined || w === null) return "auto";

        if (typeof w === "number") {
            if (!Number.isFinite(w)) return "auto";
            if (w <= 0) return "0px";
            if (w > 0 && w <= 1) return `${w * 100}%`;
            return `${w}px`;
        }

        if (typeof w === "string") {
            const s = w.trim().toLowerCase();
            if (!s || s === "auto") return "auto";
            if (s.endsWith("%")) return s;
            return w.trim();
        }

        return "auto";
    }

    draw_header_cell(parent) {
        const cell = document.createElement("th");

        cell.textContent = this.configuration.title;
        cell.style.fontSize = `${this.configuration.title_font_size}pt`;
        cell.style.fontFamily = this.configuration.title_font_family;
        cell.style.textAlign = this.configuration.title_font_align;
        cell.style.color = getColor(this.configuration.title_color);
        cell.style.backgroundColor = getColor(this.configuration.background_color);
        cell.style.fontWeight = "bold";
        cell.style.border = "1px solid #aaaaaa";

        const cssW = this.get_css_width();
        if (cssW !== "auto") cell.style.width = cssW;

        parent.appendChild(cell);
    }
}

/* ------------------------------------------------------------------------------------------------------------------ */
export class TextColumn extends TableColumn {
    constructor(id, config = {}) {
        super(id, config);

        this.defaults = {
            text_color: [1, 1, 1, 0.8],
            font_size: 10,  // pt
            font_family: 'sans-serif',
            font_align: 'left',  // left, center, right
        }

        this.configuration = {...this.defaults, ...this.configuration};
    }
}

export class TextCell extends TableCell {
    static column_type = TextColumn;

    constructor(id, row, column, value, config = {}) {
        super(id, row, column, value, config);
    }

    draw_cell(container) {
        this.element = document.createElement("td");

        const cfg = this._getMergedStyleConfig();

        const text = this.value;
        this.element.textContent = (text !== undefined && text !== null) ? String(text) : "";

        this.element.style.border = "0.5px solid #999999";
        this.element.style.padding = "1px";
        this.element.style.verticalAlign = "middle";

        this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
        this.element.style.color = getColor(cfg.text_color ?? [1, 1, 1, 0.8]);
        this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
        this.element.style.fontFamily = cfg.font_family ?? "sans-serif";
        this.element.style.textAlign = cfg.font_align ?? "left";

        if (cfg.font_weight !== undefined) this.element.style.fontWeight = String(cfg.font_weight);
        if (cfg.padding !== undefined) this.element.style.padding = String(cfg.padding);
        if (cfg.border !== undefined) this.element.style.border = String(cfg.border);
        if (cfg.white_space !== undefined) this.element.style.whiteSpace = String(cfg.white_space);
        if (cfg.overflow !== undefined) this.element.style.overflow = String(cfg.overflow);
        if (cfg.text_overflow !== undefined) this.element.style.textOverflow = String(cfg.text_overflow);

        container.appendChild(this.element);
    }

    update(value) {
        this.value = value;
        if (!this.element) return;

        const cfg = this._getMergedStyleConfig();

        this.element.textContent = (value !== undefined && value !== null) ? String(value) : "";

        this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
        this.element.style.color = getColor(cfg.text_color ?? [1, 1, 1, 0.8]);
        this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
        this.element.style.fontFamily = cfg.font_family ?? "sans-serif";
        this.element.style.textAlign = cfg.font_align ?? "left";

        if (cfg.font_weight !== undefined) this.element.style.fontWeight = String(cfg.font_weight);
        if (cfg.padding !== undefined) this.element.style.padding = String(cfg.padding);
        if (cfg.border !== undefined) this.element.style.border = String(cfg.border);
        if (cfg.white_space !== undefined) this.element.style.whiteSpace = String(cfg.white_space);
        if (cfg.overflow !== undefined) this.element.style.overflow = String(cfg.overflow);
        if (cfg.text_overflow !== undefined) this.element.style.textOverflow = String(cfg.text_overflow);
    }
}

/* ------------------------------------------------------------------------------------------------------------------ */
export class TextInputColumn extends TableColumn {
    constructor(id, config = {}) {
        super(id, config);

        this.defaults = {
            input_color: [1, 1, 1, 0.8],
            text_color: [1, 1, 1, 0.8],
            font_size: 10,
            font_family: 'sans-serif',
            font_align: 'left',
            interactive: true,
        }
        this.configuration = {...this.defaults, ...this.configuration};
    }
}


/* ------------------------------------------------------------------------------------------------------------------ */
export class TextInputCell extends TableCell {
    static column_type = TextInputColumn;

    constructor(id, row, column, value, config = {}) {
        super(id, row, column, value, config);

        /** @type {HTMLInputElement|null} */
        this.input = null;

        this._committedValue = (value !== undefined && value !== null) ? String(value) : "";
        this._lastSentValue = null;
    }

    _commit() {
        if (!this.input) return;

        const next = this.input.value;
        console.log(`Committing ${next} from UI`);

        if (next === this._committedValue) {
            this.input.value = this._committedValue;
            this.input.blur();
            return;
        }

        if (this._lastSentValue === next) {
            this.input.blur();
            return;
        }

        this._lastSentValue = next;

        const payload = {
            row_id: this.row,
            column_id: this.column,
            value: next,
            cell_id: this.id,
        };

        if (this.table) {
            this.table.callbacks.get('event').call({
                id: this.table.id,
                event: 'cell_edit',
                data: payload,
            });
        }

        this.input.blur();
    }

    accept(value) {
        const v = (value !== undefined && value !== null) ? String(value) : "";
        this._lastSentValue = null;

        if (!this.input) return;

        this.update(v);

        this.input.classList.remove("error");
        this.input.classList.add("accepted");
        this.input.addEventListener(
            "animationend",
            () => this.input && this.input.classList.remove("accepted"),
            {once: true}
        );
    }

    reject() {
        this._lastSentValue = null;

        if (!this.input) return;

        this.input.value = this._committedValue;

        this.input.classList.remove("accepted");
        this.input.classList.add("error");
        this.input.addEventListener(
            "animationend",
            () => this.input && this.input.classList.remove("error"),
            {once: true}
        );
    }

    draw_cell(container) {
        this.element = document.createElement("td");
        this.element.classList.add("table-cell-input");

        const cfg = this._getMergedStyleConfig();

        this.element.style.border = "0.5px solid #999999";
        this.element.style.padding = "1px";
        this.element.style.verticalAlign = "middle";

        this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
        this.element.style.color = getColor(cfg.text_color ?? [0, 0, 0, 1]);
        this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
        this.element.style.fontFamily = cfg.font_family ?? "sans-serif";
        this.element.style.textAlign = cfg.font_align ?? "left";

        if (cfg.font_weight !== undefined) this.element.style.fontWeight = String(cfg.font_weight);
        if (cfg.border !== undefined) this.element.style.border = String(cfg.border);
        if (cfg.padding !== undefined) this.element.style.padding = String(cfg.padding);
        if (cfg.white_space !== undefined) this.element.style.whiteSpace = String(cfg.white_space);
        if (cfg.overflow !== undefined) this.element.style.overflow = String(cfg.overflow);
        if (cfg.text_overflow !== undefined) this.element.style.textOverflow = String(cfg.text_overflow);

        this.input = document.createElement("input");
        this.input.type = "text";
        this.input.classList.add("tableInput");
        this.input.value = this._committedValue;

        if (cfg.input_color) this.input.style.borderColor = getColor(cfg.input_color);
        else this.input.style.borderColor = "";

        this.input.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                this._commit();
            } else if (e.key === "Escape") {
                e.preventDefault();
                this.input.value = this._committedValue;
                this.input.blur();
            }
        });

        this.input.addEventListener("blur", () => {
            if (!this.input) return;
            this.input.value = this._committedValue;
        });

        this.element.appendChild(this.input);
        container.appendChild(this.element);
    }

    update(value) {
        this.value = value;

        if (!this.element || !this.input) return;

        this.input.value = value;
        this._committedValue = value;
    }
}


/* ------------------------------------------------------------------------------------------------------------------ */
export class NumberColumn extends TableColumn {
    constructor(id, config = {}) {
        super(id, config);

        this.defaults = {
            increment: 0.1,
            align: 'right',  // left, center, right,
            font_size: 10,
        }
        this.configuration = {...this.defaults, ...this.configuration};

    }
}

/* ------------------------------------------------------------------------------------------------------------------ */
export class NumberCell extends TableCell {
    static column_type = NumberColumn;

    constructor(id, row, column, value, config = {}) {
        super(id, row, column, value, config);
        this._lastFormatted = "";
    }

    draw_cell(container) {
        this.element = document.createElement("td");

        const cfg = this._getMergedStyleConfig();
        this.element.style.border = "0.5px solid #999999";
        this.element.style.padding = "1px";
        this.element.style.verticalAlign = "middle";

        this.element.style.textAlign = cfg.align ?? "right";
        this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;

        this.element.style.fontFamily =
            cfg.font_family ?? "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace";
        this.element.style.fontVariantNumeric = "tabular-nums";
        this.element.style.fontFeatureSettings = '"tnum" 1';

        this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
        if (cfg.text_color) this.element.style.color = getColor(cfg.text_color);

        const initial = this.value;
        const formatted = formatNumberWithIncrement(initial, cfg.increment)
        this._lastFormatted = formatted;
        this.element.textContent = formatted;

        if (cfg.font_weight !== undefined) this.element.style.fontWeight = String(cfg.font_weight);
        if (cfg.padding !== undefined) this.element.style.padding = String(cfg.padding);
        if (cfg.border !== undefined) this.element.style.border = String(cfg.border);

        container.appendChild(this.element);
    }

    update(value) {
        this.value = value;
        if (!this.element) return;

        const cfg = this._getMergedStyleConfig();

        this.element.style.textAlign = cfg.align ?? "right";
        this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
        this.element.style.fontFamily =
            cfg.font_family ?? "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace";
        this.element.style.fontVariantNumeric = "tabular-nums";
        this.element.style.fontFeatureSettings = '"tnum" 1';
        this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
        if (cfg.text_color) this.element.style.color = getColor(cfg.text_color);
        if (cfg.font_weight !== undefined) this.element.style.fontWeight = String(cfg.font_weight);
        if (cfg.padding !== undefined) this.element.style.padding = String(cfg.padding);
        if (cfg.border !== undefined) this.element.style.border = String(cfg.border);

        const formatted = formatNumberWithIncrement(value, cfg.increment);
        if (formatted !== this._lastFormatted) {
            this._lastFormatted = formatted;
            this.element.textContent = formatted;
        }
    }
}

/* ------------------------------------------------------------------------------------------------------------------ */
export class ButtonColumn extends TableColumn {
    constructor(id, config = {}) {
        super(id, config);

        this.defaults = {
            button_color: [0.4, 0.4, 0.2, 0.8],
            text_color: [1, 1, 1, 1],
            font_size: 10,
            font_family: 'sans-serif',
            font_align: 'center',
            active: true,
        }
        this.configuration = {...this.defaults, ...this.configuration};
    }
}

export class ButtonCell extends TableCell {
    static column_type = ButtonColumn;

    constructor(id, row, column, value, config = {}) {
        super(id, row, column, value, config);
        /** @type {HTMLButtonElement|null} */
        this.button = null;
    }

    draw_cell(container) {
        this.element = document.createElement("td");
        this.element.classList.add("table-cell-button");

        const cfg = this._getMergedStyleConfig();

        this.element.style.border = "0.5px solid #999999";
        this.element.style.padding = "1px";
        this.element.style.verticalAlign = "middle";

        this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
        if (cfg.text_color) this.element.style.color = getColor(cfg.text_color);
        this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
        this.element.style.fontFamily = cfg.font_family ?? "sans-serif";
        this.element.style.textAlign = cfg.font_align ?? "center";

        if (cfg.font_weight !== undefined) this.element.style.fontWeight = String(cfg.font_weight);
        if (cfg.border !== undefined) this.element.style.border = String(cfg.border);
        if (cfg.padding !== undefined) this.element.style.padding = String(cfg.padding);
        if (cfg.white_space !== undefined) this.element.style.whiteSpace = String(cfg.white_space);
        if (cfg.overflow !== undefined) this.element.style.overflow = String(cfg.overflow);
        if (cfg.text_overflow !== undefined) this.element.style.textOverflow = String(cfg.text_overflow);

        this.button = document.createElement("button");
        this.button.classList.add("tableButton");
        this.button.textContent = (this.value !== undefined && this.value !== null) ? String(this.value) : "";

        this.button.style.backgroundColor = getColor(cfg.button_color ?? [0.2, 0.2, 0.2, 0.8]);
        this.button.style.color = getColor(cfg.text_color ?? [1, 1, 1, 1]);
        this.button.style.fontSize = `${cfg.font_size ?? 12}pt`;
        this.button.style.fontFamily = cfg.font_family ?? "sans-serif";
        this.button.style.textAlign = cfg.font_align ?? "center";

        const active = (cfg.active !== undefined) ? !!cfg.active : true;
        this.button.disabled = !active;
        if (!active) this.button.classList.add("tableButton--disabled");

        this.button.addEventListener("click", () => {
            if (!active) return;
            this.button.classList.add("pressed");
            setTimeout(() => this.button && this.button.classList.remove("pressed"), 120);

            if (this.table) {
                this.table.callbacks.get('event').call({
                    id: this.table.id,
                    event: 'cell_edit',
                    data: {
                        row_id: this.row,
                        column_id: this.column,
                        value: this.value,
                        cell_id: this.id,
                    },
                });
            }
        });

        this.element.appendChild(this.button);
        container.appendChild(this.element);
    }

    update(value) {
        this.value = value;
        if (!this.element || !this.button) return;

        const cfg = this._getMergedStyleConfig();

        this.button.textContent = (value !== undefined && value !== null) ? String(value) : "";

        this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
        this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
        this.element.style.fontFamily = cfg.font_family ?? "sans-serif";
        this.element.style.textAlign = cfg.font_align ?? "center";
        if (cfg.text_color) this.element.style.color = getColor(cfg.text_color);

        this.button.style.backgroundColor = getColor(cfg.button_color ?? [0.2, 0.2, 0.2, 0.8]);
        this.button.style.color = getColor(cfg.text_color ?? [1, 1, 1, 1]);
        this.button.style.fontSize = `${cfg.font_size ?? 12}pt`;
        this.button.style.fontFamily = cfg.font_family ?? "sans-serif";

        const active = (cfg.active !== undefined) ? !!cfg.active : true;
        this.button.disabled = !active;
        this.button.classList.toggle("tableButton--disabled", !active);
    }
}

/* ------------------------------------------------------------------------------------------------------------------ */
export class CheckboxColumn extends TableColumn {
    constructor(id, config = {}) {
        super(id, config);
        this.defaults = {
            checkbox_color: [1, 1, 1, 0.7],
            checkmark_color: [0, 0, 0, 1],
            checkmark_type: 'cross',
            checkbox_alignment: 'center',
            active: true,
        }
        this.configuration = {...this.defaults, ...this.configuration};
    }
}

export class CheckboxCell extends TableCell {
    static column_type = CheckboxColumn;

    constructor(id, row, column, value, config = {}) {
        super(id, row, column, value, config);

        /** @type {HTMLInputElement|null} */
        this.input = null;
        /** @type {HTMLSpanElement|null} */
        this.box = null;
        /** @type {HTMLLabelElement|null} */
        this.label = null;

        this._checked = this._toBool(value);
        this._suppressChange = false;
    }

    _toBool(v) {
        if (v === true) return true;
        if (v === false) return false;
        if (v === 1) return true;
        if (v === 0) return false;

        if (typeof v === "string") {
            const s = v.trim().toLowerCase();
            if (["1", "true", "yes", "y", "on", "checked"].includes(s)) return true;
            if (["0", "false", "no", "n", "off", "unchecked", ""].includes(s)) return false;
        }
        return !!v;
    }

    _applyTdStyle(td, cfg) {
        td.style.border = "0.5px solid #999999";
        td.style.padding = "1px";
        td.style.verticalAlign = "middle";
        td.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);

        const align = cfg.checkbox_alignment ?? "center";
        td.style.textAlign = (align === "left" || align === "right") ? align : "center";

        if (cfg.border !== undefined) td.style.border = String(cfg.border);
        if (cfg.padding !== undefined) td.style.padding = String(cfg.padding);
    }

    _applyBoxStyle(box, cfg) {
        const boxColor = getColor(cfg.checkbox_color ?? [1, 1, 1, 0.7]);
        const markColor = getColor(cfg.checkmark_color ?? [0, 0, 0, 1]);
        const markType = (cfg.checkmark_type ?? "check").toString().trim().toLowerCase();

        box.style.setProperty("--checkbox-color", boxColor);
        box.style.setProperty("--checkmark-color", markColor);
        box.dataset.mark = markType;
    }

    _setVisualState(checked, active) {
        if (!this.label) return;
        this.label.classList.toggle("is-checked", !!checked);
        this.label.classList.toggle("is-disabled", !active);
    }

    on_change(checked) {
        console.log(`CheckboxCell (${this.row}, ${this.column}) => ${checked}`);
        this.update(checked);
    }

    draw_cell(container) {
        this.element = document.createElement("td");
        this.element.classList.add("table-cell-checkbox");

        const cfg = this._getMergedStyleConfig();
        this._applyTdStyle(this.element, cfg);

        this.label = document.createElement("label");
        this.label.classList.add("tableCheckbox");

        this.input = document.createElement("input");
        this.input.type = "checkbox";
        this.input.checked = this._checked;

        const active = (cfg.active !== undefined) ? !!cfg.active : true;
        this.input.disabled = !active;

        this.box = document.createElement("span");
        this.box.classList.add("tableCheckbox__box");
        this._applyBoxStyle(this.box, cfg);

        this._setVisualState(this._checked, active);

        this.input.addEventListener("change", () => {
            if (this._suppressChange) return;

            const next = !!this.input.checked;
            if (next === this._checked) return;

            this._checked = next;
            this._setVisualState(next, !this.input.disabled);
            this.on_change(next);
        });

        this.label.appendChild(this.input);
        this.label.appendChild(this.box);
        this.element.appendChild(this.label);
        container.appendChild(this.element);
    }

    update(value) {
        this.value = value;
        if (!this.element || !this.input || !this.box) return;

        const cfg = this._getMergedStyleConfig();
        this._applyTdStyle(this.element, cfg);
        this._applyBoxStyle(this.box, cfg);

        const active = (cfg.active !== undefined) ? !!cfg.active : true;
        this.input.disabled = !active;

        const next = this._toBool(value);

        if (next === this._checked && this.input.checked === next) {
            this._setVisualState(next, active);
            return;
        }

        this._suppressChange = true;
        this.input.checked = next;
        this._suppressChange = false;

        this._checked = next;
        this._setVisualState(next, active);
    }
}


/* ------------------------------------------------------------------------------------------------------------------ */
export class SelectColumn extends TableColumn {
    constructor(id, config = {}) {
        super(id, config);
        this.defaults = {
            select_color: [0.8, 0.8, 0.8, 0.7],
            text_color: [0.8, 0.8, 0.8, 0.7],
            font_size: 12,
            options: {},
            font_family: 'sans-serif',
            font_align: 'center',
            active: true,
        }
        this.configuration = {...this.defaults, ...this.configuration};
    }
}

/* ------------------------------------------------------------------------------------------------------------------ */
// export class SelectCell extends TableCell {
//     static column_type = SelectColumn;
//
//     constructor(id, row, column, value, config = {}) {
//         super(id, row, column, value, config);
//
//         /** @type {HTMLSelectElement|null} */
//         this.select = null;
//
//         this._committedValue = (value !== undefined && value !== null) ? String(value) : "";
//         this._lastSentValue = null;
//         this._editingValue = this._committedValue;
//     }
//
//     on_select(value) {
//         console.log(`Selected value: ${value}`);
//     }
//
//     _commit() {
//         if (!this.select) return;
//
//         const next = this.select.value;
//         console.log(`Committing ${next} from UI`);
//
//         if (next === this._committedValue) {
//             this.select.value = this._committedValue;
//             this.select.blur();
//             return;
//         }
//
//         if (this._lastSentValue === next) {
//             this.select.blur();
//             return;
//         }
//
//         this._lastSentValue = next;
//
//         this.on_select(next);
//         this.accept(next);
//
//         this.select.blur();
//     }
//
//     accept(value) {
//         const v = (value !== undefined && value !== null) ? String(value) : "";
//         this._lastSentValue = null;
//
//         if (!this.select) return;
//
//         this.update(v);
//
//         this.select.classList.remove("error");
//         this.select.classList.add("accepted");
//         this.select.addEventListener(
//             "animationend",
//             () => this.select && this.select.classList.remove("accepted"),
//             {once: true}
//         );
//     }
//
//     reject() {
//         this._lastSentValue = null;
//
//         if (!this.select) return;
//
//         this.select.value = this._committedValue;
//
//         this.select.classList.remove("accepted");
//         this.select.classList.add("error");
//         this.select.addEventListener(
//             "animationend",
//             () => this.select && this.select.classList.remove("error"),
//             {once: true}
//         );
//     }
//
//     _rebuildOptions(cfg) {
//         if (!this.select) return;
//
//         const optionsObj = cfg.options ?? {};
//         this.select.innerHTML = "";
//
//         for (const [id, label] of Object.entries(optionsObj)) {
//             const opt = document.createElement("option");
//             opt.value = String(id);
//             opt.textContent = (label !== undefined && label !== null) ? String(label) : "";
//             this.select.appendChild(opt);
//         }
//
//         this.select.value = this._committedValue;
//     }
//
//     draw_cell(container) {
//         this.element = document.createElement("td");
//         this.element.classList.add("table-cell-select");
//
//         const cfg = this._getMergedStyleConfig();
//
//         this.element.style.border = "0.5px solid #999999";
//         this.element.style.padding = "1px";
//         this.element.style.verticalAlign = "middle";
//
//         this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
//         this.element.style.color = getColor(cfg.text_color ?? [0, 0, 0, 1]);
//         this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
//         this.element.style.fontFamily = cfg.font_family ?? "sans-serif";
//         this.element.style.textAlign = cfg.font_align ?? "center";
//
//         if (cfg.font_weight !== undefined) this.element.style.fontWeight = String(cfg.font_weight);
//         if (cfg.border !== undefined) this.element.style.border = String(cfg.border);
//         if (cfg.padding !== undefined) this.element.style.padding = String(cfg.padding);
//         if (cfg.white_space !== undefined) this.element.style.whiteSpace = String(cfg.white_space);
//         if (cfg.overflow !== undefined) this.element.style.overflow = String(cfg.overflow);
//         if (cfg.text_overflow !== undefined) this.element.style.textOverflow = String(cfg.text_overflow);
//
//         this.select = document.createElement("select");
//         this.select.classList.add("tableSelect");
//
//         if (cfg.select_color) this.select.style.borderColor = getColor(cfg.select_color);
//         else this.select.style.borderColor = "";
//
//         const active = (cfg.active !== undefined) ? !!cfg.active : true;
//         this.select.disabled = !active;
//         if (!active) this.select.classList.add("tableSelect--disabled");
//         else this.select.classList.remove("tableSelect--disabled");
//
//         this._rebuildOptions(cfg);
//         this.select.value = this._committedValue;
//
//         this.select.addEventListener("focus", () => {
//             if (!this.select) return;
//             this._editingValue = this.select.value;
//         });
//
//         this.select.addEventListener("change", () => {
//             this._commit();
//         });
//
//         this.select.addEventListener("keydown", (e) => {
//             if (e.key === "Enter") {
//                 e.preventDefault();
//                 this._commit();
//             } else if (e.key === "Escape") {
//                 e.preventDefault();
//                 if (!this.select) return;
//                 this.select.value = this._committedValue;
//                 this.select.blur();
//             }
//         });
//
//         this.select.addEventListener("blur", () => {
//             if (!this.select) return;
//             this.select.value = this._committedValue;
//         });
//
//         this.element.appendChild(this.select);
//         container.appendChild(this.element);
//     }
//
//     update(value) {
//         this.value = value;
//         if (!this.element || !this.select) return;
//
//         const cfg = this._getMergedStyleConfig();
//
//         this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
//         this.element.style.color = getColor(cfg.text_color ?? [0, 0, 0, 1]);
//         this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
//         this.element.style.fontFamily = cfg.font_family ?? "sans-serif";
//         this.element.style.textAlign = cfg.font_align ?? "center";
//
//         if (cfg.font_weight !== undefined) this.element.style.fontWeight = String(cfg.font_weight);
//         if (cfg.border !== undefined) this.element.style.border = String(cfg.border);
//         if (cfg.padding !== undefined) this.element.style.padding = String(cfg.padding);
//         if (cfg.white_space !== undefined) this.element.style.whiteSpace = String(cfg.white_space);
//         if (cfg.overflow !== undefined) this.element.style.overflow = String(cfg.overflow);
//         if (cfg.text_overflow !== undefined) this.element.style.textOverflow = String(cfg.text_overflow);
//
//         const active = (cfg.active !== undefined) ? !!cfg.active : true;
//         this.select.disabled = !active;
//         this.select.classList.toggle("tableSelect--disabled", !active);
//
//         this._rebuildOptions(cfg);
//
//         const v = (value !== undefined && value !== null) ? String(value) : "";
//         this._committedValue = v;
//         this.select.value = v;
//     }
// }

export class SelectCell extends TableCell {
    static column_type = SelectColumn;

    constructor(id, row, column, value, config = {}) {
        super(id, row, column, value, config);

        /** @type {HTMLDivElement|null} */
        this.root = null;
        /** @type {HTMLButtonElement|null} */
        this.button = null;

        /** @type {HTMLDivElement|null} */
        this.menu = null;

        this._committedValue = (value !== undefined && value !== null) ? String(value) : "";
        this._editingValue = this._committedValue;
        this._open = false;

        this._outsideClickHandler = (e) => {
            if (!this.root || !this.menu) return;
            const t = e.target;
            if (!this.root.contains(t) && !this.menu.contains(t)) {
                this._close();
            }
        };

        this._onReposition = () => {
            if (this._open) this._positionMenu();
        };
    }

    on_select(value) {
        console.log(`Selected value: ${value}`);
    }

    _ensureMenuExists() {
        if (this.menu) return;

        this.menu = document.createElement("div");
        this.menu.classList.add("tableSingleSelect__menu", "tableSingleSelect__menu--portal");
        this.menu.style.position = "fixed";
        this.menu.style.zIndex = "99999";
        this.menu.style.display = "none";
        this.menu.tabIndex = -1;

        document.body.appendChild(this.menu);
    }

    destroy() {
        this._close();

        if (this.menu) {
            this.menu.remove();
            this.menu = null;
        }

        this.root = null;
        this.button = null;
        this.element = null;
    }

    _labelFor(id, optionsObj) {
        const lbl = optionsObj?.[id];
        return (lbl !== undefined && lbl !== null) ? String(lbl) : String(id);
    }

    _summaryText(cfg) {
        const optionsObj = cfg.options ?? {};
        if (!this._editingValue) return cfg.placeholder ?? "Select…";
        return this._labelFor(this._editingValue, optionsObj);
    }

    _renderMenu() {
        if (!this.menu || !this.button) return;

        const cfg = this._getMergedStyleConfig();
        const optionsObj = cfg.options ?? {};
        const active = (cfg.active !== undefined) ? !!cfg.active : true;

        this.button.textContent = this._summaryText(cfg);
        this.button.disabled = !active;
        this.button.classList.toggle("tableSingleSelect__button--disabled", !active);

        this.menu.innerHTML = "";

        const entries = Object.entries(optionsObj);
        for (const [idRaw, label] of entries) {
            const id = String(idRaw);

            const item = document.createElement("div");
            item.classList.add("tableSingleSelect__item");
            item.dataset.selected = (id === this._editingValue) ? "true" : "false";
            item.textContent = (label !== undefined && label !== null) ? String(label) : id;

            item.addEventListener("mousedown", (e) => {
                // prevent outside-click handler from firing first
                e.preventDefault();
            });

            item.addEventListener("click", () => {
                if (!active) return;

                this._editingValue = id;

                // fire hook immediately (like native select)
                this.on_select(id);

                // accept/commit immediately
                this.accept(id);

                this._close();
            });

            this.menu.appendChild(item);
        }
    }

    _positionMenu() {
        if (!this.button || !this.menu) return;

        const rect = this.button.getBoundingClientRect();
        const gap = 4;

        const prevDisplay = this.menu.style.display;
        const prevVis = this.menu.style.visibility;
        this.menu.style.visibility = "hidden";
        this.menu.style.display = "block";

        const minW = Math.max(140, rect.width);
        this.menu.style.minWidth = `${minW}px`;

        const menuRect = this.menu.getBoundingClientRect();
        const vw = window.innerWidth || document.documentElement.clientWidth;
        const vh = window.innerHeight || document.documentElement.clientHeight;

        let left = rect.left;
        let top = rect.bottom + gap;

        if (left + menuRect.width > vw - 8) left = Math.max(8, vw - 8 - menuRect.width);
        if (left < 8) left = 8;

        if (top + menuRect.height > vh - 8) {
            const above = rect.top - gap - menuRect.height;
            if (above >= 8) top = above;
            else top = Math.max(8, vh - 8 - menuRect.height);
        }

        this.menu.style.left = `${left}px`;
        this.menu.style.top = `${top}px`;

        this.menu.style.visibility = prevVis || "";
        this.menu.style.display = this._open ? "block" : (prevDisplay || "none");
    }

    _openMenu() {
        if (this._open) return;

        const cfg = this._getMergedStyleConfig();
        const active = (cfg.active !== undefined) ? !!cfg.active : true;
        if (!active) return;

        this._ensureMenuExists();
        this._open = true;

        this._renderMenu();
        this._positionMenu();
        if (this.menu) this.menu.style.display = "block";

        document.addEventListener("mousedown", this._outsideClickHandler, true);
        window.addEventListener("resize", this._onReposition, true);
        window.addEventListener("scroll", this._onReposition, true);
    }

    _close() {
        if (!this._open) return;
        this._open = false;

        if (this.menu) this.menu.style.display = "none";

        document.removeEventListener("mousedown", this._outsideClickHandler, true);
        window.removeEventListener("resize", this._onReposition, true);
        window.removeEventListener("scroll", this._onReposition, true);
    }

    _toggleMenu() {
        this._open ? this._close() : this._openMenu();
    }

    accept(value) {
        const v = (value !== undefined && value !== null) ? String(value) : "";
        this.update(v);

        if (!this.button) return;
        this.button.classList.remove("error");
        this.button.classList.add("accepted");
        this.button.addEventListener(
            "animationend",
            () => this.button && this.button.classList.remove("accepted"),
            {once: true}
        );
    }

    reject() {
        if (!this.button) return;
        this._editingValue = this._committedValue;

        this.button.classList.remove("accepted");
        this.button.classList.add("error");
        this.button.addEventListener(
            "animationend",
            () => this.button && this.button.classList.remove("error"),
            {once: true}
        );
    }

    draw_cell(container) {
        this.element = document.createElement("td");
        this.element.classList.add("table-cell-select");

        const cfg = this._getMergedStyleConfig();

        // td styling (same style approach you used before)
        this.element.style.border = "0.5px solid #999999";
        this.element.style.padding = "1px";
        this.element.style.verticalAlign = "middle";
        this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
        this.element.style.color = getColor(cfg.text_color ?? [0, 0, 0, 1]);
        this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
        this.element.style.fontFamily = cfg.font_family ?? "sans-serif";
        this.element.style.textAlign = cfg.font_align ?? "center";

        // root
        this.root = document.createElement("div");
        this.root.classList.add("tableSingleSelect");

        // button
        this.button = document.createElement("button");
        this.button.type = "button";
        this.button.classList.add("tableSingleSelect__button");
        if (cfg.select_color) this.button.style.borderColor = getColor(cfg.select_color);

        this.button.textContent = this._summaryText(cfg);

        this.button.addEventListener("click", (e) => {
            e.preventDefault();
            this._toggleMenu();
        });

        this.button.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === "ArrowDown") {
                e.preventDefault();
                this._openMenu();
            } else if (e.key === "Escape") {
                e.preventDefault();
                this._close();
            }
        });

        this.root.appendChild(this.button);
        this.element.appendChild(this.root);
        container.appendChild(this.element);
    }

    update(value) {
        this.value = value;

        if (!this.element || !this.root || !this.button) return;

        const cfg = this._getMergedStyleConfig();

        // re-apply td styling
        this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
        this.element.style.color = getColor(cfg.text_color ?? [0, 0, 0, 1]);
        this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
        this.element.style.fontFamily = cfg.font_family ?? "sans-serif";
        this.element.style.textAlign = cfg.font_align ?? "center";

        // commit value
        const v = (value !== undefined && value !== null) ? String(value) : "";
        this._committedValue = v;
        this._editingValue = v;

        this.button.textContent = this._summaryText(cfg);

        // keep menu updated if open
        if (this._open) {
            this._renderMenu();
            this._positionMenu();
        }
    }
}

/* ------------------------------------------------------------------------------------------------------------------ */
export class MultiSelectColumn extends TableColumn {
    constructor(id, config = {}) {
        super(id, config);
        this.defaults = {
            select_color: [0.8, 0.8, 0.8, 0.7],
            text_color: [0.8, 0.8, 0.8, 0.7],
            font_size: 12,
            options: {},
            font_family: "sans-serif",
            font_align: "left",
            active: true,
            max_labels_inline: 2,
            placeholder: "Select…",
        };
        this.configuration = {...this.defaults, ...this.configuration};
    }
}

export class MultiSelectCell extends TableCell {
    static column_type = MultiSelectColumn;

    constructor(id, row, column, value, config = {}) {
        super(id, row, column, value, config);

        /** @type {HTMLDivElement|null} */
        this.root = null;
        /** @type {HTMLButtonElement|null} */
        this.button = null;
        /** @type {HTMLDivElement|null} */
        this.menu = null;

        this._committed = this._normValue(value);
        this._editing = [...this._committed];
        this._lastSent = null;
        this._open = false;

        this._outsideClickHandler = (e) => {
            if (!this.root || !this.menu) return;
            const t = e.target;
            if (!this.root.contains(t) && !this.menu.contains(t)) {
                this._commit();
            }
        };

        this._onReposition = () => {
            if (this._open) this._positionMenu();
        };
    }

    _normValue(v) {
        if (Array.isArray(v)) return v.map(x => String(x));
        if (v === undefined || v === null) return [];
        if (typeof v === "string") {
            const s = v.trim();
            if (!s) return [];
            return s.split(",").map(x => x.trim()).filter(Boolean).map(String);
        }
        return [String(v)];
    }

    destroy() {
        // close + remove event listeners
        this._close();

        // remove portaled menu from DOM
        if (this.menu) {
            this.menu.remove();
            this.menu = null;
        }

        this.root = null;
        this.button = null;
        this.element = null;
    }

    on_select(values) {
        console.log(`Selected values: ${values}`);
    }

    _ensureMenuExists() {
        if (this.menu) return;

        this.menu = document.createElement("div");
        this.menu.classList.add("tableMultiSelect__menu", "tableMultiSelect__menu--portal");
        this.menu.style.position = "fixed";
        this.menu.style.zIndex = "99999";
        this.menu.style.display = "none";
        this.menu.tabIndex = -1;

        document.body.appendChild(this.menu);
    }

    _labelFor(id, optionsObj) {
        const lbl = optionsObj?.[id];
        return (lbl !== undefined && lbl !== null) ? String(lbl) : String(id);
    }

    _summaryText(cfg) {
        const optionsObj = cfg.options ?? {};
        const ids = this._editing;

        if (!ids.length) return cfg.placeholder ?? "Select…";

        const maxInline = Number(cfg.max_labels_inline ?? 2);
        const labels = ids.map(id => this._labelFor(id, optionsObj));

        if (labels.length <= maxInline) return labels.join(", ");
        return `${labels.length} selected`;
    }

    _renderMenu() {
        if (!this.menu || !this.button) return;

        const cfg = this._getMergedStyleConfig();
        const optionsObj = cfg.options ?? {};
        const active = (cfg.active !== undefined) ? !!cfg.active : true;

        this.button.textContent = this._summaryText(cfg);
        this.button.disabled = !active;
        this.button.classList.toggle("tableMultiSelect__button--disabled", !active);

        this.menu.innerHTML = "";
        const idsInSet = new Set(this._editing);

        for (const [idRaw, label] of Object.entries(optionsObj)) {
            const id = String(idRaw);

            const item = document.createElement("label");
            item.classList.add("tableMultiSelect__item");

            const cb = document.createElement("input");
            cb.type = "checkbox";
            cb.checked = idsInSet.has(id);
            cb.disabled = !active;

            const txt = document.createElement("span");
            txt.classList.add("tableMultiSelect__label");
            txt.textContent = (label !== undefined && label !== null) ? String(label) : id;

            cb.addEventListener("change", () => {
                const set = new Set(this._editing);
                if (cb.checked) set.add(id);
                else set.delete(id);

                const nextArr = Array.from(set);
                this._editing = nextArr;

                this.button.textContent = this._summaryText(cfg);
                this._positionMenu();

                const sig = [...nextArr].sort().join("|");
                if (this._lastSent !== sig) {
                    this._lastSent = sig;
                    this.on_select([...nextArr]);
                    this._committed = [...nextArr];
                }
            });

            item.appendChild(cb);
            item.appendChild(txt);
            this.menu.appendChild(item);
        }
    }

    _positionMenu() {
        if (!this.button || !this.menu) return;

        const rect = this.button.getBoundingClientRect();
        const gap = 4;

        const prevDisplay = this.menu.style.display;
        const prevVis = this.menu.style.visibility;
        this.menu.style.visibility = "hidden";
        this.menu.style.display = "block";

        const minW = Math.max(140, rect.width);
        this.menu.style.minWidth = `${minW}px`;

        const menuRect = this.menu.getBoundingClientRect();
        const vw = window.innerWidth || document.documentElement.clientWidth;
        const vh = window.innerHeight || document.documentElement.clientHeight;

        let left = rect.left;
        let top = rect.bottom + gap;

        if (left + menuRect.width > vw - 8) left = Math.max(8, vw - 8 - menuRect.width);
        if (left < 8) left = 8;

        if (top + menuRect.height > vh - 8) {
            const above = rect.top - gap - menuRect.height;
            if (above >= 8) top = above;
            else top = Math.max(8, vh - 8 - menuRect.height);
        }

        this.menu.style.left = `${left}px`;
        this.menu.style.top = `${top}px`;

        this.menu.style.visibility = prevVis || "";
        this.menu.style.display = this._open ? "block" : (prevDisplay || "none");
    }

    _openMenu() {
        if (!this.root || !this.button) return;
        if (this._open) return;

        this._ensureMenuExists();
        this._open = true;

        this.root.classList.add("is-open");

        this._renderMenu();
        this._positionMenu();
        if (this.menu) this.menu.style.display = "block";

        document.addEventListener("mousedown", this._outsideClickHandler, true);
        window.addEventListener("resize", this._onReposition, true);
        window.addEventListener("scroll", this._onReposition, true);
    }

    _close() {
        if (!this.root) return;
        if (!this._open) return;

        this._open = false;
        this.root.classList.remove("is-open");

        if (this.menu) this.menu.style.display = "none";

        document.removeEventListener("mousedown", this._outsideClickHandler, true);
        window.removeEventListener("resize", this._onReposition, true);
        window.removeEventListener("scroll", this._onReposition, true);
    }

    _toggleMenu() {
        this._open ? this._close() : this._openMenu();
    }

    _commit() {
        const next = [...this._editing].sort().join("|");
        const committed = [...this._committed].sort().join("|");

        if (next === committed) {
            this._close();
            return;
        }
        if (this._lastSent === next) {
            this._close();
            return;
        }

        this._lastSent = next;

        this.on_select([...this._editing]);
        this.accept([...this._editing]);

        this._close();
    }

    accept(value) {
        const v = this._normValue(value);
        this._lastSent = null;

        this.update(v);

        if (!this.button) return;
        this.button.classList.remove("error");
        this.button.classList.add("accepted");
        this.button.addEventListener(
            "animationend",
            () => this.button && this.button.classList.remove("accepted"),
            {once: true}
        );
    }

    reject() {
        this._lastSent = null;
        this._editing = [...this._committed];

        const cfg = this._getMergedStyleConfig();
        if (this.button) this.button.textContent = this._summaryText(cfg);
        if (this._open) this._renderMenu();

        if (!this.button) return;
        this.button.classList.remove("accepted");
        this.button.classList.add("error");
        this.button.addEventListener(
            "animationend",
            () => this.button && this.button.classList.remove("error"),
            {once: true}
        );
    }

    draw_cell(container) {
        this.element = document.createElement("td");
        this.element.classList.add("table-cell-multiselect");

        const cfg = this._getMergedStyleConfig();

        this.element.style.border = "0.5px solid #999999";
        this.element.style.padding = "1px";
        this.element.style.verticalAlign = "middle";
        this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
        this.element.style.color = getColor(cfg.text_color ?? [0, 0, 0, 1]);
        this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
        this.element.style.fontFamily = cfg.font_family ?? "sans-serif";
        this.element.style.textAlign = cfg.font_align ?? "left";

        this.root = document.createElement("div");
        this.root.classList.add("tableMultiSelect");
        this.root.tabIndex = 0;

        this.button = document.createElement("button");
        this.button.type = "button";
        this.button.classList.add("tableMultiSelect__button");
        if (cfg.select_color) this.button.style.borderColor = getColor(cfg.select_color);

        this.button.addEventListener("click", (e) => {
            e.preventDefault();
            const active = (cfg.active !== undefined) ? !!cfg.active : true;
            if (!active) return;
            this._toggleMenu();
        });

        this.button.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                this._toggleMenu();
            } else if (e.key === "Escape") {
                e.preventDefault();
                this._close();
            } else if (e.key === "ArrowDown") {
                e.preventDefault();
                this._openMenu();
            }
        });

        // this.root.addEventListener("focusout", (e) => {
        //     const next = e.relatedTarget;
        //     if (!this.root) return;
        //
        //     if (this.menu && next && this.menu.contains(next)) return;
        //
        //     const leftRoot = (!next || !this.root.contains(next));
        //     const leftMenu = (!this.menu || !next || !this.menu.contains(next));
        //     if (leftRoot && leftMenu) {
        //         this._commit();
        //     }
        // });

        this.root.appendChild(this.button);
        this.element.appendChild(this.root);
        container.appendChild(this.element);

        this._editing = [...this._committed];
        this.button.textContent = this._summaryText(cfg);
    }

    update(value) {
        this.value = value;

        if (!this.element || !this.root || !this.button) return;

        const cfg = this._getMergedStyleConfig();

        this.element.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
        this.element.style.color = getColor(cfg.text_color ?? [0, 0, 0, 1]);
        this.element.style.fontSize = `${cfg.font_size ?? 12}pt`;
        this.element.style.fontFamily = cfg.font_family ?? "sans-serif";
        this.element.style.textAlign = cfg.font_align ?? "left";

        this._committed = this._normValue(value);
        this._editing = [...this._committed];

        this.button.textContent = this._summaryText(cfg);
        if (this._open) {
            this._renderMenu();
            this._positionMenu();
        }
    }
}

/* ------------------------------------------------------------------------------------------------------------------ */
export class SliderColumn extends TableColumn {
    constructor(id, config = {}) {
        super(id, config);
        this.defaults = {
            slider_color: [0.8, 0.8, 0.8, 0.7],
            text_color: [0.8, 0.8, 0.8, 1],
            background_opacity: 0.12,
            min_value: 0,
            max_value: 100,
            increment: 1,
            text_align: "center",
            font_size: 9,
            font_family: "monospace",
            active: true,
            padding: "1px",
            border: "0.5px solid #999999",
        };
        this.configuration = {...this.defaults, ...this.configuration};
    }
}

export class SliderCell extends TableCell {
    static column_type = SliderColumn;

    constructor(id, row, column, value, config = {}) {
        super(id, row, column, value, config);

        /** @type {HTMLDivElement|null} */
        this.sliderEl = null;
        /** @type {HTMLDivElement|null} */
        this.fillEl = null;
        /** @type {HTMLSpanElement|null} */
        this.valueEl = null;

        this._dragging = false;
        this._lastValue = null;
        this._pointerId = null;

        this._min = 0;
        this._max = 100;
        this._inc = 1;
        this._decimals = 0;
        this._valueType = "int";
    }

    on_value_change(value) {
        console.log(`SliderCell (${this.row}, ${this.column}) => ${value}`);
    }

    _computeNumberMeta(cfg) {
        const inc = parseFloat(cfg.increment ?? 1);
        const decimals = Math.max(0, (inc.toString().split(".")[1] || "").length);
        const valueType = (inc % 1 === 0) ? "int" : "float";
        return {inc, decimals, valueType};
    }

    _clampSnap(v) {
        let x = Number(v);
        if (!Number.isFinite(x)) x = this._min;

        x = Math.max(this._min, Math.min(this._max, x));

        x = Math.round(x / this._inc) * this._inc;
        if (this._valueType === "int") x = Math.round(x);
        else x = parseFloat(x.toFixed(this._decimals));

        x = Math.max(this._min, Math.min(this._max, x));
        return x;
    }

    _pctFromValue(v) {
        const denom = (this._max - this._min);
        if (!denom) return 0;
        return Math.min(1, Math.max(0, (v - this._min) / denom));
    }

    _formatValue(v) {
        return (this._valueType === "int") ? Number(v).toFixed(0) : Number(v).toFixed(this._decimals);
    }

    _applyTdStyle(td, cfg) {
        td.style.border = cfg.border ?? "0.5px solid #999999";
        td.style.padding = cfg.padding ?? "1px";
        td.style.verticalAlign = "middle";
        td.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);
        td.style.color = getColor(cfg.text_color ?? [0.8, 0.8, 0.8, 1]);
        td.style.fontSize = `${cfg.font_size ?? 12}pt`;
        td.style.fontFamily = cfg.font_family ?? "monospace";
        td.style.textAlign = "left";

        if (cfg.font_weight !== undefined) td.style.fontWeight = String(cfg.font_weight);
        if (cfg.white_space !== undefined) td.style.whiteSpace = String(cfg.white_space);
        if (cfg.overflow !== undefined) td.style.overflow = String(cfg.overflow);
        if (cfg.text_overflow !== undefined) td.style.textOverflow = String(cfg.text_overflow);
    }

    _applySliderStyle(cfg) {
        if (!this.sliderEl || !this.fillEl || !this.valueEl) return;

        const bar = getColor(cfg.slider_color ?? [1, 0, 0, 0.7]);

        const sc = (cfg.slider_color ?? [1, 0, 0, 0.7]).slice();
        sc[3] = (cfg.background_opacity !== undefined) ? Number(cfg.background_opacity) : 0.12;
        const bg = getColor(sc);

        this.sliderEl.style.setProperty("--ts-bar", bar);
        this.sliderEl.style.setProperty("--ts-bg", bg);

        const align = (cfg.text_align ?? "center").toString().toLowerCase();
        this.valueEl.dataset.align = (align === "left" || align === "right") ? align : "center";

        const active = (cfg.active !== undefined) ? !!cfg.active : true;
        this.sliderEl.classList.toggle("is-disabled", !active);
        this.sliderEl.style.pointerEvents = active ? "auto" : "none";
        this.sliderEl.style.cursor = active ? "pointer" : "default";
    }

    _setUIValue(v) {
        if (!this.fillEl || !this.valueEl) return;

        const pct = this._pctFromValue(v) * 100;
        this.fillEl.style.width = `${pct}%`;
        this.valueEl.textContent = this._formatValue(v);
    }

    _valueFromPointer(clientX) {
        if (!this.sliderEl) return this._min;

        const rect = this.sliderEl.getBoundingClientRect();
        const track = rect.width || 1;

        const pos = clientX - rect.left;
        const rawPct = Math.max(0, Math.min(1, pos / track));
        const raw = this._min + rawPct * (this._max - this._min);

        return this._clampSnap(raw);
    }

    _bindPointerHandlers() {
        if (!this.sliderEl) return;

        const onMove = (e) => {
            if (!this._dragging) return;
            const v = this._valueFromPointer(e.clientX);
            if (v === this._lastValue) return;

            this._lastValue = v;
            this._setUIValue(v);
        };

        const onUp = () => {
            if (!this._dragging) return;

            this._dragging = false;

            try {
                this.sliderEl.releasePointerCapture(this._pointerId);
            } catch (_) {
            }
            this._pointerId = null;

            const finalValue = (this._lastValue !== null) ? this._lastValue : this._clampSnap(this.value);
            this.value = finalValue;
            this.on_value_change(finalValue);

            this.sliderEl.classList.add("accepted");
            this.sliderEl.addEventListener("animationend", () => {
                this.sliderEl && this.sliderEl.classList.remove("accepted");
            }, {once: true});
        };

        this.sliderEl.addEventListener("pointerdown", (e) => {
            if (e.button !== 0) return;
            e.preventDefault();

            this._dragging = true;
            this._pointerId = e.pointerId;
            this.sliderEl.setPointerCapture(e.pointerId);

            const v = this._valueFromPointer(e.clientX);
            this._lastValue = v;
            this._setUIValue(v);
        });

        this.sliderEl.addEventListener("pointermove", onMove);
        this.sliderEl.addEventListener("pointerup", onUp);
        this.sliderEl.addEventListener("pointercancel", onUp);
        this.sliderEl.addEventListener("lostpointercapture", () => {
            if (!this._dragging) return;
            this._dragging = false;
            this._pointerId = null;
        });
    }

    draw_cell(container) {
        this.element = document.createElement("td");
        this.element.classList.add("table-cell-slider");

        const cfg = this._getMergedStyleConfig();

        this._min = Number(cfg.min_value ?? 0);
        this._max = Number(cfg.max_value ?? 100);
        const meta = this._computeNumberMeta(cfg);
        this._inc = meta.inc;
        this._decimals = meta.decimals;
        this._valueType = meta.valueType;

        this._applyTdStyle(this.element, cfg);

        this.sliderEl = document.createElement("div");
        this.sliderEl.classList.add("tableSlider");
        this.sliderEl.setAttribute("role", "slider");
        this.sliderEl.setAttribute("aria-valuemin", String(this._min));
        this.sliderEl.setAttribute("aria-valuemax", String(this._max));

        const bg = document.createElement("div");
        bg.classList.add("tableSlider__bg");

        this.fillEl = document.createElement("div");
        this.fillEl.classList.add("tableSlider__fill");

        this.valueEl = document.createElement("span");
        this.valueEl.classList.add("tableSlider__value");

        this.sliderEl.appendChild(bg);
        this.sliderEl.appendChild(this.fillEl);
        this.sliderEl.appendChild(this.valueEl);

        this.element.appendChild(this.sliderEl);
        container.appendChild(this.element);

        this._applySliderStyle(cfg);

        const initial = this._clampSnap(this.value ?? this._min);
        this.value = initial;
        this._lastValue = initial;
        this._setUIValue(initial);

        this._bindPointerHandlers();
    }

    update(value) {
        this.value = value;

        if (!this.element || !this.sliderEl) return;

        const cfg = this._getMergedStyleConfig();

        this._applyTdStyle(this.element, cfg);

        this._min = Number(cfg.min_value ?? 0);
        this._max = Number(cfg.max_value ?? 100);
        const meta = this._computeNumberMeta(cfg);
        this._inc = meta.inc;
        this._decimals = meta.decimals;
        this._valueType = meta.valueType;

        this.sliderEl.setAttribute("aria-valuemin", String(this._min));
        this.sliderEl.setAttribute("aria-valuemax", String(this._max));

        this._applySliderStyle(cfg);

        const v = this._clampSnap(value ?? this._min);
        this._lastValue = v;
        this._setUIValue(v);
    }
}


/* ------------------------------------------------------------------------------------------------------------------ */
export class IndicatorColumn extends TableColumn {
    constructor(id, config = {}) {
        super(id, config);

        this.defaults = {
            indicator_color: [1, 1, 1, 0.7],
            text_color: [1, 1, 1, 0.85],
            label: "",
            alignment: "center",
            size_ratio: 0.8,
            gap_px: 6,
            font_size: 12,
            font_family: "sans-serif",
            padding: "1px",
            border: "0.5px solid #999999",
        };

        this.configuration = {...this.defaults, ...this.configuration, ...config};
    }
}

export class IndicatorCell extends TableCell {
    static column_type = IndicatorColumn;

    constructor(id, row, column, value, config = {}) {
        super(id, row, column, value, config);

        /** @type {HTMLDivElement|null} */
        this.wrapEl = null;
        /** @type {HTMLSpanElement|null} */
        this.dotEl = null;
        /** @type {HTMLSpanElement|null} */
        this.labelEl = null;
    }

    _applyTdStyle(td, cfg) {
        td.style.border = cfg.border ?? "0.5px solid #999999";
        td.style.padding = cfg.padding ?? "1px";
        td.style.verticalAlign = "middle";
        td.style.backgroundColor = getColor(cfg.background_color ?? [0, 0, 0, 0]);

        td.style.color = getColor(cfg.text_color ?? [1, 1, 1, 0.85]);
        td.style.fontSize = `${cfg.font_size ?? 12}pt`;
        td.style.fontFamily = cfg.font_family ?? "sans-serif";

        if (cfg.font_weight !== undefined) td.style.fontWeight = String(cfg.font_weight);
        if (cfg.white_space !== undefined) td.style.whiteSpace = String(cfg.white_space);
        if (cfg.overflow !== undefined) td.style.overflow = String(cfg.overflow);
        if (cfg.text_overflow !== undefined) td.style.textOverflow = String(cfg.text_overflow);
    }

    _normValue(value) {
        let color = undefined;
        let label = undefined;

        if (Array.isArray(value)) {
            if (value.length === 4 && value.every(n => typeof n === "number")) {
                color = value;
            } else if (value.length >= 1 && Array.isArray(value[0])) {
                color = value[0];
                if (value.length > 1) label = value[1];
            }
        } else if (value && typeof value === "object") {
            if (Array.isArray(value.color)) color = value.color;
            if (Array.isArray(value.indicator_color)) color = value.indicator_color;
            if (value.label !== undefined) label = value.label;
        } else if (typeof value === "string" || typeof value === "number") {
            label = String(value);
        }

        return {color, label};
    }

    _applyIndicatorStyle(cfg, value) {
        if (!this.wrapEl || !this.dotEl || !this.labelEl) return;

        const {color: vColor, label: vLabel} = this._normValue(value);

        const circleColor = getColor(vColor ?? cfg.indicator_color ?? [1, 1, 1, 0.7]);

        this.dotEl.style.setProperty("--ti-dot", circleColor);

        const gap = Number(cfg.gap_px ?? 6);
        this.wrapEl.style.setProperty("--ti-gap", `${gap}px`);

        const ratio = Math.max(0.1, Math.min(1.0, Number(cfg.size_ratio ?? 0.8)));
        this.wrapEl.style.setProperty("--ti-size", String(ratio));

        const align = (cfg.alignment ?? "center").toString().toLowerCase();
        this.wrapEl.dataset.align = (align === "left" || align === "right") ? align : "center";

        const label = (vLabel !== undefined && vLabel !== null) ? String(vLabel) : (cfg.label ?? "");
        const hasLabel = label.trim().length > 0;

        this.labelEl.textContent = hasLabel ? label : "";
        this.labelEl.style.display = hasLabel ? "" : "none";
        this.wrapEl.classList.toggle("has-label", hasLabel);
    }

    draw_cell(container) {
        this.element = document.createElement("td");
        this.element.classList.add("table-cell-indicator");

        const cfg = this._getMergedStyleConfig();
        this._applyTdStyle(this.element, cfg);

        this.wrapEl = document.createElement("div");
        this.wrapEl.classList.add("tableIndicator");

        this.dotEl = document.createElement("span");
        this.dotEl.classList.add("tableIndicator__dot");

        this.labelEl = document.createElement("span");
        this.labelEl.classList.add("tableIndicator__label");

        this.wrapEl.appendChild(this.dotEl);
        this.wrapEl.appendChild(this.labelEl);

        this.element.appendChild(this.wrapEl);
        container.appendChild(this.element);

        this._applyIndicatorStyle(cfg, this.value);
    }

    update(value) {
        this.value = value;
        if (!this.element || !this.wrapEl) return;
        const cfg = this._getMergedStyleConfig();
        // this._applyTdStyle(this.element, cfg);
        this._applyIndicatorStyle(cfg, value);
    }
}

/* ================================================================================================================== */

const COLUMN_MAPPING = {
    'text': TextColumn,
    'text_input': TextInputColumn,
    'number': NumberColumn,
    'slider': SliderColumn,
    'indicator': IndicatorColumn,
    'select': SelectColumn,
    'multi-select': MultiSelectColumn,
    'button': ButtonColumn,
    'checkbox': CheckboxColumn,
};

const CELL_MAPPING = {
    'text': TextCell,
    'text_input': TextInputCell,
    'number': NumberCell,
    'slider': SliderCell,
    'indicator': IndicatorCell,
    'select': SelectCell,
    'multi-select': MultiSelectCell,
    'button': ButtonCell,
    'checkbox': CheckboxCell,
}

/* ================================================================================================================== */
export class TableRow {

    /** @type {Table} */
    table = undefined;
    /** @type {string} */
    id = undefined;
    /** @type {Array<TableCell>} */
    cells = [];
    /** @type {object} */
    parent = undefined;

    /** @type {boolean} */
    highlight = false;
    /** @type {string|Array|null} */
    row_background_color = null;
    /** @type {string|null} */
    group = null;

    constructor(id, config = {}) {
        this.id = id;
        this.configuration = config;

        this.highlight = !!config.highlight;
        this.row_background_color = (config.row_background_color !== undefined) ? config.row_background_color : null;
        this.group = (config.group !== undefined) ? config.group : null;

        /** @type {HTMLTableRowElement|null} */
        this.row_element = null;
    }

    clear_cells() {
        this.cells = [];
    }

    add_cell(cell) {
        this.cells.push(cell);
        cell.table = this.table;
        return cell;
    }

    /**
     * Force row background onto an individual cell AFTER the cell applied its own styles.
     * (Backend says: if row_background_color != None, ALL cells get it.)
     */
    _applyRowBackgroundToCell(cell) {
        if (!this.row_background_color) return;
        if (!cell?.element) return;
        cell.element.style.backgroundColor = getColor(this.row_background_color);
    }

    _applyRowDecorations() {
        if (!this.row_element) return;
        this.row_element.classList.toggle("tableRow--highlight", !!this.highlight);

        if (this.row_background_color) {
            // ensure already-created cells follow it
            for (const c of this.cells) this._applyRowBackgroundToCell(c);
        }
    }

    draw_row(container, columns) {
        this.row_element = document.createElement('tr');
        this.row_element.dataset.rowId = this.id;
        if (this.group) this.row_element.dataset.groupId = this.group;

        // highlight / background (row-level)
        this._applyRowDecorations();

        for (const [column_id] of Object.entries(columns)) {
            const cell = this.cells.find(cell => cell.column === column_id);
            if (cell) {
                cell.draw_cell(this.row_element);
                this._applyRowBackgroundToCell(cell);
            } else {
                console.log(`Placeholder cell for column ${column_id} in row ${this.id}`);
                const placeholder = new TableCell(column_id, this.id, column_id, {});
                placeholder.table = this.table;
                placeholder.draw_cell(this.row_element);
                this._applyRowBackgroundToCell(placeholder);
            }
        }

        container.appendChild(this.row_element);
    }

    static from_config(id, config) {
        const row = new TableRow(id, config);
        const cells = config.cells ?? {};
        for (const [column_id, cell_config] of Object.entries(cells)) {
            const cell_type = CELL_MAPPING[cell_config.column_type] ?? TableCell;
            const cell = new cell_type(
                cell_config.id,
                cell_config.row,
                cell_config.column,
                cell_config.value,
                cell_config.overwrites
            );
            row.add_cell(cell);
        }
        return row;
    }
}

/* ================================================================================================================== */
export class TableGroup {
    /** @type {Table|null} */
    table = null;

    /** @type {string} */
    id = undefined;

    /** @type {object} */
    configuration = {};

    /** @type {boolean} */
    collapsible = false;

    /** @type {boolean} */
    collapsed = false;

    /** @type {Array<TableRow>} */
    rows = [];

    /** @type {HTMLTableRowElement|null} */
    title_row_element = null;

    /** @type {HTMLTableCellElement|null} */
    title_cell_element = null;

    constructor(id, config = {}) {
        this.id = id;
        this.configuration = config;

        this.collapsible = !!config.collapsible;
        this.collapsed = false; // start expanded by default
    }

    get groupColor() {
        // group_color can be rgba list or css string; backend default is [0,0,0,0]
        return this.configuration?.group_color ?? [0, 0, 0, 0];
    }

    get title() {
        return this.configuration?.title ?? "";
    }

    get titleColor() {
        return this.configuration?.title_color ?? "white";
    }

    _colorIsVisible(color) {
        try {
            if (Array.isArray(color)) return (color[3] ?? 0) > 0;
            if (typeof color === "string") return color.trim().length > 0 && color !== "transparent";
        } catch (_) {
        }
        return false;
    }

    _setGroupRowClasses() {
        // Recompute first/last markers (for outline drawing)
        const visibleRows = this.rows; // even if collapsed, we still mark; CSS will handle hidden rows
        const all = [];

        if (this.title_row_element) all.push(this.title_row_element);
        for (const r of visibleRows) {
            if (r?.row_element) all.push(r.row_element);
        }

        for (const tr of all) {
            tr.classList.remove("tableGroup--first", "tableGroup--last", "tableGroup--in", "tableGroup--title");
        }

        if (this.title_row_element) {
            this.title_row_element.classList.add("tableGroup--in", "tableGroup--title");
        }

        for (const r of visibleRows) {
            if (r?.row_element) r.row_element.classList.add("tableGroup--in");
        }

        const first = this.title_row_element;
        const last = (this.collapsed || visibleRows.length === 0)
            ? this.title_row_element
            : (visibleRows[visibleRows.length - 1]?.row_element ?? this.title_row_element);

        if (first) first.classList.add("tableGroup--first");
        if (last) last.classList.add("tableGroup--last");
    }

    _applyGroupColorToRow(tr) {
        if (!tr) return;
        if (!this._colorIsVisible(this.groupColor)) {
            tr.style.removeProperty("--table-group-color");
            tr.classList.remove("tableGroup--colored");
            return;
        }
        tr.style.setProperty("--table-group-color", getColor(this.groupColor));
        tr.classList.add("tableGroup--colored");
    }

    _applyGroupColorToAll() {
        this._applyGroupColorToRow(this.title_row_element);
        for (const r of this.rows) this._applyGroupColorToRow(r?.row_element);
    }

    _updateTriangle() {
        if (!this.title_row_element) return;
        this.title_row_element.classList.toggle("is-collapsible", !!this.collapsible);
        this.title_row_element.classList.toggle("is-collapsed", !!this.collapsed);
    }

    toggleCollapsed() {
        if (!this.collapsible) return;
        this.collapsed = !this.collapsed;

        for (const r of this.rows) {
            if (!r?.row_element) continue;
            r.row_element.style.display = this.collapsed ? "none" : "";
        }

        this._updateTriangle();
        this._setGroupRowClasses();
        this._applyGroupColorToAll();
    }

    draw_title_row(container, columnCount) {
        this.title_row_element = document.createElement("tr");
        this.title_row_element.dataset.groupId = this.id;
        this.title_row_element.classList.add("tableGroupTitleRow");
        this._updateTriangle();

        const td = document.createElement("td");
        td.colSpan = Math.max(1, Number(columnCount || 1));
        td.classList.add("tableGroupTitleCell");

        // left triangle + title
        const wrap = document.createElement("div");
        wrap.classList.add("tableGroupTitleContent");

        const tri = document.createElement("span");
        tri.classList.add("tableGroupTriangle");
        tri.setAttribute("aria-hidden", "true");

        const title = document.createElement("span");
        title.classList.add("tableGroupTitleText");
        title.textContent = this.title;

        wrap.appendChild(tri);
        wrap.appendChild(title);

        td.appendChild(wrap);

        // styling
        td.style.color = getColor(this.titleColor);

        this.title_cell_element = td;
        this.title_row_element.appendChild(td);
        container.appendChild(this.title_row_element);

        // Collapse/expand on double click
        this.title_row_element.addEventListener("dblclick", (e) => {
            e.preventDefault();
            this.toggleCollapsed();
        });

        // Optional: single-click on triangle area to toggle too
        td.addEventListener("click", (e) => {
            const t = e.target;
            if (!(t instanceof HTMLElement)) return;
            if (t.classList.contains("tableGroupTriangle")) {
                e.preventDefault();
                this.toggleCollapsed();
            }
        });

        this._applyGroupColorToRow(this.title_row_element);
    }

    draw(container, columns) {
        const colCount = Object.keys(columns ?? {}).length || 1;

        // title row is always visible
        this.draw_title_row(container, colCount);

        // rows
        for (const r of this.rows) {
            r.table = this.table;
            r.draw_row(container, columns);

            // apply group id onto row element (and any outline styles)
            if (r.row_element) r.row_element.dataset.groupId = this.id;
            this._applyGroupColorToRow(r.row_element);

            // start expanded
            if (this.collapsed && r.row_element) r.row_element.style.display = "none";
        }

        this._setGroupRowClasses();
        this._applyGroupColorToAll();
    }

    add_row(row, columns, container) {
        this.rows.push(row);
        row.group = this.id;
        row.table = this.table;

        // Insert: after title row + existing rows
        // If we already rendered, add to DOM at the end of group block.
        if (container && this.title_row_element) {
            row.draw_row(container, columns);
            if (row.row_element) row.row_element.dataset.groupId = this.id;
            this._applyGroupColorToRow(row.row_element);
            if (this.collapsed && row.row_element) row.row_element.style.display = "none";
            this._setGroupRowClasses();
            this._applyGroupColorToAll();
        }
    }

    delete_row(rowId) {
        const idx = this.rows.findIndex(r => r?.id === rowId);
        if (idx < 0) return;
        const row = this.rows[idx];
        if (row?.row_element?.parentElement) row.row_element.parentElement.removeChild(row.row_element);
        this.rows.splice(idx, 1);
        this._setGroupRowClasses();
        this._applyGroupColorToAll();

        if (Array.isArray(row.cells)) {
            for (const cell of row.cells) {
                if (cell && typeof cell.destroy === "function") {
                    cell.destroy();
                }
            }
        }

    }

    setTitle(newTitle) {
        this.configuration.title = newTitle;
        if (this.title_cell_element) {
            const textEl = this.title_cell_element.querySelector(".tableGroupTitleText");
            if (textEl) textEl.textContent = newTitle ?? "";
        }
    }
}

/* ================================================================================================================== */

export class Table extends Widget {
    /** @type {object} */
    columns = undefined;

    /**
     * Rows lookup by row id (includes grouped rows).
     * @type {Object.<string, TableRow>}
     */
    rows = {};

    /**
     * Groups lookup by group id.
     * @type {Object.<string, TableGroup>}
     */
    groups = {};

    /**
     * Top-level render order items: (TableRow | TableGroup)
     * @type {Array}
     */
    items = [];

    header_row = null;

    constructor(id, payload = {}) {
        super(id, payload);

        this.element = this.initializeElement();
        this.configureElement(this.element);
        this.assignListeners(this.element);

        this.columns = {};

        this.table_element = null;
        this.table_head = null;
        this.table_body = null;

        this._colEls = null;
        this._colgroup = null;

        this.draw(this.table_container);

        const columns = payload?.table?.columns ? payload.table.columns : {};
        const items = payload?.table?.items ? payload.table.items : [];

        // columns
        for (const [column_id, column_config] of Object.entries(columns)) {
            const column_type = COLUMN_MAPPING[column_config.type] ?? TableColumn;
            const column = new column_type(column_id, column_config);
            this.add_column(column);
        }

        // items is now an ARRAY (rows and groups)
        // group item has "rows" array; row item has "cells" dict
        for (const item of (Array.isArray(items) ? items : [])) {
            if (item && typeof item === "object" && Array.isArray(item.rows)) {
                const group = new TableGroup(item.id, item);
                this.add_group(group);
                // add group rows from config
                for (const rCfg of (item.rows ?? [])) {
                    const row = TableRow.from_config(rCfg.id, rCfg);
                    this.add_row(row, {group_id: group.id});
                }
            } else if (item && typeof item === "object" && item.cells) {
                const row = TableRow.from_config(item.id, item);
                this.add_row(row, {group_id: item.group ?? null});
            }
        }

        // render everything (groups and ungrouped rows) in correct order:
        this._redraw_body();
    }

    initializeElement() {
        const element = document.createElement('div');
        element.id = this.id;
        element.classList.add('widget', 'tableWidget');

        this.title_container = document.createElement('div');
        element.appendChild(this.title_container);

        this.table_container = document.createElement('div');
        element.appendChild(this.table_container);

        return element;
    }

    configureElement(element) {
        super.configureElement(element);
    }

    add_column(column) {
        if (column.id in this.columns) {
            console.error(`Column with id ${column.id} already exists.`);
            return;
        }
        this.columns[column.id] = column;
        column.table = this;

        this._draw_header();
        this._sync_colgroup();
    }

    /* ------------------------------------------ Groups / Rows (new) ------------------------------------------ */

    add_group(group) {
        if (!group || !group.id) return;
        if (group.id in this.groups) return;

        group.table = this;
        this.groups[group.id] = group;

        // keep ordering: if backend sends groups as items they are already added via constructor;
        // for dynamic add you can push them
        this.items.push(group);
    }

    add_group_from_config({id, config}) {
        const g = new TableGroup(id, config);
        this.add_group(g);
        this._redraw_body();
    }

    add_row_from_config({id, config}) {
        const row = TableRow.from_config(id, config);
        this.add_row(row, {group_id: config?.group ?? null});
        this._redraw_body();
    }

    delete_row(id) {
        // row may be grouped or ungrouped
        const row = this.rows[id];
        if (!row) return;

        const groupId = row.group ?? row.configuration?.group ?? null;

        if (groupId && this.groups[groupId]) {
            this.groups[groupId].delete_row(id);
        } else {
            if (row.row_element && row.row_element.parentElement) {
                row.row_element.parentElement.removeChild(row.row_element);
            }
        }

        delete this.rows[id];

        if (Array.isArray(row.cells)) {
            for (const cell of row.cells) {
                if (cell && typeof cell.destroy === "function") {
                    cell.destroy();
                }
            }
        }
        // also remove from top-level items if it was ungrouped
        this.items = this.items.filter(it => !(it instanceof TableRow && it.id === id));
    }

    add_row(row, {group_id = null} = {}) {
        if (!(row instanceof TableRow)) {
            console.error(`Row must be of type TableRow.`);
            return;
        }
        if (!Array.isArray(row.cells)) {
            console.error(`Row ${row.id} has no cells array.`);
            return;
        }
        if (row.id in this.rows) {
            console.error(`Row with id ${row.id} already exists.`);
            return;
        }

        row.table = this;
        row.cells.forEach(cell => cell.table = this);

        // attach group if specified (or in row config)
        const gid = group_id ?? row.group ?? row.configuration?.group ?? null;
        if (gid && this.groups[gid]) {
            row.group = gid;
            this.groups[gid].rows.push(row);
        } else {
            // ungrouped row
            row.group = null;
            this.items.push(row);
        }

        this.rows[row.id] = row;
    }

    /* ---------------------------------------------- Render --------------------------------------------------- */

    draw() {
        this.table_element = document.createElement("table");
        this.table_element.style.width = "100%";
        this.table_element.style.borderCollapse = "collapse";

        this.table_container.classList.add("table-container");
        this.table_element.classList.add("table");
        this.table_container.appendChild(this.table_element);

        this._colgroup = document.createElement("colgroup");
        this.table_element.appendChild(this._colgroup);

        this.table_head = document.createElement("thead");
        this.table_element.appendChild(this.table_head);

        this.table_body = document.createElement("tbody");
        this.table_element.appendChild(this.table_body);

        this._sync_colgroup();
    }

    _redraw_body() {
        if (!this.table_body) return;
        this.table_body.innerHTML = "";

        // Ensure header exists
        this._draw_header();

        // Draw in order: items contain TableGroup and ungrouped TableRow
        for (const it of this.items) {
            if (it instanceof TableGroup) {
                it.draw(this.table_body, this.columns);
            } else if (it instanceof TableRow) {
                it.draw_row(this.table_body, this.columns);
            }
        }
    }

    _sync_colgroup() {
        if (!this._colgroup) return;

        this._colgroup.innerHTML = "";
        this._colEls = [];

        for (const [, column] of Object.entries(this.columns)) {
            const colEl = document.createElement("col");
            const cssW = (typeof column.get_css_width === "function")
                ? column.get_css_width()
                : "auto";

            if (cssW !== "auto") colEl.style.width = cssW;
            else colEl.style.width = "";

            this._colgroup.appendChild(colEl);
            this._colEls.push(colEl);
        }
    }

    _draw_header() {
        if (!this.table_head) return;

        if (this.header_row === null) {
            this.header_row = document.createElement("tr");
        } else {
            if (this.header_row.parentElement === this.table_head) {
                this.table_head.removeChild(this.header_row);
            }
            this.header_row = document.createElement("tr");
        }

        for (const [, column] of Object.entries(this.columns)) {
            column.draw_header_cell(this.header_row);
        }

        this.table_head.appendChild(this.header_row);
        this._sync_colgroup();
    }

    /* ---------------------------------------------- Updates -------------------------------------------------- */

    get_cell_by_row_and_column(row_id, column_id) {
        const row = this.rows[row_id];
        if (!row) return null;
        return row.cells.find(cell => cell.column === column_id) ?? null;
    }

    update_cell({row, column, value, config}) {
        const cell = this.get_cell_by_row_and_column(row, column);
        if (cell) {
            cell.update(value);

            // enforce row-level background after cell update (backend rule)
            const r = this.rows[row];
            if (r) r._applyRowBackgroundToCell(cell);

        } else {
            console.warn(`Cell ${row}.${column} not found.`);
        }
    }

    accept_cell({row_id, column_id, value}) {
        const cell = this.get_cell_by_row_and_column(row_id, column_id);
        if (cell && typeof cell.accept === 'function') {
            cell.accept(value);
        }
    }

    reject_cell({row_id, column_id}) {
        const cell = this.get_cell_by_row_and_column(row_id, column_id);
        if (cell && typeof cell.reject === 'function') {
            cell.reject();
        }
    }

    mark_cell_dirty({row_id, column_id}) {
        const cell = this.get_cell_by_row_and_column(row_id, column_id);
        if (cell && cell.input) {
            cell.input.classList.add("dirty");
        }
    }

    mark_cell_clean({row_id, column_id}) {
        const cell = this.get_cell_by_row_and_column(row_id, column_id);
        if (cell && cell.input) {
            cell.input.classList.remove("dirty");
        }
    }

    onMessage(message) {
        super.onMessage(message);

        switch (message.type) {
            case 'cell_update': {
                break;
            }
            case 'cell_config_update': {
                // if you later add: update_cell_config(message.data.row, message.data.column, message.data.config)
                break;
            }
            case 'add_row': {
                break;
            }
            case 'remove_row': {
                break;
            }
            case 'add_column': {
                break;
            }
            case 'remove_column': {
                break;
            }
        }
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