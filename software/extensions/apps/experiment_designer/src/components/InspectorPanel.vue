<script setup>
import { computed, ref, nextTick } from 'vue'
import { getAllActions, INTERNAL_ACTIONS, getAllCategories, getAllRequirements, getAllGuards, getDataDefs, getTransitionPorts, TRIGGER_TYPES } from '../actionRegistry.js'
import {
  selection, nodes, edges, meta, selectedNodeIds,
  getNode, getEdge, getEdgesTo, updateNodeParams, updateNodeField,
  updateEdgeMapping, removeNode, removeEdge, removeSelectedNodes, snapshot,
  getChildren, isEntryOrExit, getAllEventNames, renameNode,
} from '../graphState.js'
import { notifyMutation } from '../mutationBridge.js'
import RefPicker from './RefPicker.vue'

// ── Selected item ──────────────────────────────────────────────────────────
const selectedNode = computed(() => {
  if (selection.type !== 'node') return null
  return getNode(selection.id)
})

const selectedEdge = computed(() => {
  if (selection.type !== 'edge') return null
  return getEdge(selection.id)
})

const actionDef = computed(() => {
  if (!selectedNode.value) return null
  return getAllActions()[selectedNode.value.type] || INTERNAL_ACTIONS[selectedNode.value.type]
})

const category = computed(() => {
  if (!actionDef.value) return null
  return getAllCategories()[actionDef.value.category]
})

const dataDefs = computed(() => {
  if (!selectedNode.value) return {}
  return getDataDefs(selectedNode.value.type)
})

const transitionPorts = computed(() => {
  if (!selectedNode.value) return []
  return getTransitionPorts(selectedNode.value.type)
})

const isContainerNode = computed(() => {
  return selectedNode.value && actionDef.value?.isContainer
})

const containerChildCount = computed(() => {
  if (!isContainerNode.value) return 0
  // Count real children (not entry/exit)
  return getChildren(selectedNode.value.id).filter(n => n.type !== '__entry__' && n.type !== '__exit__').length
})

const isEntryOrExitNode = computed(() => {
  if (!selectedNode.value) return false
  return selectedNode.value.type === '__entry__' || selectedNode.value.type === '__exit__'
})

const isRequirementNode = computed(() => {
  return selectedNode.value && selectedNode.value.isRequirement
})

const requirementDef = computed(() => {
  if (!isRequirementNode.value) return null
  return getAllRequirements()[selectedNode.value.type]
})

const isGuardNode = computed(() => {
  return selectedNode.value && selectedNode.value.isGuard
})

const guardDef = computed(() => {
  if (!isGuardNode.value) return null
  return getAllGuards()[selectedNode.value.type]
})

// ── RefPicker state ─────────────────────────────────────────────────────
const refPickerVisible = ref(false)
const refPickerAnchorRect = ref(null)
const refPickerContext = ref(null)
// Which param/mapping key triggered the picker
const refPickerTarget = ref(null) // { type: 'param'|'number'|'mapping', key: string }

function openRefPicker(event, key, pDef) {
  const el = event.currentTarget.closest('.input-with-ref')?.querySelector('input, select') || event.currentTarget
  const rect = el.getBoundingClientRect()
  refPickerAnchorRect.value = { left: rect.left, top: rect.top, width: rect.width, height: rect.height }
  refPickerContext.value = {
    paramName: key,
    nodeType: selectedNode.value?.type || null,
    nodeId: selectedNode.value?.id || null,
  }
  refPickerTarget.value = { type: 'param', key }
  refPickerVisible.value = true
}

function openRefPickerForNumber(event, key, pDef) {
  // Switch number input to text mode by setting the value to a string with '$'
  if (!selectedNode.value) return
  const currentVal = selectedNode.value.params[key]
  const strVal = currentVal != null ? String(currentVal) : ''
  // Set value to string so the template switches from number to text input
  snapshot()
  const params = { ...selectedNode.value.params, [key]: strVal.includes('$') ? strVal : strVal }
  updateNodeParams(selectedNode.value.id, params)
  // Now open the ref picker
  nextTick(() => {
    const el = event.currentTarget.closest('.input-with-ref')?.querySelector('input') || event.currentTarget
    const rect = el.getBoundingClientRect()
    refPickerAnchorRect.value = { left: rect.left, top: rect.top, width: rect.width, height: rect.height }
    refPickerContext.value = {
      paramName: key,
      nodeType: selectedNode.value?.type || null,
      nodeId: selectedNode.value?.id || null,
    }
    refPickerTarget.value = { type: 'number', key }
    refPickerVisible.value = true
  })
}

function openRefPickerForMapping(event, param) {
  const el = event.currentTarget.closest('.mapping-input-row')?.querySelector('input') || event.currentTarget
  const rect = el.getBoundingClientRect()
  refPickerAnchorRect.value = { left: rect.left, top: rect.top, width: rect.width, height: rect.height }
  refPickerContext.value = { paramName: null, nodeType: null, nodeId: null }
  refPickerTarget.value = { type: 'mapping', key: param }
  refPickerVisible.value = true
}

function isDefaultValue(key) {
  if (!selectedNode.value) return false
  const def = actionDef.value
  if (!def?.params?.[key]) return false
  const pDef = def.params[key]
  const currentVal = selectedNode.value.params[key]
  // Treat empty, null, and exact default as "default"
  if (currentVal === null || currentVal === undefined || currentVal === '') return true
  if (pDef.default !== undefined && String(currentVal) === String(pDef.default)) return true
  // Numeric zero is a default for most number fields
  if ((pDef.type === 'int' || pDef.type === 'float') && (currentVal === 0 || currentVal === '0')) return true
  return false
}

function onRefPickerSelect(text) {
  const target = refPickerTarget.value
  if (!target) return

  if (target.type === 'param' || target.type === 'number') {
    if (!selectedNode.value) return
    snapshot()
    const params = { ...selectedNode.value.params }
    // Replace entirely if current value is still the default
    if (isDefaultValue(target.key)) {
      params[target.key] = text
    } else {
      const currentVal = params[target.key] ?? ''
      params[target.key] = String(currentVal) + text
    }
    updateNodeParams(selectedNode.value.id, params)
  } else if (target.type === 'mapping') {
    if (!selectedEdge.value) return
    const currentVal = edgeMapping.value[target.key] ?? ''
    if (!currentVal) {
      updateMappingValue(target.key, text)
    } else {
      updateMappingValue(target.key, currentVal + text)
    }
  }
}

// Events editor
const newEventName = ref('')

function addEvent() {
  const name = newEventName.value.trim()
  if (!name) return
  if (meta.events.includes(name)) return
  snapshot()
  meta.events = [...meta.events, name]
  newEventName.value = ''
  notifyMutation('add_event', { name })
}

function removeEvent(name) {
  snapshot()
  meta.events = meta.events.filter(e => e !== name)
  notifyMutation('remove_event', { name })
}

const allEvents = computed(() => getAllEventNames())

// ── Edge info ──────────────────────────────────────────────────────────────
const edgeFromNode = computed(() => {
  if (!selectedEdge.value) return null
  return getNode(selectedEdge.value.from)
})

const edgeToNode = computed(() => {
  if (!selectedEdge.value) return null
  return getNode(selectedEdge.value.to)
})

const edgeSourceDataDefs = computed(() => {
  if (!edgeFromNode.value) return {}
  return getDataDefs(edgeFromNode.value.type)
})

const edgeTargetParams = computed(() => {
  if (!edgeToNode.value) return {}
  const def = getAllActions()[edgeToNode.value.type] || INTERNAL_ACTIONS[edgeToNode.value.type]
  return def?.params || {}
})

const edgeMapping = computed(() => {
  return selectedEdge.value?.mapping || {}
})

const unmappedTargetParams = computed(() => {
  const mapped = edgeMapping.value
  return Object.keys(edgeTargetParams.value).filter(k => !(k in mapped))
})

const newMappingParam = ref('')
const mappingInputRefs = ref({})

function addMapping(param) {
  if (!selectedEdge.value || !param) return
  snapshot()
  const mapping = { ...edgeMapping.value, [param]: '' }
  updateEdgeMapping(selectedEdge.value.id, mapping)
  newMappingParam.value = ''
}

function updateMappingValue(param, value) {
  if (!selectedEdge.value) return
  snapshot()
  const mapping = { ...edgeMapping.value, [param]: value }
  updateEdgeMapping(selectedEdge.value.id, mapping)
}

function removeMapping(param) {
  if (!selectedEdge.value) return
  snapshot()
  const mapping = { ...edgeMapping.value }
  delete mapping[param]
  updateEdgeMapping(selectedEdge.value.id, mapping)
}

function setMappingInputRef(param, el) {
  if (el) mappingInputRefs.value[param] = el
  else delete mappingInputRefs.value[param]
}

function insertChip(param, key) {
  const input = mappingInputRefs.value[param]
  if (!input) return
  const ref = `\${${key}}`
  const start = input.selectionStart ?? input.value.length
  const end = input.selectionEnd ?? start
  const newVal = input.value.slice(0, start) + ref + input.value.slice(end)
  input.value = newVal
  input.dispatchEvent(new Event('change'))
  input.focus()
  const cursor = start + ref.length
  input.setSelectionRange(cursor, cursor)
}

// ── Variables ──────────────────────────────────────────────────────────────
const newVarName = ref('')
const newVarValue = ref('')

function addVariable() {
  const name = newVarName.value.trim()
  if (!name) return
  snapshot()
  const val = parseVarValue(newVarValue.value)
  meta.variables = { ...meta.variables, [name]: val }
  newVarName.value = ''
  newVarValue.value = ''
  notifyMutation('add_variable', { name, value: val })
}

function removeVariable(name) {
  snapshot()
  const vars = { ...meta.variables }
  delete vars[name]
  meta.variables = vars
  notifyMutation('remove_variable', { name })
}

function updateVariable(name, value) {
  snapshot()
  const parsed = parseVarValue(value)
  meta.variables = { ...meta.variables, [name]: parsed }
  notifyMutation('update_variable', { name, value: parsed })
}

function parseVarValue(text) {
  if (text === 'true') return true
  if (text === 'false') return false
  if (text === 'null') return null
  const num = Number(text)
  if (!isNaN(num) && text !== '') return num
  return text
}

// ── Param editing ──────────────────────────────────────────────────────────
function onParamChange(key, value, pDef) {
  if (!selectedNode.value) return
  snapshot()
  const params = { ...selectedNode.value.params }

  // For the new framework, most values can be expressions (strings with ${...})
  // so we keep them as strings unless they're clearly typed
  if (pDef.type === 'int' && !String(value).includes('$')) {
    params[key] = value === '' ? null : parseInt(value, 10)
  } else if (pDef.type === 'float' && !String(value).includes('$')) {
    params[key] = value === '' ? null : parseFloat(value)
  } else if (pDef.type === 'bool') {
    params[key] = value === 'true' || value === true
  } else if (pDef.type === 'list') {
    if (typeof value === 'string') {
      try { params[key] = JSON.parse(value) } catch { params[key] = value }
    } else {
      params[key] = value
    }
  } else if (pDef.type === 'dict') {
    if (typeof value === 'string') {
      try { params[key] = JSON.parse(value) } catch { params[key] = value }
    } else {
      params[key] = value
    }
  } else {
    params[key] = value
  }

  updateNodeParams(selectedNode.value.id, params)
}

function onFieldChange(field, value) {
  if (!selectedNode.value) return
  snapshot()
  updateNodeField(selectedNode.value.id, field, value)
}

function onWaitChange(field, value) {
  if (!selectedNode.value) return
  snapshot()
  const parsed = value === '' || value === null ? null : parseFloat(value)
  updateNodeField(selectedNode.value.id, field, parsed || null)
}

function onMessageChange(field, value) {
  if (!selectedNode.value) return
  snapshot()
  updateNodeField(selectedNode.value.id, field, value || null)
}

// Commit input on blur — dispatches a 'change' event if the value differs from last committed
function commitOnBlur(e) {
  e.target.dispatchEvent(new Event('change'))
}

function onTriggerTypeChange(type) {
  if (!selectedNode.value) return
  snapshot()
  const trigger = { type }
  if (type === 'tick') trigger.tick = 0
  else if (type === 'time') trigger.time = 0
  else if (type === 'event') trigger.event = ''
  else if (type === 'periodic') { trigger.period = 1; trigger.period_unit = 'seconds' }
  updateNodeField(selectedNode.value.id, 'trigger', type === 'transition' ? null : trigger)
  // Remove incoming edges when changing away from transition (input port hides)
  if (type !== 'transition') {
    const incoming = getEdgesTo(selectedNode.value.id)
    for (const edge of incoming) {
      edges.value = edges.value.filter(e => e.id !== edge.id)
    }
  }
  nodes.value = [...nodes.value]
}

function onTriggerFieldChange(field, value) {
  if (!selectedNode.value) return
  snapshot()
  const trigger = { ...(selectedNode.value.trigger || {}) }
  if (field === 'tick' || field === 'time' || field === 'period') {
    trigger[field] = value === '' ? null : parseFloat(value)
  } else {
    trigger[field] = value
  }
  updateNodeField(selectedNode.value.id, 'trigger', trigger)
  nodes.value = [...nodes.value]
}

function onIdChange(value) {
  if (!selectedNode.value) return
  snapshot()
  renameNode(selectedNode.value.id, value)
}

function formatValue(val) {
  if (val === null || val === undefined) return ''
  if (Array.isArray(val) || typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function deleteSelected() {
  if (selection.type === 'node') removeNode(selection.id)
  else if (selection.type === 'edge') removeEdge(selection.id)
}

// ── Meta editing ───────────────────────────────────────────────────────────
function onMetaChange(field, value) {
  snapshot()
  if (field === 'timeout') {
    const parsed = value === '' ? null : parseFloat(value)
    meta[field] = parsed
    notifyMutation('update_meta', { field, value: parsed })
  } else {
    meta[field] = value
    notifyMutation('update_meta', { field, value })
  }
}
</script>

<template>
  <aside class="inspector">
    <div class="inspector-header">
      <span class="inspector-title">Inspector</span>
    </div>

    <div class="inspector-body">
      <!-- ═══════ Nothing selected → experiment settings ═══════ -->
      <template v-if="!selectedNode && !selectedEdge">
        <div class="section">
          <div class="section-title">Experiment</div>

          <label class="field">
            <span class="field-label">ID</span>
            <input type="text" :value="meta.id" @change="onMetaChange('id', $event.target.value)" class="field-input" />
          </label>

          <label class="field">
            <span class="field-label">Description</span>
            <textarea :value="meta.description" @change="onMetaChange('description', $event.target.value)" class="field-textarea" rows="3"></textarea>
          </label>

          <label class="field">
            <span class="field-label">Timeout (s)</span>
            <input type="number" :value="meta.timeout ?? ''" @change="onMetaChange('timeout', $event.target.value)" @blur="commitOnBlur" class="field-input" placeholder="none" min="0" step="1" />
          </label>
        </div>

        <!-- Variables editor -->
        <div class="section">
          <div class="section-title">Variables</div>

          <div v-for="(value, name) in meta.variables" :key="name" class="var-row">
            <span class="var-name">{{ name }}</span>
            <input type="text" :value="formatValue(value)" @change="updateVariable(name, $event.target.value)" class="var-input" />
            <button class="var-del" @click="removeVariable(name)" title="Remove">&times;</button>
          </div>

          <div class="var-add-row">
            <input v-model="newVarName" type="text" placeholder="name" class="var-input" @keydown.enter="addVariable" />
            <input v-model="newVarValue" type="text" placeholder="value" class="var-input" @keydown.enter="addVariable" />
            <button class="var-add-btn" @click="addVariable" title="Add variable">+</button>
          </div>
        </div>

        <!-- Events editor -->
        <div class="section">
          <div class="section-title">Events</div>

          <div v-for="(source, name) in allEvents" :key="name" class="var-row">
            <span class="var-name" style="color: #a55eea">{{ name }}</span>
            <span v-if="source === 'auto'" class="auto-tag">auto</span>
            <button v-if="source === 'manual'" class="var-del" @click="removeEvent(name)" title="Remove">&times;</button>
          </div>

          <div v-if="Object.keys(allEvents).length === 0" class="help-text">No events declared</div>

          <div class="var-add-row">
            <input v-model="newEventName" type="text" placeholder="event name" class="var-input" @keydown.enter="addEvent" />
            <button class="var-add-btn" @click="addEvent" title="Add event">+</button>
          </div>
        </div>

        <div class="section">
          <div class="section-title">Graph Info</div>
          <div class="info-row">Nodes: {{ nodes.filter(n => n.type !== '__start__' && n.type !== '__stop__' && n.type !== '__entry__' && n.type !== '__exit__').length }}</div>
          <div class="info-row">Connections: {{ edges.length }}</div>
        </div>

        <!-- Expression help -->
        <div class="section">
          <div class="section-title hint">Expression Syntax</div>
          <div class="help-text">
            <code>$var</code> — variable reference<br>
            <code>${"${expr}"}</code> — expression<br>
            <code>${"${x * 2 + 1}"}</code> — arithmetic<br>
            <code>${"${abs(offset)}"}</code> — safe functions<br>
            <code>$action_id.result</code> — action data<br>
            <code>$action_id:param</code> — action param
          </div>
        </div>
      </template>

      <!-- ═══════ Entry/Exit nodes ═══════ -->
      <template v-else-if="isEntryOrExitNode">
        <div class="section">
          <div class="section-title node-type-title">
            {{ selectedNode.type === '__entry__' ? 'Entry Node' : 'Exit Node' }}
          </div>
          <div class="info-row" style="font-size: 10px; color: var(--text-dim)">
            {{ selectedNode.type === '__entry__'
              ? 'Internal entry point for container. Connect to first sub-action.'
              : 'Internal exit point for container. Connect from last sub-action.'
            }}
          </div>
          <div class="info-row" style="font-size: 10px; color: var(--text-dim); margin-top: 4px;">
            Cannot be deleted independently.
          </div>
        </div>
      </template>

      <!-- ═══════ Start/Stop nodes ═══════ -->
      <template v-else-if="selectedNode && (selectedNode.type === '__start__' || selectedNode.type === '__stop__')">
        <div class="section">
          <div class="section-title node-type-title">
            {{ selectedNode.type === '__start__' ? 'Start Node' : 'Stop Node' }}
          </div>
          <div class="info-row" style="font-size: 10px; color: var(--text-dim)">
            {{ selectedNode.type === '__start__'
              ? 'Entry point. Connected actions get trigger: immediate.'
              : 'Visual endpoint. Generates a stop action in YAML.'
            }}
          </div>
        </div>

        <!-- Stop node params -->
        <template v-if="selectedNode.type === '__stop__'">
          <div class="section">
            <label class="field">
              <span class="field-label">Status</span>
              <select :value="selectedNode.params?.status || 'finished'" @change="onParamChange('status', $event.target.value, { type: 'str' })" class="field-input">
                <option value="finished">finished</option>
                <option value="error">error</option>
                <option value="aborted">aborted</option>
              </select>
            </label>
            <label class="field">
              <span class="field-label">Message</span>
              <input type="text" :value="selectedNode.params?.message || ''" @change="onParamChange('message', $event.target.value, { type: 'str' })" class="field-input" placeholder="optional" />
            </label>
          </div>
        </template>
      </template>

      <!-- ═══════ Requirement nodes ═══════ -->
      <template v-else-if="isRequirementNode && requirementDef">
        <div class="section">
          <div class="section-title node-type-title">
            <span class="type-badge" style="background: #e056a018; color: #e056a0; border-color: #e056a0">
              {{ selectedNode.type }}
            </span>
            <span class="container-tag" style="color: #e056a0">requirement</span>
          </div>
          <div class="action-desc">{{ requirementDef.description }}</div>
        </div>

        <!-- ID -->
        <div class="section">
          <label class="field">
            <span class="field-label">ID</span>
            <input type="text" :value="selectedNode.id" @change="onIdChange($event.target.value)" class="field-input" />
          </label>
        </div>

        <!-- Parameters -->
        <div class="section" v-if="requirementDef.params && Object.keys(requirementDef.params).length > 0">
          <div class="section-title">Parameters</div>

          <template v-for="(pDef, key) in requirementDef.params" :key="key">
            <label class="field">
              <span class="field-label">
                {{ key }}
                <span v-if="pDef.required" class="required-dot">*</span>
              </span>

              <!-- Boolean -->
              <select v-if="pDef.type === 'bool'" :value="String(selectedNode.params[key] ?? pDef.default ?? false)" @change="onParamChange(key, $event.target.value, pDef)" class="field-input">
                <option value="true">true</option>
                <option value="false">false</option>
              </select>

              <!-- Options -->
              <select v-else-if="pDef.options" :value="selectedNode.params[key] ?? pDef.default ?? ''" @change="onParamChange(key, $event.target.value, pDef)" class="field-input">
                <option v-for="opt in pDef.options" :key="opt" :value="opt">{{ opt }}</option>
              </select>

              <!-- Number -->
              <input
                v-else-if="pDef.type === 'int' || pDef.type === 'float'"
                type="number"
                :value="formatValue(selectedNode.params[key])"
                @change="onParamChange(key, $event.target.value, pDef)"
                @blur="commitOnBlur"
                class="field-input"
                :step="pDef.type === 'float' ? 0.1 : 1"
                :placeholder="pDef.default != null ? String(pDef.default) : ''"
              />

              <!-- String -->
              <input
                v-else
                type="text"
                :value="selectedNode.params[key] ?? ''"
                @change="onParamChange(key, $event.target.value, pDef)"
                @blur="commitOnBlur"
                class="field-input"
                :placeholder="pDef.default != null ? String(pDef.default) : ''"
              />

              <span v-if="pDef.description" class="field-hint">{{ pDef.description }}</span>
            </label>
          </template>
        </div>

        <div class="section">
          <div class="help-text" style="color: #e056a0">Requirements are checked before the experiment starts.</div>
        </div>

        <div class="section">
          <button class="delete-btn" @click="deleteSelected">Delete Requirement</button>
        </div>
      </template>

      <!-- ═══════ Guard nodes ═══════ -->
      <template v-else-if="isGuardNode">
        <div class="section">
          <div class="section-title node-type-title">
            <span class="type-badge" style="background: #3dc1d318; color: #3dc1d3; border-color: #3dc1d3">
              {{ selectedNode.type }}
            </span>
            <span class="container-tag" style="color: #3dc1d3">guard</span>
          </div>
          <div v-if="guardDef" class="action-desc">{{ guardDef.description }}</div>
        </div>

        <!-- ID -->
        <div class="section">
          <label class="field">
            <span class="field-label">ID</span>
            <input type="text" :value="selectedNode.id" @change="onIdChange($event.target.value)" class="field-input" />
          </label>
        </div>

        <!-- Parameters -->
        <div class="section" v-if="guardDef.params && Object.keys(guardDef.params).length > 0">
          <div class="section-title">Parameters</div>

          <template v-for="(pDef, key) in guardDef.params" :key="key">
            <label class="field">
              <span class="field-label">
                {{ key }}
                <span v-if="pDef.required" class="required-dot">*</span>
              </span>

              <!-- Boolean -->
              <select v-if="pDef.type === 'bool'" :value="String(selectedNode.params[key] ?? pDef.default ?? false)" @change="onParamChange(key, $event.target.value, pDef)" class="field-input">
                <option value="true">true</option>
                <option value="false">false</option>
              </select>

              <!-- Options -->
              <select v-else-if="pDef.options" :value="selectedNode.params[key] ?? pDef.default ?? ''" @change="onParamChange(key, $event.target.value, pDef)" class="field-input">
                <option v-for="opt in pDef.options" :key="opt" :value="opt">{{ opt }}</option>
              </select>

              <!-- Number -->
              <input
                v-else-if="pDef.type === 'int' || pDef.type === 'float'"
                type="number"
                :value="formatValue(selectedNode.params[key])"
                @change="onParamChange(key, $event.target.value, pDef)"
                @blur="commitOnBlur"
                class="field-input"
                :step="pDef.type === 'float' ? 0.1 : 1"
                :placeholder="pDef.default != null ? String(pDef.default) : ''"
              />

              <!-- String -->
              <input
                v-else
                type="text"
                :value="selectedNode.params[key] ?? ''"
                @change="onParamChange(key, $event.target.value, pDef)"
                @blur="commitOnBlur"
                class="field-input"
                :placeholder="pDef.default != null ? String(pDef.default) : ''"
              />

              <span v-if="pDef.description" class="field-hint">{{ pDef.description }}</span>
            </label>
          </template>
        </div>

        <div class="section">
          <div class="help-text" style="color: #3dc1d3">Guards run setup before experiment start and teardown on finish (guaranteed cleanup).</div>
        </div>

        <div class="section">
          <button class="delete-btn" @click="deleteSelected">Delete Guard</button>
        </div>
      </template>

      <!-- ═══════ Action nodes ═══════ -->
      <template v-else-if="selectedNode && actionDef">
        <div class="section">
          <div class="section-title node-type-title">
            <span class="type-badge" :style="{ background: category?.color + '22', color: category?.color, borderColor: category?.color }">
              {{ selectedNode.type }}
            </span>
            <span v-if="actionDef.isContainer" class="container-tag">container</span>
          </div>
          <div class="action-desc">{{ actionDef.description }}</div>
        </div>

        <!-- ID -->
        <div class="section">
          <label class="field">
            <span class="field-label">ID</span>
            <input type="text" :value="selectedNode.id" @change="onIdChange($event.target.value)" class="field-input" />
          </label>
        </div>

        <!-- Container info -->
        <div class="section" v-if="isContainerNode">
          <div class="section-title">Container</div>
          <div class="info-row">
            <span class="field-label">Dimensions:</span>
            <span>{{ selectedNode.width }} &times; {{ selectedNode.height }}px</span>
          </div>
          <div class="info-row">
            <span class="field-label">Children:</span>
            <span>{{ containerChildCount }} action{{ containerChildCount !== 1 ? 's' : '' }}</span>
          </div>
        </div>

        <!-- Trigger -->
        <div class="section">
          <div class="section-title">Trigger</div>
          <label class="field">
            <span class="field-label">Type</span>
            <select
              :value="selectedNode.trigger?.type || 'transition'"
              @change="onTriggerTypeChange($event.target.value)"
              class="field-input"
            >
              <option v-for="t in TRIGGER_TYPES" :key="t" :value="t">{{ t }}</option>
            </select>
          </label>

          <!-- Trigger-specific fields -->
          <label v-if="selectedNode.trigger?.type === 'tick'" class="field">
            <span class="field-label">Tick number</span>
            <input type="number" :value="selectedNode.trigger?.tick ?? 0" @change="onTriggerFieldChange('tick', $event.target.value)" @blur="commitOnBlur" class="field-input" min="0" step="1" />
          </label>

          <label v-if="selectedNode.trigger?.type === 'time'" class="field">
            <span class="field-label">Time (s)</span>
            <input type="number" :value="selectedNode.trigger?.time ?? 0" @change="onTriggerFieldChange('time', $event.target.value)" @blur="commitOnBlur" class="field-input" min="0" step="0.1" />
          </label>

          <label v-if="selectedNode.trigger?.type === 'event'" class="field">
            <span class="field-label">Event name</span>
            <input type="text" :value="selectedNode.trigger?.event ?? ''" @change="onTriggerFieldChange('event', $event.target.value)" @blur="commitOnBlur" class="field-input" placeholder="event_name" />
          </label>

          <template v-if="selectedNode.trigger?.type === 'periodic'">
            <label class="field">
              <span class="field-label">Period</span>
              <input type="number" :value="selectedNode.trigger?.period ?? 1" @change="onTriggerFieldChange('period', $event.target.value)" @blur="commitOnBlur" class="field-input" min="0" step="0.1" />
            </label>
            <label class="field">
              <span class="field-label">Period unit</span>
              <select :value="selectedNode.trigger?.period_unit || 'seconds'" @change="onTriggerFieldChange('period_unit', $event.target.value)" class="field-input">
                <option value="seconds">seconds</option>
                <option value="ticks">ticks</option>
              </select>
            </label>
          </template>

          <div v-if="!selectedNode.trigger || selectedNode.trigger?.type === 'transition'" class="help-text" style="margin-top: 2px;">
            Triggered by incoming connection from another action.
          </div>
          <div v-else-if="selectedNode.trigger?.type === 'immediate'" class="help-text" style="margin-top: 2px;">
            Starts as soon as the experiment begins (same as connected to Start).
          </div>
        </div>

        <!-- Wait before / after -->
        <div class="section">
          <div class="section-title">Wait Delays</div>
          <label class="field">
            <span class="field-label">Wait before (s)</span>
            <input
              type="number"
              :value="selectedNode.wait_before ?? ''"
              @change="onWaitChange('wait_before', $event.target.value)"
              @blur="commitOnBlur"
              class="field-input"
              placeholder="none"
              min="0"
              step="0.1"
            />
            <span class="field-hint">Delay before action executes</span>
          </label>
          <label class="field">
            <span class="field-label">Wait after (s)</span>
            <input
              type="number"
              :value="selectedNode.wait_after ?? ''"
              @change="onWaitChange('wait_after', $event.target.value)"
              @blur="commitOnBlur"
              class="field-input"
              placeholder="none"
              min="0"
              step="0.1"
            />
            <span class="field-hint">Delay after action completes</span>
          </label>
        </div>

        <!-- Messages before / after -->
        <div class="section">
          <div class="section-title">Messages</div>
          <label class="field">
            <span class="field-label">Message before</span>
            <input
              type="text"
              :value="selectedNode.message_before ?? ''"
              @change="onMessageChange('message_before', $event.target.value)"
              @blur="commitOnBlur"
              class="field-input"
              placeholder="none"
            />
            <span class="field-hint">User-facing message emitted before action executes</span>
          </label>
          <label class="field">
            <span class="field-label">Message after</span>
            <input
              type="text"
              :value="selectedNode.message_after ?? ''"
              @change="onMessageChange('message_after', $event.target.value)"
              @blur="commitOnBlur"
              class="field-input"
              placeholder="none"
            />
            <span class="field-hint">User-facing message emitted after action completes</span>
          </label>
        </div>

        <!-- Parameters -->
        <div class="section" v-if="actionDef.params && Object.keys(actionDef.params).length > 0">
          <div class="section-title">Parameters</div>

          <template v-for="(pDef, key) in actionDef.params" :key="key">
            <label class="field">
              <span class="field-label">
                {{ key }}
                <span v-if="pDef.required" class="required-dot">*</span>
              </span>

              <!-- Boolean -->
              <select v-if="pDef.type === 'bool'" :value="String(selectedNode.params[key] ?? pDef.default ?? false)" @change="onParamChange(key, $event.target.value, pDef)" class="field-input">
                <option value="true">true</option>
                <option value="false">false</option>
              </select>

              <!-- Options (select) -->
              <select v-else-if="pDef.options" :value="selectedNode.params[key] ?? pDef.default ?? ''" @change="onParamChange(key, $event.target.value, pDef)" class="field-input">
                <option v-for="opt in pDef.options" :key="opt" :value="opt">{{ opt }}</option>
              </select>

              <!-- Number (only if no expression support needed) -->
              <div v-else-if="(pDef.type === 'int' || pDef.type === 'float') && !String(selectedNode.params[key] || '').includes('$')" class="input-with-ref">
                <input
                  type="number"
                  :value="formatValue(selectedNode.params[key])"
                  @change="onParamChange(key, $event.target.value, pDef)"
                  @blur="commitOnBlur"
                  class="field-input"
                  :min="pDef.min" :max="pDef.max"
                  :step="pDef.step || (pDef.type === 'float' ? 0.1 : 1)"
                  :placeholder="pDef.default != null ? String(pDef.default) : ''"
                />
                <button class="ref-btn" @click="openRefPickerForNumber($event, key, pDef)" title="Insert reference">${}</button>
              </div>

              <!-- List / Dict (JSON) -->
              <input
                v-else-if="pDef.type === 'list' || pDef.type === 'dict'"
                type="text"
                :value="formatValue(selectedNode.params[key])"
                @change="onParamChange(key, $event.target.value, pDef)"
                @blur="commitOnBlur"
                class="field-input"
                :placeholder="pDef.type === 'list' ? '[1, 2, 3]' : '{key: val}'"
              />

              <!-- String / expression (default) -->
              <div v-else class="input-with-ref">
                <input
                  type="text"
                  :value="selectedNode.params[key] ?? ''"
                  @change="onParamChange(key, $event.target.value, pDef)"
                  @blur="commitOnBlur"
                  class="field-input expr-input"
                  :placeholder="pDef.default != null ? String(pDef.default) : ''"
                />
                <button class="ref-btn" @click="openRefPicker($event, key, pDef)" title="Insert reference">${}</button>
              </div>

              <span v-if="pDef.description" class="field-hint">{{ pDef.description }}</span>
            </label>
          </template>
        </div>

        <!-- Data outputs -->
        <div class="section" v-if="Object.keys(dataDefs).length > 0">
          <div class="section-title">Data Outputs</div>
          <div v-for="(dd, key) in dataDefs" :key="key" class="info-row">
            <code class="data-key">${{ selectedNode.id }}.{{ key }}</code>
            <span v-if="dd.description" class="field-hint">{{ dd.description }}</span>
          </div>
        </div>

        <!-- Transition ports -->
        <div class="section">
          <div class="section-title">Transition Ports</div>
          <div class="port-list">
            <span v-for="port in transitionPorts" :key="port" class="port-chip" :class="port">{{ port }}</span>
            <span class="port-chip error">error (implicit)</span>
          </div>
        </div>

        <!-- Delete -->
        <div class="section">
          <button class="delete-btn" @click="deleteSelected">
            {{ isContainerNode && containerChildCount > 0
              ? `Delete Container (${containerChildCount} children)`
              : 'Delete Node'
            }}
          </button>
          <div v-if="isContainerNode && containerChildCount > 0" class="help-text" style="margin-top: 4px; color: #f7b731;">
            Deleting a container removes all children and their connections.
          </div>
        </div>
      </template>

      <!-- ═══════ Multi-selection ═══════ -->
      <template v-else-if="selection.type === 'multi'">
        <div class="section">
          <div class="section-title">Multi-Selection</div>
          <div class="info-row">{{ selectedNodeIds.length }} nodes selected</div>
          <div class="help-text" style="margin-top: 4px">
            Drag any selected node to move all. Press Delete to remove all.
          </div>
        </div>
        <div class="section">
          <button class="delete-btn" @click="removeSelectedNodes()">Delete Selected ({{ selectedNodeIds.length }})</button>
        </div>
      </template>

      <!-- ═══════ Edge selected ═══════ -->
      <template v-else-if="selectedEdge">
        <div class="section">
          <div class="section-title">Connection</div>

          <div class="info-row">
            <span class="field-label">From:</span>
            <span>{{ edgeFromNode?.id || '?' }}</span>
          </div>
          <div class="info-row">
            <span class="field-label">Port:</span>
            <span class="port-chip" :class="selectedEdge.fromPort">{{ selectedEdge.fromPort }}</span>
          </div>
          <div class="info-row">
            <span class="field-label">To:</span>
            <span>{{ edgeToNode?.id || '?' }}</span>
          </div>
        </div>

        <!-- Source data reference -->
        <div class="section" v-if="Object.keys(edgeSourceDataDefs).length > 0">
          <div class="section-title hint">Source Data <span class="source-node-id">{{ edgeFromNode?.id }}</span></div>
          <div v-for="(dd, key) in edgeSourceDataDefs" :key="key" class="source-data-item">
            <code class="data-key">{{ key }}</code>
            <span v-if="dd.type" class="type-chip">{{ dd.type }}</span>
            <span v-if="dd.description" class="field-hint">{{ dd.description }}</span>
          </div>
        </div>

        <!-- Data mapping cards -->
        <div class="section" v-if="Object.keys(edgeTargetParams).length > 0">
          <div class="section-title">Data Mapping</div>

          <div v-for="(val, param) in edgeMapping" :key="param" class="mapping-card">
            <div class="mapping-card-header">
              <span class="mapping-card-name">{{ param }}</span>
              <span v-if="edgeTargetParams[param]?.type" class="type-chip">{{ edgeTargetParams[param].type }}</span>
              <span v-if="edgeTargetParams[param]?.required" class="required-dot">*</span>
              <button class="mapping-card-del" @click="removeMapping(param)" title="Remove mapping">&times;</button>
            </div>
            <div class="mapping-input-row">
              <input
                type="text"
                :value="val"
                :ref="el => setMappingInputRef(param, el)"
                @change="updateMappingValue(param, $event.target.value)"
                class="field-input expr-input mapping-card-input"
                :placeholder="edgeTargetParams[param]?.description || 'value or ${expr}'"
              />
              <button class="ref-btn ref-btn-mapping" @click="openRefPickerForMapping($event, param)" title="Insert reference">${}</button>
            </div>
            <div class="mapping-chips" v-if="Object.keys(edgeSourceDataDefs).length > 0">
              <span class="mapping-chip-arrow">&larr;</span>
              <button
                v-for="(dd, key) in edgeSourceDataDefs"
                :key="key"
                class="mapping-chip"
                @click="insertChip(param, key)"
                :title="dd.description || key"
              >{{ key }}</button>
            </div>
          </div>

          <!-- Add mapping -->
          <div class="mapping-add-row" v-if="unmappedTargetParams.length > 0">
            <select v-model="newMappingParam" class="field-input mapping-select">
              <option value="" disabled>+ add param...</option>
              <option v-for="p in unmappedTargetParams" :key="p" :value="p">{{ p }}</option>
            </select>
            <button class="var-add-btn" @click="addMapping(newMappingParam)" :disabled="!newMappingParam" title="Add mapping">+</button>
          </div>

          <div v-if="Object.keys(edgeMapping).length === 0" class="help-text" style="margin-top: 2px;">
            Map source data to target action parameters.
          </div>
        </div>

        <div class="section">
          <button class="delete-btn" @click="deleteSelected">Delete Connection</button>
        </div>
      </template>
    </div>

    <RefPicker
      :visible="refPickerVisible"
      :anchorRect="refPickerAnchorRect"
      :paramContext="refPickerContext"
      @select="onRefPickerSelect"
      @close="refPickerVisible = false"
    />
  </aside>
</template>

<style scoped>
.inspector {
  width: 280px;
  height: 100%;
  flex-shrink: 0;
  background: var(--bg-surface);
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.inspector-header {
  padding: 8px 12px;
  font-size: 11px;
  font-weight: 600;
  border-bottom: 1px solid var(--border);
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-dim);
}

.inspector-body {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

/* Sections */
.section {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
}

.section-title {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.section-title.hint { color: var(--accent); }

/* Type badge */
.type-badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid;
}

.container-tag {
  font-size: 9px;
  color: var(--text-dim);
  background: var(--bg);
  padding: 1px 5px;
  border-radius: 3px;
  margin-left: 6px;
}

.action-desc {
  font-size: 10px;
  color: var(--text-dim);
  margin-top: 4px;
}

/* Fields */
.field {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 8px;
}

.field-label {
  font-size: 10px;
  color: var(--text-dim);
  font-weight: 500;
}

.required-dot { color: #fc5c65; font-weight: 700; }

.field-input, .field-textarea {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  padding: 4px 6px;
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 3px;
  outline: none;
  width: 100%;
}
.field-input:focus, .field-textarea:focus { border-color: var(--accent); }

.field-textarea { resize: vertical; min-height: 40px; }

.field-hint {
  font-size: 9px;
  color: var(--text-dim);
  opacity: 0.7;
}

/* Expression-aware inputs get a subtle indicator */
.expr-input { border-left: 2px solid var(--accent); padding-left: 5px; }

/* Input with reference picker button */
.input-with-ref {
  display: flex;
  gap: 2px;
  align-items: stretch;
}
.input-with-ref .field-input { flex: 1; min-width: 0; }

.ref-btn {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  font-weight: 600;
  padding: 2px 4px;
  background: var(--bg);
  color: var(--accent);
  border: 1px solid var(--border);
  border-radius: 3px;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  line-height: 1;
  transition: background 0.1s, border-color 0.1s;
}
.ref-btn:hover {
  background: var(--bg-hover);
  border-color: var(--accent);
}

.ref-btn-mapping {
  align-self: center;
}

.mapping-input-row {
  display: flex;
  gap: 2px;
  align-items: stretch;
  margin-bottom: 4px;
}
.mapping-input-row .mapping-card-input {
  flex: 1;
  min-width: 0;
  margin-bottom: 0;
}

/* Info rows */
.info-row {
  font-size: 11px;
  padding: 2px 0;
  display: flex;
  gap: 8px;
  align-items: center;
}

/* Data output keys */
.data-key {
  font-size: 10px;
  color: var(--accent);
  background: var(--bg);
  padding: 1px 4px;
  border-radius: 2px;
}

/* Port chips */
.port-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.port-chip {
  font-size: 9px;
  padding: 2px 6px;
  border-radius: 3px;
  background: var(--bg);
  border: 1px solid var(--border);
}
.port-chip.done { color: #45aaf2; border-color: #45aaf233; }
.port-chip.error { color: #e74c3c; border-color: #e74c3c33; }
.port-chip.timeout { color: #f39c12; border-color: #f39c1233; }
.port-chip.then { color: #2ecc71; border-color: #2ecc7133; }
.port-chip.else { color: #e67e22; border-color: #e67e2233; }

/* Help text */
.help-text {
  font-size: 9px;
  color: var(--text-dim);
  line-height: 1.6;
}
.help-text code {
  font-size: 9px;
  background: var(--bg);
  padding: 0 3px;
  border-radius: 2px;
  color: var(--accent);
}

/* Variables editor */
.var-row {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 4px;
}

.var-name {
  font-size: 10px;
  font-weight: 500;
  color: var(--accent);
  min-width: 60px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.var-input {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  padding: 2px 4px;
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 3px;
  outline: none;
  flex: 1;
  min-width: 0;
}
.var-input:focus { border-color: var(--accent); }

.var-del {
  font-size: 14px;
  background: none;
  border: none;
  color: var(--text-dim);
  cursor: pointer;
  padding: 0 2px;
  line-height: 1;
}
.var-del:hover { color: #e74c3c; }

.auto-tag {
  font-size: 8px;
  color: var(--text-dim);
  background: var(--bg);
  padding: 0 4px;
  border-radius: 3px;
  border: 1px solid var(--border);
  margin-left: auto;
}

.var-add-row {
  display: flex;
  gap: 4px;
  margin-top: 4px;
}

.var-add-btn {
  font-size: 14px;
  font-weight: 700;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--accent);
  cursor: pointer;
  border-radius: 3px;
  padding: 0 6px;
  line-height: 1;
}
.var-add-btn:hover { background: var(--bg-hover); }

/* Delete button */
.delete-btn {
  font-family: inherit;
  font-size: 11px;
  padding: 6px 12px;
  width: 100%;
  border: 1px solid #6b1a1a;
  border-radius: 4px;
  background: #3d0a0a;
  color: #e76f6f;
  cursor: pointer;
  transition: background 0.15s;
}
.delete-btn:hover { background: #5a1515; }

.node-type-title { margin-bottom: 4px; display: flex; align-items: center; }

/* Source data reference */
.source-node-id {
  font-weight: 400;
  color: var(--text-dim);
  margin-left: 4px;
  font-size: 9px;
  opacity: 0.7;
}

.source-data-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 0;
  font-size: 10px;
}

.type-chip {
  font-size: 8px;
  font-family: 'JetBrains Mono', monospace;
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text-dim);
  white-space: nowrap;
}

/* Mapping cards */
.mapping-card {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 6px 8px;
  margin-bottom: 6px;
}

.mapping-card-header {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 4px;
}

.mapping-card-name {
  font-size: 10px;
  font-weight: 600;
  color: var(--accent);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mapping-card-del {
  font-size: 14px;
  background: none;
  border: none;
  color: var(--text-dim);
  cursor: pointer;
  padding: 0 2px;
  line-height: 1;
  margin-left: auto;
}
.mapping-card-del:hover { color: #e74c3c; }

.mapping-card-input {
  width: 100%;
  margin-bottom: 4px;
}

.mapping-chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 3px;
}

.mapping-chip-arrow {
  font-size: 10px;
  color: var(--text-dim);
  margin-right: 1px;
}

.mapping-chip {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  color: var(--accent);
  cursor: pointer;
  transition: background 0.1s, border-color 0.1s;
}
.mapping-chip:hover {
  background: var(--bg-hover);
  border-color: var(--accent);
}

.mapping-add-row {
  display: flex;
  gap: 4px;
  margin-top: 4px;
}

.mapping-select {
  flex: 1;
  min-width: 0;
}
</style>
