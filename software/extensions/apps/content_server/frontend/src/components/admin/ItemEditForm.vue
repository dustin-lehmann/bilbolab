<template>
    <div class="ief">
        <!-- General -->
        <div class="ief-card">
            <h3>General</h3>
            <div class="ief-field">
                <label>Type</label>
                <select v-model="form.type" class="ief-input">
                    <option value="video">Video</option>
                    <option value="synchronized">Synchronized Videos</option>
                    <option value="collection">Video Collection</option>
                    <option value="figures">Figure Collection</option>
                    <option value="pdf">PDF</option>
                    <option value="code">Code</option>
                    <option value="interactive">Interactive Example</option>
                    <option value="model3d">3D Model</option>
                </select>
            </div>
            <div class="ief-field">
                <label>Title</label>
                <input v-model="form.title" class="ief-input" placeholder="Item title">
            </div>
            <div class="ief-field">
                <label>Description</label>
                <textarea v-model="form.description" class="ief-input ief-textarea" rows="2" placeholder="Optional description"></textarea>
            </div>
            <div class="ief-row">
                <div class="ief-field">
                    <label>Date</label>
                    <input v-model="form.date" class="ief-input" type="date">
                </div>
            </div>
            <label class="ief-checkbox"><input type="checkbox" v-model="form.draft"> Draft (hidden from public)</label>
        </div>

        <!-- Slot: files area (provided by consumer) -->
        <slot name="files"></slot>

        <!-- Single Video -->
        <div class="ief-card" v-if="form.type === 'video'">
            <h3>Video Settings</h3>
            <div class="ief-field">
                <label>Video File</label>
                <select v-model="form.file" class="ief-input">
                    <option value="" disabled>Select file...</option>
                    <option v-for="f in availableFiles" :key="f" :value="f">{{ f }}</option>
                </select>
            </div>
            <div class="ief-field">
                <label>Markers</label>
                <div class="ief-array-row ief-array-header">
                    <span style="max-width:100px;flex:0 0 100px">Time (s)</span>
                    <span style="flex:1">Description</span>
                    <span style="width:24px"></span>
                </div>
                <div v-for="(m, i) in form.markers" :key="i" class="ief-array-row">
                    <input v-model.number="m.time" class="ief-input ief-input-sm" type="number" step="0.1" placeholder="0" style="max-width:100px">
                    <input v-model="m.label" class="ief-input ief-input-sm" placeholder="Marker label">
                    <button class="ief-btn-rm" @click="form.markers.splice(i, 1)">&times;</button>
                </div>
                <button class="ief-btn-add" @click="form.markers.push({time:0,label:''})">+ Add Marker</button>
            </div>
            <!-- Overlay Style -->
            <div class="ief-field">
                <div class="ief-label-row"><label>Overlay Style</label><button class="ief-btn-reset" @click="resetOverlayStyle(form.overlayStyle)" title="Reset to defaults">Reset</button></div>
                <div class="ief-style-row">
                    <div class="ief-style-field"><span class="ief-style-label">V. Position</span>
                        <select v-model="form.overlayStyle.verticalPosition" class="ief-input ief-input-sm"><option value="bottom">Bottom</option><option value="top">Top</option></select>
                    </div>
                    <div class="ief-style-field"><span class="ief-style-label">H. Position</span>
                        <select v-model="form.overlayStyle.horizontalPosition" class="ief-input ief-input-sm"><option value="center">Center</option><option value="left">Left</option><option value="right">Right</option></select>
                    </div>
                    <div class="ief-style-field"><span class="ief-style-label">Font Size</span>
                        <input v-model.number="form.overlayStyle.fontSize" class="ief-input ief-input-sm" type="number" min="8" max="72" placeholder="16">
                    </div>
                    <div class="ief-style-field"><span class="ief-style-label">Font Color</span>
                        <input v-model="form.overlayStyle.fontColor" class="ief-input ief-input-sm" type="color" style="height:32px;padding:2px">
                    </div>
                    <div class="ief-style-field"><span class="ief-style-label">Background</span>
                        <ColorAlphaPicker v-model="form.overlayStyle.backgroundColor" />
                    </div>
                    <div class="ief-style-field"><span class="ief-style-label">Opacity</span>
                        <input v-model.number="form.overlayStyle.opacity" class="ief-input ief-input-sm" type="number" min="0" max="1" step="0.1" placeholder="1.0">
                    </div>
                </div>
            </div>
            <!-- Overlay Entries -->
            <div class="ief-field">
                <label>Overlay Entries</label>
                <div class="ief-array-row ief-array-header">
                    <span style="max-width:90px;flex:0 0 90px">Time (s)</span>
                    <span style="max-width:100px;flex:0 0 100px">Duration (s)</span>
                    <span style="flex:1">Text</span>
                    <span style="width:24px"></span>
                </div>
                <div v-for="(o, i) in form.overlays" :key="i" class="ief-array-row">
                    <input v-model.number="o.time" class="ief-input ief-input-sm" type="number" step="0.1" placeholder="0" style="max-width:90px">
                    <input v-model.number="o.duration" class="ief-input ief-input-sm" type="number" step="0.1" placeholder="2" style="max-width:100px">
                    <input v-model="o.text" class="ief-input ief-input-sm" placeholder="Overlay text">
                    <button class="ief-btn-rm" @click="form.overlays.splice(i, 1)">&times;</button>
                </div>
                <button class="ief-btn-add" @click="form.overlays.push({time:0,duration:2,text:''})">+ Add Overlay</button>
            </div>
        </div>

        <!-- Synced / Collection Videos -->
        <div class="ief-card" v-if="form.type === 'synchronized' || form.type === 'collection'">
            <h3>Videos</h3>
            <div v-for="(v, i) in form.videos" :key="i" class="ief-video-card">
                <div class="ief-array-row">
                    <input v-model="v.name" class="ief-input ief-input-sm" placeholder="Label">
                    <select v-model="v.file" class="ief-input ief-input-sm">
                        <option value="" disabled>Select file...</option>
                        <option v-for="f in availableFiles" :key="f" :value="f">{{ f }}</option>
                    </select>
                    <button class="ief-btn-rm" @click="form.videos.splice(i, 1)">&times;</button>
                </div>
                <div class="ief-nested">
                    <div class="ief-label-row"><span class="ief-style-label">Overlay Style</span><button class="ief-btn-reset" @click="resetOverlayStyle(v.overlayStyle)" title="Reset to defaults">Reset</button></div>
                    <div class="ief-style-row">
                        <div class="ief-style-field"><span class="ief-style-label">V. Pos</span>
                            <select v-model="v.overlayStyle.verticalPosition" class="ief-input ief-input-sm"><option value="bottom">Bottom</option><option value="top">Top</option></select>
                        </div>
                        <div class="ief-style-field"><span class="ief-style-label">H. Pos</span>
                            <select v-model="v.overlayStyle.horizontalPosition" class="ief-input ief-input-sm"><option value="center">Center</option><option value="left">Left</option><option value="right">Right</option></select>
                        </div>
                        <div class="ief-style-field"><span class="ief-style-label">Size</span>
                            <input v-model.number="v.overlayStyle.fontSize" class="ief-input ief-input-sm" type="number" min="8" max="72" placeholder="16">
                        </div>
                        <div class="ief-style-field"><span class="ief-style-label">Color</span>
                            <input v-model="v.overlayStyle.fontColor" class="ief-input ief-input-sm" type="color" style="height:32px;padding:2px">
                        </div>
                        <div class="ief-style-field"><span class="ief-style-label">BG</span>
                            <ColorAlphaPicker v-model="v.overlayStyle.backgroundColor" />
                        </div>
                        <div class="ief-style-field"><span class="ief-style-label">Opacity</span>
                            <input v-model.number="v.overlayStyle.opacity" class="ief-input ief-input-sm" type="number" min="0" max="1" step="0.1" placeholder="1.0">
                        </div>
                    </div>
                    <div class="ief-array-row ief-array-header">
                        <span style="max-width:80px;flex:0 0 80px">Time (s)</span>
                        <span style="max-width:80px;flex:0 0 80px">Dur (s)</span>
                        <span style="flex:1">Text</span>
                        <span style="width:24px"></span>
                    </div>
                    <div v-for="(o, oi) in v.overlays" :key="oi" class="ief-array-row">
                        <input v-model.number="o.time" class="ief-input ief-input-sm" type="number" step="0.1" placeholder="0" style="max-width:80px">
                        <input v-model.number="o.duration" class="ief-input ief-input-sm" type="number" step="0.1" placeholder="2" style="max-width:80px">
                        <input v-model="o.text" class="ief-input ief-input-sm" placeholder="Overlay text">
                        <button class="ief-btn-rm" @click="v.overlays.splice(oi, 1)">&times;</button>
                    </div>
                    <button class="ief-btn-add" @click="v.overlays.push({time:0,duration:2,text:''})">+ Overlay</button>
                </div>
            </div>
            <button class="ief-btn-add" @click="form.videos.push({name:'',file:'',overlays:[],overlayStyle:{}})">+ Add Video</button>

            <!-- Global Overlays (all videos) -->
            <div v-if="form.type === 'synchronized'" class="ief-field" style="margin-top:12px">
                <div class="ief-label-row"><label>Global Overlay Style</label><button class="ief-btn-reset" @click="resetOverlayStyle(form.overlayStyle)" title="Reset to defaults">Reset</button></div>
                <div class="ief-style-row">
                    <div class="ief-style-field"><span class="ief-style-label">V. Position</span>
                        <select v-model="form.overlayStyle.verticalPosition" class="ief-input ief-input-sm"><option value="bottom">Bottom</option><option value="top">Top</option></select>
                    </div>
                    <div class="ief-style-field"><span class="ief-style-label">H. Position</span>
                        <select v-model="form.overlayStyle.horizontalPosition" class="ief-input ief-input-sm"><option value="center">Center</option><option value="left">Left</option><option value="right">Right</option></select>
                    </div>
                    <div class="ief-style-field"><span class="ief-style-label">Font Size</span>
                        <input v-model.number="form.overlayStyle.fontSize" class="ief-input ief-input-sm" type="number" min="8" max="72" placeholder="16">
                    </div>
                    <div class="ief-style-field"><span class="ief-style-label">Font Color</span>
                        <input v-model="form.overlayStyle.fontColor" class="ief-input ief-input-sm" type="color" style="height:32px;padding:2px">
                    </div>
                    <div class="ief-style-field"><span class="ief-style-label">Background</span>
                        <ColorAlphaPicker v-model="form.overlayStyle.backgroundColor" />
                    </div>
                    <div class="ief-style-field"><span class="ief-style-label">Opacity</span>
                        <input v-model.number="form.overlayStyle.opacity" class="ief-input ief-input-sm" type="number" min="0" max="1" step="0.1" placeholder="1.0">
                    </div>
                </div>
            </div>
            <div v-if="form.type === 'synchronized'" class="ief-field">
                <label>Global Overlay Entries</label>
                <div class="ief-array-row ief-array-header">
                    <span style="max-width:90px;flex:0 0 90px">Time (s)</span>
                    <span style="max-width:100px;flex:0 0 100px">Duration (s)</span>
                    <span style="flex:1">Text</span>
                    <span style="width:24px"></span>
                </div>
                <div v-for="(o, i) in form.overlays" :key="i" class="ief-array-row">
                    <input v-model.number="o.time" class="ief-input ief-input-sm" type="number" step="0.1" placeholder="0" style="max-width:90px">
                    <input v-model.number="o.duration" class="ief-input ief-input-sm" type="number" step="0.1" placeholder="2" style="max-width:100px">
                    <input v-model="o.text" class="ief-input ief-input-sm" placeholder="Overlay text">
                    <button class="ief-btn-rm" @click="form.overlays.splice(i, 1)">&times;</button>
                </div>
                <button class="ief-btn-add" @click="form.overlays.push({time:0,duration:2,text:''})">+ Add Global Overlay</button>
            </div>

            <div v-if="form.type === 'synchronized'" class="ief-field" style="margin-top:12px">
                <label>Markers</label>
                <div class="ief-array-row ief-array-header">
                    <span style="max-width:100px;flex:0 0 100px">Time (s)</span>
                    <span style="flex:1">Description</span>
                    <span style="width:24px"></span>
                </div>
                <div v-for="(m, i) in form.markers" :key="i" class="ief-array-row">
                    <input v-model.number="m.time" class="ief-input ief-input-sm" type="number" step="0.1" placeholder="0" style="max-width:100px">
                    <input v-model="m.label" class="ief-input ief-input-sm" placeholder="Marker label">
                    <button class="ief-btn-rm" @click="form.markers.splice(i, 1)">&times;</button>
                </div>
                <button class="ief-btn-add" @click="form.markers.push({time:0,label:''})">+ Add Marker</button>
            </div>
        </div>

        <!-- Figures -->
        <div class="ief-card" v-if="form.type === 'figures'">
            <h3>Figures</h3>
            <div v-for="(f, i) in form.figures" :key="i" class="ief-array-row">
                <input v-model="f.name" class="ief-input ief-input-sm" placeholder="Label">
                <select v-model="f.file" class="ief-input ief-input-sm">
                    <option value="" disabled>Select file...</option>
                    <option v-for="af in availableFiles" :key="af" :value="af">{{ af }}</option>
                </select>
                <button class="ief-btn-rm" @click="form.figures.splice(i, 1)">&times;</button>
            </div>
            <button class="ief-btn-add" @click="form.figures.push({name:'',file:''})">+ Add Figure</button>
        </div>

        <!-- PDF -->
        <div class="ief-card" v-if="form.type === 'pdf'">
            <h3>PDF Settings</h3>
            <div class="ief-field">
                <label>PDF File</label>
                <select v-model="form.file" class="ief-input">
                    <option value="" disabled>Select file...</option>
                    <option v-for="f in availableFiles" :key="f" :value="f">{{ f }}</option>
                </select>
            </div>
        </div>

        <!-- Code -->
        <div class="ief-card" v-if="form.type === 'code'">
            <h3>Code Settings</h3>
            <div class="ief-row">
                <div class="ief-field">
                    <label>File</label>
                    <select v-model="form.file" class="ief-input">
                        <option value="" disabled>Select file...</option>
                        <option v-for="f in availableFiles" :key="f" :value="f">{{ f }}</option>
                    </select>
                </div>
                <div class="ief-field"><label>Language</label><input v-model="form.language" class="ief-input" placeholder="python"></div>
            </div>
        </div>

        <!-- Interactive / 3D -->
        <div class="ief-card" v-if="form.type === 'interactive' || form.type === 'model3d'">
            <h3>Model Settings</h3>
            <div class="ief-field">
                <label>3D Model File</label>
                <select v-model="form.model" class="ief-input">
                    <option value="" disabled>Select file...</option>
                    <option v-for="f in availableFiles" :key="f" :value="f">{{ f }}</option>
                </select>
            </div>
        </div>

        <!-- Document Reference -->
        <div class="ief-card">
            <h3>Document Reference</h3>
            <div class="ief-row">
                <div class="ief-field"><label>Chapter</label><input v-model="form.chapter" class="ief-input" placeholder="e.g. 3"></div>
                <div class="ief-field"><label>Section</label><input v-model="form.section" class="ief-input" placeholder="e.g. 2"></div>
            </div>
            <div class="ief-row">
                <div class="ief-field"><label>Subsection</label><input v-model="form.subsection" class="ief-input" placeholder="e.g. 1"></div>
                <div class="ief-field"><label>Page</label><input v-model="form.page" class="ief-input" placeholder="e.g. 42"></div>
            </div>
        </div>

        <!-- Additional Information -->
        <div class="ief-card ief-card-grow">
            <div class="ief-md-header">
                <h3>Additional Information</h3>
                <div class="ief-md-tabs">
                    <button :class="{ active: mdTab === 'write' }" @click="mdTab = 'write'">Write</button>
                    <button :class="{ active: mdTab === 'preview' }" @click="mdTab = 'preview'">Preview</button>
                </div>
            </div>
            <textarea v-if="mdTab === 'write'" v-model="form.additionalInfo" class="ief-input ief-textarea ief-md-textarea" placeholder="Supports Markdown: headings, tables, code blocks, images, links..."></textarea>
            <div v-else class="ief-md-preview" v-html="renderedInfo"></div>
        </div>

        <!-- Thumbnail -->
        <div class="ief-card" v-if="showThumbnail">
            <h3>Thumbnail</h3>
            <div class="ief-thumb-row">
                <div v-if="form.thumbnail" class="ief-thumb-preview">
                    <img :src="`/thumbnails/${form.thumbnail}?t=${thumbCacheBust}`" @error="$event.target.style.display='none'">
                    <button class="ief-thumb-remove" @click="form.thumbnail = ''" title="Remove thumbnail">&times;</button>
                </div>
                <span v-else class="ief-no-thumb">No thumbnail</span>
                <div class="ief-thumb-actions">
                    <button v-if="pickerVideos.length" class="ief-btn-sm" @click="showPicker = true">Pick from video</button>
                    <button v-if="['video', 'synchronized', 'collection'].includes(form.type)" class="ief-btn-sm" @click="$emit('generate-thumbnail')" :disabled="generatingThumbnail">
                        {{ generatingThumbnail ? 'Generating...' : 'Auto-generate' }}
                    </button>
                    <input type="file" accept="image/*" ref="thumbInput" @change="onThumbSelect" style="display:none">
                    <button class="ief-btn-sm" @click="$refs.thumbInput.click()">Upload image</button>
                </div>
            </div>
        </div>

        <ThumbnailPicker
            v-if="showPicker"
            :videos="pickerVideos"
            @accept="onPickerAccept"
            @cancel="showPicker = false"
        />
    </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { marked } from 'marked'
import ColorAlphaPicker from '../ColorAlphaPicker.vue'
import ThumbnailPicker from './ThumbnailPicker.vue'
import { DEFAULT_OVERLAY_STYLE } from './itemFormHelpers.js'

marked.setOptions({ breaks: true, gfm: true })

const props = defineProps({
    form: { type: Object, required: true },
    availableFiles: { type: Array, default: () => [] },
    showThumbnail: { type: Boolean, default: false },
    generatingThumbnail: { type: Boolean, default: false },
})

const emit = defineEmits(['generate-thumbnail', 'upload-thumbnail'])

const mdTab = ref('write')
const showPicker = ref(false)
const thumbCacheBust = ref(Date.now())

watch(() => props.form.thumbnail, () => { thumbCacheBust.value = Date.now() })

const pickerVideos = computed(() => {
    const t = props.form.type
    if (t === 'video' && props.form.file) {
        return [{ name: 'Video', file: props.form.file }]
    }
    if ((t === 'synchronized' || t === 'collection') && props.form.videos?.length) {
        return props.form.videos.filter(v => v.file).map(v => ({ name: v.name || v.file, file: v.file }))
    }
    return []
})

function onPickerAccept(blob) {
    showPicker.value = false
    thumbCacheBust.value = Date.now()
    const file = new File([blob], 'thumbnail.jpg', { type: 'image/jpeg' })
    emit('upload-thumbnail', file)
}

const renderedInfo = computed(() => {
    if (!props.form.additionalInfo) return '<p style="color:var(--text-faint);font-style:italic">Nothing to preview</p>'
    return marked.parse(props.form.additionalInfo)
})

function resetOverlayStyle(styleObj) {
    Object.assign(styleObj, { ...DEFAULT_OVERLAY_STYLE })
}

function onThumbSelect(e) {
    const file = e.target.files[0]
    if (file) {
        thumbCacheBust.value = Date.now()
        emit('upload-thumbnail', file)
    }
    e.target.value = ''
}
</script>

<style scoped>
.ief { display: flex; flex-direction: column; gap: 16px; }

.ief-card {
    background: var(--bg-card, #1e1e2e);
    border: 1px solid var(--border, #2a2a3e);
    border-radius: 10px;
    padding: 18px 20px;
}
.ief-card h3 {
    font-size: 14px; font-weight: 600;
    margin: 0 0 14px; color: var(--text-primary);
}
.ief-card-grow { flex: 1; display: flex; flex-direction: column; }

/* Fields */
.ief-field { margin-bottom: 12px; }
.ief-field label {
    display: block; font-size: 12px; font-weight: 500;
    color: var(--text-muted); margin-bottom: 4px;
}

.ief-row { display: flex; gap: 10px; margin-bottom: 12px; }
.ief-row .ief-field { flex: 1; margin-bottom: 0; }

.ief-input {
    width: 100%; padding: 8px 11px;
    background: var(--bg-input, #16162a);
    border: 1px solid var(--border, #2a2a3e);
    border-radius: 7px; color: #ddd; font-size: 13px;
    outline: none; box-sizing: border-box;
    transition: border-color 0.15s;
}
.ief-input:focus { border-color: #3b82f6; }
.ief-input-sm { padding: 6px 9px; font-size: 12px; }
.ief-textarea { min-height: 60px; resize: vertical; font-family: inherit; }
select.ief-input { cursor: pointer; }

.ief-checkbox {
    display: flex; align-items: center; gap: 8px;
    font-size: 13px; color: var(--text-secondary); cursor: pointer; margin-top: 4px;
}

/* Array rows */
.ief-array-row { display: flex; gap: 6px; margin-bottom: 6px; align-items: center; }
.ief-array-header { font-size: 11px; color: var(--text-faint); margin-bottom: 2px; }

.ief-btn-rm {
    width: 24px; height: 24px;
    display: flex; align-items: center; justify-content: center;
    background: none; border: 1px solid var(--border); color: var(--text-faint);
    border-radius: 5px; cursor: pointer; font-size: 14px; flex-shrink: 0;
}
.ief-btn-rm:hover { color: #f87171; border-color: #f87171; }

.ief-btn-add {
    padding: 4px 10px; font-size: 11px;
    background: var(--bg-elevated, #1e1e2e); color: var(--text-muted);
    border: 1px solid var(--border); border-radius: 5px; cursor: pointer;
}
.ief-btn-add:hover { color: var(--text-secondary); border-color: var(--border-hover); }

/* Label row with reset button */
.ief-label-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.ief-btn-reset {
    padding: 2px 8px; font-size: 10px; background: none; color: var(--text-faint);
    border: 1px solid var(--border); border-radius: 4px; cursor: pointer; transition: all 0.15s;
}
.ief-btn-reset:hover { color: var(--text-secondary); border-color: var(--border-hover); }

/* Overlay style */
.ief-style-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.ief-style-field { flex: 1; min-width: 70px; }
.ief-style-label { display: block; font-size: 11px; color: var(--text-faint); margin-bottom: 3px; }

/* Video cards */
.ief-video-card {
    border: 1px solid var(--border); border-radius: 8px; padding: 10px;
    margin-bottom: 8px; background: rgba(255,255,255,0.02);
}
.ief-nested { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); }

/* Markdown editor */
.ief-md-header {
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;
}
.ief-md-header h3 { margin: 0; }

.ief-md-tabs {
    display: flex; gap: 0;
    border: 1px solid var(--border); border-radius: 6px; overflow: hidden;
}
.ief-md-tabs button {
    background: none; border: none; padding: 5px 14px; font-size: 12px;
    color: var(--text-muted); cursor: pointer; transition: all 0.15s;
}
.ief-md-tabs button.active { background: var(--border); color: var(--text-primary); }
.ief-md-tabs button:hover:not(.active) { background: rgba(255,255,255,0.03); }

.ief-md-textarea {
    flex: 1; min-height: 200px;
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 12px; line-height: 1.6; resize: vertical;
}

.ief-md-preview {
    flex: 1; min-height: 200px;
    border: 1px solid var(--border); border-radius: 7px;
    padding: 14px 16px; background: var(--bg-elevated);
    overflow-y: auto; font-size: 14px; line-height: 1.7;
    color: var(--text-secondary, #ccc);
}

.ief-md-preview :deep(h1) { font-size: 20px; font-weight: 600; margin: 0 0 12px; color: #eee; }
.ief-md-preview :deep(h2) { font-size: 17px; font-weight: 600; margin: 20px 0 10px; color: #eee; }
.ief-md-preview :deep(h3) { font-size: 15px; font-weight: 600; margin: 16px 0 8px; color: #eee; }
.ief-md-preview :deep(p) { margin: 0 0 10px; }
.ief-md-preview :deep(ul), .ief-md-preview :deep(ol) { margin: 0 0 10px; padding-left: 22px; }
.ief-md-preview :deep(li) { margin-bottom: 3px; }
.ief-md-preview :deep(a) { color: #3b82f6; text-decoration: none; }
.ief-md-preview :deep(a:hover) { text-decoration: underline; }
.ief-md-preview :deep(code) {
    background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 4px;
    font-size: 13px; font-family: 'SF Mono', 'Fira Code', monospace;
}
.ief-md-preview :deep(pre) {
    background: rgba(255,255,255,0.06); padding: 12px 14px; border-radius: 8px;
    overflow-x: auto; margin: 0 0 10px;
}
.ief-md-preview :deep(pre code) { background: none; padding: 0; }
.ief-md-preview :deep(blockquote) {
    border-left: 3px solid #3b82f6; margin: 0 0 10px; padding: 8px 14px;
    color: var(--text-muted);
}
.ief-md-preview :deep(img) { max-width: 100%; border-radius: 8px; margin: 6px 0; }
.ief-md-preview :deep(table) { width: 100%; border-collapse: collapse; margin: 0 0 10px; }
.ief-md-preview :deep(th), .ief-md-preview :deep(td) {
    padding: 7px 10px; border: 1px solid var(--border); text-align: left; font-size: 13px;
}
.ief-md-preview :deep(th) { background: rgba(255,255,255,0.06); font-weight: 600; }
.ief-md-preview :deep(hr) { border: none; border-top: 1px solid var(--border); margin: 16px 0; }

/* Thumbnail */
.ief-thumb-row { display: flex; align-items: flex-start; gap: 12px; flex-wrap: wrap; }
.ief-thumb-preview { position: relative; }
.ief-thumb-preview img { width: 120px; border-radius: 8px; border: 1px solid var(--border); }
.ief-thumb-remove {
    position: absolute; top: -6px; right: -6px;
    width: 20px; height: 20px; border-radius: 50%;
    background: #ef4444; color: #fff; border: none;
    cursor: pointer; font-size: 14px; line-height: 1;
    display: flex; align-items: center; justify-content: center;
}
.ief-no-thumb { font-size: 12px; color: var(--text-faint); }
.ief-thumb-actions { display: flex; flex-direction: column; gap: 6px; }
.ief-btn-sm {
    padding: 5px 12px; font-size: 11px;
    background: var(--bg-elevated); color: var(--text-muted);
    border: 1px solid var(--border); border-radius: 5px; cursor: pointer;
}
.ief-btn-sm:hover { color: var(--text-secondary); border-color: var(--border-hover); }
.ief-btn-sm:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
