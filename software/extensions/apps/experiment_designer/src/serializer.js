/**
 * YAML serializer/deserializer for the new experiment framework.
 *
 * Export: Converts the node graph into the YAML format accepted by
 *         core.utils.experiments.parser.ExperimentParser.
 *
 * The parser supports two formats:
 *   1. Sequential shorthand — flat action list with implicit chaining
 *   2. Canonical — explicit triggers and transitions
 *
 * The designer exports in CANONICAL format when the graph has branching,
 * and SEQUENTIAL shorthand when the graph is a simple linear chain.
 *
 * Import: Parses both formats back into graph nodes + edges.
 */
import { getAllActions, INTERNAL_ACTIONS, createDefaultParams, getTransitionPorts, getAllRequirements, isRequirementType, getAllGuards, isGuardType, getSummary, getParamLines } from './actionRegistry.js'

// Detect simple comparisons in condition test expressions for import
// Matches: ${expr op expr}, ${expr} op ${expr}, or bare A op B
const COMPARE_OPS = ['<=', '>=', '!=', '==', '<', '>']
function parseCompareExpr(test) {
  if (!test || typeof test !== 'string') return null
  // Strip outer ${...} wrapper
  let inner = test.trim()
  if (inner.startsWith('${') && inner.endsWith('}')) inner = inner.slice(2, -1).trim()
  // Try to match: A op B where op is a comparison operator
  for (const op of COMPARE_OPS) {
    const idx = inner.indexOf(` ${op} `)
    if (idx > 0) {
      const a = inner.slice(0, idx).trim()
      const b = inner.slice(idx + op.length + 2).trim()
      // Only upgrade if both sides are "simple" (no nested operators)
      if (a && b && !COMPARE_OPS.some(o => a.includes(` ${o} `) || b.includes(` ${o} `))) {
        return { a, op, b }
      }
    }
  }
  return null
}

// ── YAML Export ────────────────────────────────────────────────────────────

/**
 * Convert graph (nodes + edges) to YAML string.
 */
export function toYaml(nodes, edges, meta) {
  const lines = []

  // Header
  lines.push(`id: ${yamlStr(meta.id)}`)
  lines.push(`description: ${yamlStr(meta.description)}`)
  if (meta.timeout != null) lines.push(`timeout: ${meta.timeout}`)

  // Variables
  if (meta.variables && Object.keys(meta.variables).length > 0) {
    lines.push('')
    lines.push('variables:')
    for (const [name, value] of Object.entries(meta.variables)) {
      lines.push(`  ${name}: ${yamlValue(value)}`)
    }
  }

  // Requirements
  const requirementNodes = nodes.filter(n => n.isRequirement)
  if (requirementNodes.length > 0) {
    lines.push('')
    lines.push('requirements:')
    const allReqs = getAllRequirements()
    for (const reqNode of requirementNodes) {
      const reqDef = allReqs[reqNode.type]
      lines.push(`  - type: ${reqNode.type}`)
      if (reqNode.id) lines.push(`    id: ${reqNode.id}`)
      if (reqDef && reqDef.params && reqNode.params) {
        for (const [key, pDef] of Object.entries(reqDef.params)) {
          const val = reqNode.params[key]
          if (val === null || val === undefined) continue
          if (pDef.default !== undefined && val === pDef.default) continue
          lines.push(`    ${key}: ${yamlValue(val)}`)
        }
      }
    }
  }

  // Guards
  const guardNodes = nodes.filter(n => n.isGuard)
  if (guardNodes.length > 0) {
    lines.push('')
    lines.push('guards:')
    const allGuards = getAllGuards()
    for (const guardNode of guardNodes) {
      const guardDef = allGuards[guardNode.type]
      lines.push(`  - type: ${guardNode.type}`)
      if (guardNode.id) lines.push(`    id: ${guardNode.id}`)
      if (guardDef && guardDef.params && guardNode.params) {
        for (const [key, pDef] of Object.entries(guardDef.params)) {
          const val = guardNode.params[key]
          if (val === null || val === undefined) continue
          if (pDef.default !== undefined && val === pDef.default) continue
          lines.push(`    ${key}: ${yamlValue(val)}`)
        }
      }
    }
  }

  // Setup/cleanup groups: serialize children as setup_actions/cleanup_actions
  const PHASE_TYPES = { setup_group: 'setup_actions', cleanup_group: 'cleanup_actions' }
  for (const [phaseType, yamlKey] of Object.entries(PHASE_TYPES)) {
    const groupNode = nodes.find(n => n.type === phaseType && !n.parentId)
    if (!groupNode) continue

    // Get children (excluding entry/exit), ordered by walking from entry
    const entryId = `__entry_${groupNode.id}__`
    const children = nodes.filter(n =>
      n.parentId === groupNode.id &&
      n.type !== '__entry__' && n.type !== '__exit__'
    )
    if (children.length === 0) continue

    // Build local outgoing map for ordering
    const localOut = {}
    for (const edge of edges) {
      if (!localOut[edge.from]) localOut[edge.from] = []
      localOut[edge.from].push(edge)
    }

    // Walk from entry to get ordered children
    const ordered = []
    const visited = new Set()
    let current = (localOut[entryId] || []).find(e => e.fromPort === 'done')?.to
    while (current) {
      if (visited.has(current)) break
      visited.add(current)
      const child = children.find(n => n.id === current)
      if (!child) break
      ordered.push(child)
      const next = (localOut[current] || []).find(e => e.fromPort === 'done')
      current = next ? next.to : null
    }
    // Add any unconnected children
    for (const child of children) {
      if (!visited.has(child.id)) ordered.push(child)
    }

    lines.push('')
    lines.push(`${yamlKey}:`)
    for (const child of ordered) {
      lines.push(...serializeAction(child, 2))
    }
  }

  lines.push('')

  // Build adjacency from all edges
  const outgoing = {}  // nodeId → [{ port, target }]
  const incoming = {}  // nodeId → [{ sourceId, port }]
  for (const edge of edges) {
    if (!outgoing[edge.from]) outgoing[edge.from] = []
    outgoing[edge.from].push({ port: edge.fromPort, target: edge.to, mapping: edge.mapping })
    if (!incoming[edge.to]) incoming[edge.to] = []
    incoming[edge.to].push({ sourceId: edge.from, port: edge.fromPort })
  }

  // Collect top-level action nodes (not start/stop, not children, not entry/exit, not requirements, not phase groups)
  const topLevelActions = nodes.filter(n =>
    n.type !== '__start__' && n.type !== '__stop__' &&
    n.type !== '__entry__' && n.type !== '__exit__' &&
    n.type !== 'setup_group' && n.type !== 'cleanup_group' &&
    !n.parentId && !n.isRequirement && !n.isGuard
  )

  if (topLevelActions.length === 0) {
    lines.push('actions: []')
    return lines.join('\n')
  }

  // Any containers in the graph → always canonical
  const hasContainers = topLevelActions.some(n => n.width != null)
  const isLinear = !hasContainers && checkLinearChain(nodes, edges, outgoing, incoming)

  if (isLinear) {
    return lines.join('\n') + '\n' + exportSequential(nodes, edges, outgoing, incoming)
  } else {
    return lines.join('\n') + '\n' + exportCanonical(nodes, edges, outgoing, incoming)
  }
}

/**
 * Check if the graph is a simple linear chain: start → a → b → c → stop
 * with only 'done' port transitions and no fan-out/fan-in.
 */
function checkLinearChain(nodes, edges, outgoing, incoming) {
  const startNode = nodes.find(n => n.type === '__start__')
  if (!startNode) return false

  const startEdges = outgoing[startNode.id] || []
  if (startEdges.length !== 1) return false

  // Any top-level node with a non-transition trigger (time, tick, event, periodic)
  // means the graph is not a simple linear chain
  const topLevelActions = nodes.filter(n =>
    n.type !== '__start__' && n.type !== '__stop__' &&
    n.type !== '__entry__' && n.type !== '__exit__' &&
    n.type !== 'setup_group' && n.type !== 'cleanup_group' &&
    !n.parentId && !n.isRequirement && !n.isGuard
  )
  if (topLevelActions.some(n => n.trigger && n.trigger.type !== 'transition' && n.trigger.type !== 'immediate')) {
    return false
  }

  // Walk the chain
  let current = startEdges[0].target
  const visited = new Set()
  while (current) {
    if (visited.has(current)) return false
    visited.add(current)

    const node = nodes.find(n => n.id === current)
    if (!node) return false
    if (node.type === '__stop__') break

    // Must have exactly 0 or 1 incoming (from previous or start)
    const inEdges = (incoming[current] || []).filter(e => e.sourceId !== '__start__')
    if (inEdges.length > 1) return false

    // Must have exactly 0 or 1 outgoing on 'done' port
    const outEdges = (outgoing[current] || []).filter(e => e.port === 'done')
    if (outEdges.length > 1) return false

    // Must not have error/timeout transitions
    const otherOutEdges = (outgoing[current] || []).filter(e => e.port !== 'done')
    if (otherOutEdges.length > 0) return false

    current = outEdges.length > 0 ? outEdges[0].target : null
  }

  // All top-level action nodes must be part of the chain
  for (const node of topLevelActions) {
    if (!visited.has(node.id)) return false
  }

  return true
}

/**
 * Export in sequential shorthand format.
 * Actions as a flat list — the parser auto-chains them.
 */
function exportSequential(nodes, edges, outgoing, incoming) {
  const lines = []
  const startNode = nodes.find(n => n.type === '__start__')

  // Walk the chain from start
  const ordered = []
  let current = (outgoing[startNode.id] || [])[0]?.target
  const visited = new Set()

  while (current) {
    if (visited.has(current)) break
    visited.add(current)
    const node = nodes.find(n => n.id === current)
    if (!node || node.type === '__stop__') break
    ordered.push(node)
    const out = (outgoing[current] || []).filter(e => e.port === 'done')
    current = out.length > 0 ? out[0].target : null
  }

  lines.push('actions:')
  for (const node of ordered) {
    lines.push(...serializeAction(node, 2))
  }

  return lines.join('\n')
}

/**
 * Export in canonical format with explicit triggers and transitions.
 */
function exportCanonical(nodes, edges, outgoing, incoming) {
  const lines = []
  const startNode = nodes.find(n => n.type === '__start__')
  // Top-level action nodes only (not children, not entry/exit, not requirements, not phase groups)
  const actionNodes = nodes.filter(n =>
    n.type !== '__start__' && n.type !== '__stop__' &&
    n.type !== '__entry__' && n.type !== '__exit__' &&
    n.type !== 'setup_group' && n.type !== 'cleanup_group' &&
    !n.parentId && !n.isRequirement && !n.isGuard
  )

  // Topological sort via BFS from start
  const ordered = []
  const visited = new Set()
  const queue = []

  if (startNode && outgoing[startNode.id]) {
    for (const conn of outgoing[startNode.id]) {
      if (!visited.has(conn.target)) {
        queue.push(conn.target)
        visited.add(conn.target)
      }
    }
  }

  while (queue.length > 0) {
    const nodeId = queue.shift()
    const node = nodes.find(n => n.id === nodeId)
    if (node && node.type !== '__stop__' && node.type !== '__entry__' && node.type !== '__exit__' && !node.parentId) {
      ordered.push(node)
    }
    if (outgoing[nodeId]) {
      for (const conn of outgoing[nodeId]) {
        if (!visited.has(conn.target)) {
          visited.add(conn.target)
          queue.push(conn.target)
        }
      }
    }
  }

  // Add any orphaned top-level nodes
  for (const node of actionNodes) {
    if (!visited.has(node.id)) {
      ordered.push(node)
    }
  }

  // Collect __stop__ nodes that have incoming edges (need to become real stop actions)
  const stopNodes = nodes.filter(n => n.type === '__stop__')
  const reachableStopIds = new Set()
  for (const edge of edges) {
    const target = nodes.find(n => n.id === edge.to)
    if (target && target.type === '__stop__') reachableStopIds.add(target.id)
  }

  lines.push('actions:')

  for (const node of ordered) {
    lines.push(...serializeCanonicalAction(node, nodes, outgoing, incoming, 2, reachableStopIds))
  }

  // Emit stop actions for __stop__ nodes that have incoming edges
  for (const stopNode of stopNodes) {
    if (!reachableStopIds.has(stopNode.id)) continue
    const pad = '  '
    lines.push(`${pad}- type: stop`)
    lines.push(`${pad}  id: ${stopNode.id}`)
    lines.push(`${pad}  trigger: transition`)
    const status = stopNode.params?.status || 'finished'
    const message = stopNode.params?.message || ''
    if (status !== 'finished') lines.push(`${pad}  status: ${yamlValue(status)}`)
    if (message) lines.push(`${pad}  message: ${yamlValue(message)}`)
  }

  return lines.join('\n')
}

/**
 * Serialize a single action in canonical format, including nested children for containers.
 */
function serializeCanonicalAction(node, allNodes, outgoing, incoming, indent, reachableStopIds = new Set()) {
  const lines = []
  const pad = ' '.repeat(indent)

  // Designer-only 'compare' → serialize as 'condition' with generated test
  const isCompare = node.type === 'compare'
  const emitType = isCompare ? 'condition' : node.type

  const def = getAllActions()[node.type] || INTERNAL_ACTIONS[node.type]
  if (!def) return lines

  lines.push(`${pad}- type: ${emitType}`)
  lines.push(`${pad}  id: ${node.id}`)

  // Trigger
  const inEdges = incoming[node.id] || []
  const fromStart = inEdges.some(e => e.sourceId === '__start__')
  const fromEntry = inEdges.some(e => {
    const src = allNodes.find(n => n.id === e.sourceId)
    return src && src.type === '__entry__'
  })
  const fromActions = inEdges.filter(e => {
    const src = allNodes.find(n => n.id === e.sourceId)
    return e.sourceId !== '__start__' && (!src || src.type !== '__entry__')
  })

  if (node.trigger) {
    lines.push(`${pad}  trigger: ${serializeTrigger(node.trigger)}`)
  } else if (fromStart || fromEntry) {
    lines.push(`${pad}  trigger: immediate`)
  } else if (fromActions.length > 0) {
    lines.push(`${pad}  trigger: transition`)
  }

  // Wait delays
  if (node.wait_before) lines.push(`${pad}  wait_before: ${node.wait_before}`)
  if (node.wait_after) lines.push(`${pad}  wait_after: ${node.wait_after}`)
  if (node.message_before) lines.push(`${pad}  message_before: "${node.message_before.replace(/"/g, '\\"')}"`)
  if (node.message_after) lines.push(`${pad}  message_after: "${node.message_after.replace(/"/g, '\\"')}"`)

  // Parameters
  if (isCompare) {
    // Emit as condition test expression
    const a = node.params.value_a || '?'
    const op = node.params.operator || '<'
    const b = node.params.value_b || '?'
    // Wrap each side in ${} only if it looks like a reference (contains dot or $)
    const wrapExpr = v => (/[.$]/.test(v) && !v.startsWith('${')) ? `\${${v}}` : v
    const exprA = wrapExpr(a)
    const exprB = wrapExpr(b)
    lines.push(`${pad}  test: "\${${exprA} ${op} ${exprB}}"`)
  } else if (def.params && node.params) {
    for (const [key, pDef] of Object.entries(def.params)) {
      const val = node.params[key]
      if (val === null || val === undefined) continue
      if (!pDef.required && isDefault(val, pDef.default)) continue
      lines.push(`${pad}  ${key}: ${yamlValue(val)}`)
    }
  }

  // Container: serialize nested children under 'actions:'
  if (def.isContainer && node.width != null) {
    const children = allNodes.filter(n =>
      n.parentId === node.id &&
      n.type !== '__entry__' && n.type !== '__exit__'
    )
    if (children.length > 0) {
      lines.push(`${pad}  actions:`)
      // Get the entry node for this container
      const entryId = `__entry_${node.id}__`
      // Order children: BFS from entry
      const childOrdered = []
      const childVisited = new Set()
      const childQueue = []

      if (outgoing[entryId]) {
        for (const conn of outgoing[entryId]) {
          if (!childVisited.has(conn.target)) {
            childQueue.push(conn.target)
            childVisited.add(conn.target)
          }
        }
      }

      while (childQueue.length > 0) {
        const childId = childQueue.shift()
        const child = allNodes.find(n => n.id === childId)
        if (child && child.type !== '__exit__' && child.type !== '__entry__' && child.parentId === node.id) {
          childOrdered.push(child)
        }
        if (outgoing[childId]) {
          for (const conn of outgoing[childId]) {
            if (!childVisited.has(conn.target)) {
              childVisited.add(conn.target)
              childQueue.push(conn.target)
            }
          }
        }
      }

      // Add orphaned children
      for (const child of children) {
        if (!childVisited.has(child.id)) {
          childOrdered.push(child)
        }
      }

      for (const child of childOrdered) {
        lines.push(...serializeCanonicalAction(child, allNodes, outgoing, incoming, indent + 4, reachableStopIds))
      }
    }
  }

  // Transitions (outgoing edges from this node)
  // Include edges to __stop__ nodes (they become real stop actions), exclude __exit__
  const nodeOutEdges = outgoing[node.id] || []
  const nonTerminalEdges = nodeOutEdges.filter(e => {
    const targetNode = allNodes.find(n => n.id === e.target)
    if (!targetNode) return false
    if (targetNode.type === '__exit__') return false
    if (targetNode.type === '__stop__') return reachableStopIds.has(targetNode.id)
    return true
  })

  if (nonTerminalEdges.length > 0) {
    lines.push(`${pad}  transitions:`)
    const byPort = {}
    for (const edge of nonTerminalEdges) {
      if (!byPort[edge.port]) byPort[edge.port] = []
      byPort[edge.port].push(edge)
    }
    for (const [port, portEdges] of Object.entries(byPort)) {
      if (portEdges.length === 1 && !portEdges[0].mapping) {
        lines.push(`${pad}    ${port}: ${portEdges[0].target}`)
      } else if (portEdges.length === 1 && portEdges[0].mapping) {
        lines.push(`${pad}    ${port}:`)
        lines.push(`${pad}      target: ${portEdges[0].target}`)
        lines.push(`${pad}      data:`)
        for (const [k, v] of Object.entries(portEdges[0].mapping)) {
          lines.push(`${pad}        ${k}: ${yamlValue(v)}`)
        }
      } else {
        lines.push(`${pad}    ${port}:`)
        for (const edge of portEdges) {
          if (!edge.mapping) {
            lines.push(`${pad}      - ${edge.target}`)
          } else {
            lines.push(`${pad}      - target: ${edge.target}`)
            lines.push(`${pad}        data:`)
            for (const [k, v] of Object.entries(edge.mapping)) {
              lines.push(`${pad}          ${k}: ${yamlValue(v)}`)
            }
          }
        }
      }
    }
  }

  return lines
}

/**
 * Serialize a single action for sequential format.
 * (Sequential format should not contain containers, but handle gracefully.)
 */
function serializeAction(node, indent) {
  const lines = []
  const pad = ' '.repeat(indent)
  const isCompare = node.type === 'compare'
  const emitType = isCompare ? 'condition' : node.type
  const def = getAllActions()[node.type] || INTERNAL_ACTIONS[node.type]
  if (!def) return lines

  lines.push(`${pad}- type: ${emitType}`)

  // ID (always include for clarity)
  lines.push(`${pad}  id: ${node.id}`)

  // Wait delays
  if (node.wait_before) lines.push(`${pad}  wait_before: ${node.wait_before}`)
  if (node.wait_after) lines.push(`${pad}  wait_after: ${node.wait_after}`)
  if (node.message_before) lines.push(`${pad}  message_before: "${node.message_before.replace(/"/g, '\\"')}"`)
  if (node.message_after) lines.push(`${pad}  message_after: "${node.message_after.replace(/"/g, '\\"')}"`)

  // Parameters
  if (isCompare) {
    const a = node.params.value_a || '?'
    const op = node.params.operator || '<'
    const b = node.params.value_b || '?'
    const wrapExpr = v => (/[.$]/.test(v) && !v.startsWith('${')) ? `\${${v}}` : v
    lines.push(`${pad}  test: "\${${wrapExpr(a)} ${op} ${wrapExpr(b)}}"`)
  } else if (def.params && node.params) {
    for (const [key, pDef] of Object.entries(def.params)) {
      const val = node.params[key]
      if (val === null || val === undefined) continue
      if (!pDef.required && isDefault(val, pDef.default)) continue
      lines.push(`${pad}  ${key}: ${yamlValue(val)}`)
    }
  }

  return lines
}

function serializeTrigger(trigger) {
  if (!trigger) return 'immediate'
  const t = trigger.type || trigger
  if (typeof t === 'string') {
    if (t === 'immediate') return 'immediate'
    if (t === 'transition') return 'transition'
    if (t === 'tick' && trigger.tick != null) return `"tick:${trigger.tick}"`
    if (t === 'time' && trigger.time != null) return `"time:${trigger.time}"`
    if (t === 'event' && trigger.event) return `"event:${trigger.event}"`
    if (t === 'periodic' && trigger.period != null) {
      const unit = trigger.period_unit === 'ticks' ? 'ticks' : 'seconds'
      return `"periodic:${trigger.period}:${unit}"`
    }
    return t
  }
  return 'immediate'
}

function isDefault(val, def) {
  if (def === null || def === undefined) return val === null || val === undefined
  if (Array.isArray(val) && Array.isArray(def)) {
    return JSON.stringify(val) === JSON.stringify(def)
  }
  return val === def
}

function yamlStr(s) {
  if (s === null || s === undefined) return '""'
  s = String(s)
  if (s === '') return '""'
  if (/[:#\[\]{}&*!|>'"%@`]/.test(s) || s.includes('\n') || s !== s.trim()) {
    return `"${s.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`
  }
  return s
}

function yamlValue(val) {
  if (val === null || val === undefined) return 'null'
  if (typeof val === 'boolean') return val ? 'true' : 'false'
  if (typeof val === 'number') return String(val)
  if (typeof val === 'string') return yamlStr(val)
  if (Array.isArray(val)) {
    return `[${val.map(v => yamlValue(v)).join(', ')}]`
  }
  if (typeof val === 'object') {
    const entries = Object.entries(val).map(([k, v]) => `${k}: ${yamlValue(v)}`)
    return `{${entries.join(', ')}}`
  }
  return String(val)
}

// ── YAML Import ────────────────────────────────────────────────────────────

/**
 * Simple recursive YAML parser.
 * Handles: scalars, maps, lists, nested structures (indent-based).
 */
function parseYamlDoc(text) {
  const lines = text.split('\n')
  let pos = 0

  function lineIndent(idx) {
    if (idx >= lines.length) return -1
    const m = lines[idx].match(/^( *)/)
    return m ? m[1].length : 0
  }

  function skipEmpty() {
    while (pos < lines.length && (lines[pos].trim() === '' || lines[pos].trim().startsWith('#'))) pos++
  }

  function parseMapping(indent) {
    const obj = {}
    while (pos < lines.length) {
      skipEmpty()
      if (pos >= lines.length) break
      const li = lineIndent(pos)
      if (li < indent) break
      if (li > indent) { pos++; continue }

      const trimmed = lines[pos].trim()
      if (trimmed.startsWith('- ')) break

      const m = trimmed.match(/^([\w][\w.-]*):\s*(.*)$/)
      if (!m) { pos++; continue }

      const key = m[1]
      const rest = m[2]
      pos++

      if (rest && rest !== '|' && rest !== '>') {
        obj[key] = parseScalar(rest)
      } else {
        skipEmpty()
        if (pos >= lines.length || lineIndent(pos) <= indent) {
          obj[key] = rest === '|' || rest === '>' ? '' : null
        } else {
          const childTrimmed = lines[pos].trim()
          if (childTrimmed.startsWith('- ')) {
            obj[key] = parseListAt(lineIndent(pos))
          } else {
            obj[key] = parseMapping(lineIndent(pos))
          }
        }
      }
    }
    return obj
  }

  function parseListAt(indent) {
    const items = []
    while (pos < lines.length) {
      skipEmpty()
      if (pos >= lines.length) break
      const li = lineIndent(pos)
      if (li < indent) break
      if (li > indent) { pos++; continue }

      const trimmed = lines[pos].trim()
      if (!trimmed.startsWith('- ')) break

      const afterDash = trimmed.slice(2).trim()
      pos++

      if (!afterDash) {
        // Block list item
        skipEmpty()
        if (pos < lines.length && lineIndent(pos) > indent) {
          items.push(parseMapping(lineIndent(pos)))
        } else {
          items.push(null)
        }
      } else if (afterDash.match(/^[\w][\w.-]*:\s*/)) {
        // Map item starting on dash line: "- key: value"
        const item = {}
        const firstM = afterDash.match(/^([\w][\w.-]*):\s*(.*)$/)
        if (firstM) {
          const fKey = firstM[1]
          const fRest = firstM[2]
          if (fRest && fRest !== '|' && fRest !== '>') {
            item[fKey] = parseScalar(fRest)
          } else {
            skipEmpty()
            if (pos < lines.length && lineIndent(pos) > indent + 2) {
              const childTrimmed = lines[pos].trim()
              if (childTrimmed.startsWith('- ')) {
                item[fKey] = parseListAt(lineIndent(pos))
              } else {
                item[fKey] = parseMapping(lineIndent(pos))
              }
            } else {
              item[fKey] = null
            }
          }
        }
        // Read remaining map keys for this item (at indent+2)
        const itemIndent = indent + 2
        while (pos < lines.length) {
          skipEmpty()
          if (pos >= lines.length) break
          const itemLi = lineIndent(pos)
          if (itemLi < itemIndent) break
          if (itemLi > itemIndent) { pos++; continue }

          const subTrimmed = lines[pos].trim()
          if (subTrimmed.startsWith('- ')) break

          const subM = subTrimmed.match(/^([\w][\w.-]*):\s*(.*)$/)
          if (!subM) { pos++; continue }

          const subKey = subM[1]
          const subRest = subM[2]
          pos++

          if (subRest && subRest !== '|' && subRest !== '>') {
            item[subKey] = parseScalar(subRest)
          } else {
            skipEmpty()
            if (pos < lines.length && lineIndent(pos) > itemIndent) {
              const childTrimmed = lines[pos].trim()
              if (childTrimmed.startsWith('- ')) {
                item[subKey] = parseListAt(lineIndent(pos))
              } else {
                item[subKey] = parseMapping(lineIndent(pos))
              }
            } else {
              item[subKey] = null
            }
          }
        }
        items.push(item)
      } else {
        items.push(parseScalar(afterDash))
      }
    }
    return items
  }

  skipEmpty()
  return parseMapping(0)
}

function parseScalar(text) {
  if (text === 'null' || text === '~') return null
  if (text === 'true') return true
  if (text === 'false') return false
  if ((text.startsWith('"') && text.endsWith('"')) ||
      (text.startsWith("'") && text.endsWith("'"))) {
    return text.slice(1, -1)
  }
  if (text.startsWith('[') && text.endsWith(']')) {
    const inner = text.slice(1, -1).trim()
    if (inner === '') return []
    return inner.split(',').map(s => parseScalar(s.trim()))
  }
  if (text.startsWith('{') && text.endsWith('}')) {
    const inner = text.slice(1, -1).trim()
    if (inner === '') return {}
    const obj = {}
    for (const pair of inner.split(',')) {
      const [k, ...rest] = pair.split(':')
      if (k) obj[k.trim()] = parseScalar(rest.join(':').trim())
    }
    return obj
  }
  const num = Number(text)
  if (!isNaN(num) && text !== '') return num
  return text
}

/**
 * Parse YAML string into graph nodes and edges.
 * Returns { nodes, edges, meta }.
 */
export function fromYaml(yamlText) {
  let doc = parseYamlDoc(yamlText)

  // Unwrap optional "experiment:" top-level key
  if (doc.experiment && typeof doc.experiment === 'object' && !Array.isArray(doc.experiment)) {
    doc = doc.experiment
  }

  const meta = {
    id: String(doc.id ?? ''),
    description: String(doc.description ?? ''),
    timeout: doc.timeout || null,
    variables: (typeof doc.variables === 'object' && doc.variables && !Array.isArray(doc.variables)) ? doc.variables : {},
    events: [],
  }

  // Parse requirements: map (BILBO flat) or array (list format)
  const rawRequirements = []
  if (doc.requirements) {
    if (Array.isArray(doc.requirements)) {
      for (const item of doc.requirements) {
        if (typeof item === 'object') rawRequirements.push(item)
      }
    } else if (typeof doc.requirements === 'object') {
      for (const [key, value] of Object.entries(doc.requirements)) {
        rawRequirements.push({ _flatKey: key, _flatValue: value })
      }
    }
  }

  // Parse guards: array format
  const rawGuards = []
  if (doc.guards && Array.isArray(doc.guards)) {
    for (const item of doc.guards) {
      if (typeof item === 'object') rawGuards.push(item)
    }
  }

  const rawActions = Array.isArray(doc.actions) ? doc.actions : []
  const rawSetupActions = Array.isArray(doc.setup_actions) ? doc.setup_actions : []
  const rawCleanupActions = Array.isArray(doc.cleanup_actions) ? doc.cleanup_actions : []
  return buildGraph(rawActions, meta, rawRequirements, rawGuards, rawSetupActions, rawCleanupActions)
}

// ── Build graph from parsed actions ────────────────────────────────────────

// Layout constants
const GAP_Y = 60          // vertical gap between nodes
const INNER_PAD = 20      // padding inside container body (top/bottom)
const HEADER_H = 32
const PORTS_H = 28
const ENTRY_H = 30
const NODE_W = 160
const BASE_X = 300
const START_Y = 60
const START_GAP = 80      // gap between start node and first action

/**
 * Estimate node height based on params and wait bars.
 */
function estimateNodeHeight(type, params, wait_before, wait_after, message_before, message_after) {
  let h = 28   // header
  if (message_before) h += 18
  if (wait_before) h += 18
  const summaryText = getSummary({ type, params }) || ''
  if (summaryText) {
    h += 20    // summary line
  } else {
    const lineCount = getParamLines({ type, params }).length
    if (lineCount > 0) h += lineCount * 15 + 4
  }
  if (wait_after) h += 18
  if (message_after) h += 18
  h += 20 + 4   // port section + padding
  return h
}

function buildGraph(rawActions, meta, rawRequirements = [], rawGuards = [], rawSetupActions = [], rawCleanupActions = []) {
  const nodes = []
  const edges = []
  let counter = 0

  nodes.push({ id: '__start__', type: '__start__', x: BASE_X, y: START_Y, parentId: null })

  // ── Create requirement nodes ──────────────────────────────────────────
  const allReqs = getAllRequirements()
  let reqY = 60

  const flatKeyMap = {}
  for (const [type, def] of Object.entries(allReqs)) {
    if (def.yamlMapping) {
      const m = def.yamlMapping
      if (m.type === 'flag' || m.type === 'param') {
        flatKeyMap[m.key] = { type, mapping: m }
      }
    }
  }

  for (const raw of rawRequirements) {
    if (raw._flatKey) {
      const mapped = flatKeyMap[raw._flatKey]
      if (mapped) {
        counter++
        const nodeType = mapped.type
        const reqDef = allReqs[nodeType]
        const params = {}
        if (reqDef?.params) {
          for (const [k, pDef] of Object.entries(reqDef.params)) {
            params[k] = pDef.default !== undefined ? pDef.default : null
          }
        }
        if (mapped.mapping.type === 'param' && mapped.mapping.param) {
          params[mapped.mapping.param] = raw._flatValue
        }
        nodes.push({
          id: `${nodeType}_${counter}`, type: nodeType,
          x: 60, y: reqY, parentId: null, params,
          isRequirement: true, _summaryText: '', _paramLineCount: 0,
        })
        reqY += 60
      }
    } else if (raw.state != null) {
      const srType = Object.keys(allReqs).find(t => allReqs[t].yamlMapping?.type === 'state_range')
      if (srType) {
        counter++
        const reqDef = allReqs[srType]
        const params = {}
        if (reqDef?.params) {
          for (const [k, pDef] of Object.entries(reqDef.params)) {
            params[k] = pDef.default !== undefined ? pDef.default : null
          }
        }
        params.state = raw.state
        if (raw.min != null) params.min = raw.min
        if (raw.max != null) params.max = raw.max
        nodes.push({
          id: `${srType}_${counter}`, type: srType,
          x: 60, y: reqY, parentId: null, params,
          isRequirement: true, _summaryText: '', _paramLineCount: 0,
        })
        reqY += 60
      }
    } else if (raw.type) {
      const nodeType = raw.type.startsWith('require_') ? raw.type : `require_${raw.type}`
      counter++
      const reqDef = allReqs[nodeType]
      const params = {}
      if (reqDef?.params) {
        for (const [k, pDef] of Object.entries(reqDef.params)) {
          params[k] = raw[k] !== undefined ? raw[k] : (pDef.default !== undefined ? pDef.default : null)
        }
      }
      nodes.push({
        id: raw.id || `${nodeType}_${counter}`, type: nodeType,
        x: 60, y: reqY, parentId: null, params,
        isRequirement: true, _summaryText: '', _paramLineCount: 0,
      })
      reqY += 60
    }
  }

  // ── Create guard nodes ────────────────────────────────────────────────
  const allGuards = getAllGuards()
  let guardY = reqY  // continue below requirement nodes

  for (const raw of rawGuards) {
    if (!raw.type) continue
    const nodeType = raw.type
    const guardDef = allGuards[nodeType]
    counter++
    const params = {}
    if (guardDef?.params) {
      for (const [k, pDef] of Object.entries(guardDef.params)) {
        params[k] = raw[k] !== undefined ? raw[k] : (pDef.default !== undefined ? pDef.default : null)
      }
    }
    nodes.push({
      id: raw.id || `${nodeType}_${counter}`, type: nodeType,
      x: 60, y: guardY, parentId: null, params,
      isGuard: true, _summaryText: '', _paramLineCount: 0,
    })
    guardY += 60
  }

  // ── Canonical detection (recursive) ───────────────────────────────────
  function hasCanonicalMarkers(actions) {
    for (const a of actions) {
      if (a.trigger || a.transitions) return true
      const sub = a.actions || a.sub_actions || []
      if (sub.length > 0 && hasCanonicalMarkers(sub)) return true
    }
    return false
  }
  const isCanonical = hasCanonicalMarkers(rawActions)

  // ── Add actions recursively ───────────────────────────────────────────
  /**
   * Returns { ids: string[], totalHeight: number }
   */
  function addActions(rawList, parentId, baseX, baseY) {
    const createdIds = []
    let y = baseY

    for (let idx = 0; idx < rawList.length; idx++) {
      const raw = rawList[idx]

      // Compare upgrade
      if (raw.type === 'condition' && raw.test) {
        const cm = parseCompareExpr(raw.test)
        if (cm) {
          raw.type = 'compare'
          raw.value_a = cm.a
          raw.operator = cm.op
          raw.value_b = cm.b
          delete raw.test
        }
      }

      const def = getAllActions()[raw.type] || INTERNAL_ACTIONS[raw.type]
      if (!def) continue

      counter++
      const nodeId = raw.id || `${raw.type}_${counter}`

      // Extract params — only skip structural YAML keys, not action param names
      const structural = new Set([
        'type', 'id', 'trigger', 'transitions', 'actions', 'sub_actions',
        'then', 'else', 'params', 'wait_before', 'wait_after',
        'message_before', 'message_after',
      ])
      const params = raw.params ? { ...raw.params } : {}
      for (const [k, v] of Object.entries(raw)) {
        if (structural.has(k)) continue
        if (def.params && k in def.params) {
          params[k] = v
        } else if (!def.params) {
          params[k] = v
        }
      }
      if (def.params) {
        for (const [k, pDef] of Object.entries(def.params)) {
          if (!(k in params)) {
            params[k] = pDef.default !== undefined ? pDef.default : null
          }
        }
      }

      const outPorts = getTransitionPorts(raw.type)
      const summaryText = getSummary({ type: raw.type, params }) || ''
      const paramLineCount = summaryText ? 0 : getParamLines({ type: raw.type, params }).length

      if (def.isContainer) {
        const containerW = Math.max(def.defaultWidth || 240, NODE_W + 120)

        const node = {
          id: nodeId, type: raw.type, x: baseX, y,
          parentId: parentId || null, params,
          trigger: parseTriggerValue(raw.trigger),
          wait_before: raw.wait_before || null,
          wait_after: raw.wait_after || null,
          message_before: raw.message_before || null,
          message_after: raw.message_after || null,
          _summaryText: summaryText, _paramLineCount: paramLineCount,
          _outPorts: outPorts,
          width: containerW, height: 300,
        }
        nodes.push(node)

        // Entry node
        const entryId = `__entry_${nodeId}__`
        const entryX = baseX + (containerW - 80) / 2
        const entryY = y + HEADER_H + INNER_PAD
        nodes.push({
          id: entryId, type: '__entry__',
          x: entryX, y: entryY,
          parentId: nodeId, _outPorts: ['done'],
        })

        // Children
        const subActions = raw.actions || raw.sub_actions || []
        const childBaseX = baseX + (containerW - NODE_W) / 2
        const childBaseY = entryY + ENTRY_H + GAP_Y
        let childResult = { ids: [], totalHeight: 0 }
        if (subActions.length > 0) {
          childResult = addActions(subActions, nodeId, childBaseX, childBaseY)
        }

        // Exit node
        const exitId = `__exit_${nodeId}__`
        const exitY = childResult.totalHeight > 0
          ? childBaseY + childResult.totalHeight + GAP_Y
          : entryY + ENTRY_H + GAP_Y
        nodes.push({
          id: exitId, type: '__exit__',
          x: entryX, y: exitY,
          parentId: nodeId, _outPorts: [],
        })

        // Size container to fit content
        node.height = Math.max(200, exitY + ENTRY_H + INNER_PAD + PORTS_H - y)

        // Wire children
        if (childResult.ids.length > 0) {
          if (isCanonical) {
            // Process canonical triggers + transitions for each child
            for (let j = 0; j < subActions.length; j++) {
              const childRaw = subActions[j]
              const childNodeId = childRaw.id || childResult.ids[j]
              if (!childNodeId) continue

              const trigger = childRaw.trigger
              if (trigger === 'immediate' || (!trigger && j === 0) ||
                  (typeof trigger === 'object' && trigger?.type === 'immediate')) {
                edges.push({
                  id: `edge_${entryId}_done_${childNodeId}`,
                  from: entryId, fromPort: 'done', to: childNodeId, mapping: null,
                })
              }

              if (childRaw.transitions && typeof childRaw.transitions === 'object') {
                for (const [port, target] of Object.entries(childRaw.transitions)) {
                  const targets = Array.isArray(target) ? target : [target]
                  for (const t of targets) {
                    const targetId = typeof t === 'string' ? t : t?.target
                    const mapping = typeof t === 'object' ? t?.data || null : null
                    if (targetId && nodes.some(n => n.id === targetId)) {
                      edges.push({
                        id: `edge_${childNodeId}_${port}_${targetId}`,
                        from: childNodeId, fromPort: port, to: targetId, mapping,
                      })
                    }
                  }
                }
              }
            }
            // Connect children with no outgoing → exit
            const childWithOutgoing = new Set(
              edges.filter(e => childResult.ids.includes(e.from)).map(e => e.from)
            )
            for (const childId of childResult.ids) {
              if (!childWithOutgoing.has(childId)) {
                const cn = nodes.find(n => n.id === childId)
                if (cn && (cn._outPorts || ['done']).length > 0) {
                  edges.push({
                    id: `edge_${childId}_done_${exitId}`,
                    from: childId, fromPort: 'done', to: exitId, mapping: null,
                  })
                }
              }
            }
          } else {
            // Sequential: entry → first, chain, last → exit
            edges.push({
              id: `edge_${entryId}_done_${childResult.ids[0]}`,
              from: entryId, fromPort: 'done', to: childResult.ids[0], mapping: null,
            })
            for (let j = 1; j < childResult.ids.length; j++) {
              edges.push({
                id: `edge_${childResult.ids[j-1]}_done_${childResult.ids[j]}`,
                from: childResult.ids[j-1], fromPort: 'done', to: childResult.ids[j], mapping: null,
              })
            }
            const lastId = childResult.ids[childResult.ids.length - 1]
            const lastNode = nodes.find(n => n.id === lastId)
            if (lastNode && (lastNode._outPorts || ['done']).length > 0) {
              edges.push({
                id: `edge_${lastId}_done_${exitId}`,
                from: lastId, fromPort: 'done', to: exitId, mapping: null,
              })
            }
          }
        }

        y += node.height + GAP_Y
        createdIds.push(nodeId)
      } else {
        // Regular action node
        const node = {
          id: nodeId, type: raw.type, x: baseX, y,
          parentId: parentId || null, params,
          trigger: parseTriggerValue(raw.trigger),
          wait_before: raw.wait_before || null,
          wait_after: raw.wait_after || null,
          message_before: raw.message_before || null,
          message_after: raw.message_after || null,
          _summaryText: summaryText, _paramLineCount: paramLineCount,
          _outPorts: outPorts,
        }
        nodes.push(node)

        const nodeH = estimateNodeHeight(raw.type, params, raw.wait_before, raw.wait_after, raw.message_before, raw.message_after)
        y += nodeH + GAP_Y
        createdIds.push(nodeId)
      }
    }

    const totalHeight = createdIds.length > 0 ? y - baseY - GAP_Y : 0
    return { ids: createdIds, totalHeight }
  }

  const firstActionY = START_Y + 40 + START_GAP  // 40 = start node height
  const topResult = addActions(rawActions, null, BASE_X, firstActionY)

  // Stop node — check if any imported action was type 'stop' and reuse its params
  const stopY = topResult.totalHeight > 0
    ? firstActionY + topResult.totalHeight + GAP_Y
    : firstActionY + 200

  // Find imported stop action nodes and convert them to __stop__ visual nodes
  const importedStopNodes = nodes.filter(n => n.type === 'stop')
  const stopIdMap = {}  // maps imported stop action ID → __stop__ node ID
  if (importedStopNodes.length > 0) {
    // Use the first imported stop as the visual __stop__ node
    const primary = importedStopNodes[0]
    stopIdMap[primary.id] = primary.id
    primary.type = '__stop__'
    primary._outPorts = undefined
    primary._summaryText = undefined
    primary._paramLineCount = undefined
    primary.trigger = null
    // Remove from topResult.ids so it's not treated as a regular action
    const idx = topResult.ids.indexOf(primary.id)
    if (idx >= 0) topResult.ids.splice(idx, 1)

    // Remove additional stop nodes and remap their edges
    for (let i = 1; i < importedStopNodes.length; i++) {
      const extra = importedStopNodes[i]
      stopIdMap[extra.id] = primary.id
      const extraIdx = topResult.ids.indexOf(extra.id)
      if (extraIdx >= 0) topResult.ids.splice(extraIdx, 1)
      // Remove the extra node
      const nodeIdx = nodes.indexOf(extra)
      if (nodeIdx >= 0) nodes.splice(nodeIdx, 1)
    }

    // Remap edges targeting extra stop nodes to the primary
    for (const edge of edges) {
      if (stopIdMap[edge.to] && edge.to !== stopIdMap[edge.to]) {
        edge.to = stopIdMap[edge.to]
        edge.id = `edge_${edge.from}_${edge.fromPort}_${edge.to}`
      }
    }
  } else {
    // No imported stop action — create a visual __stop__ node
    nodes.push({
      id: 'stop_1', type: '__stop__', x: BASE_X, y: stopY,
      parentId: null,
      params: { status: 'finished', message: '' },
    })
  }

  // ── Top-level edges ───────────────────────────────────────────────────
  if (isCanonical) {
    for (let i = 0; i < rawActions.length; i++) {
      const raw = rawActions[i]
      const nodeId = raw.id || topResult.ids[i]
      if (!nodeId) continue

      const trigger = raw.trigger
      if (trigger === 'immediate' || (typeof trigger === 'object' && trigger?.type === 'immediate')) {
        edges.push({
          id: `edge___start___done_${nodeId}`,
          from: '__start__', fromPort: 'done', to: nodeId, mapping: null,
        })
      }

      if (raw.transitions && typeof raw.transitions === 'object') {
        for (const [port, target] of Object.entries(raw.transitions)) {
          const targets = Array.isArray(target) ? target : [target]
          for (const t of targets) {
            const targetId = typeof t === 'string' ? t : t?.target
            const mapping = typeof t === 'object' ? t?.data || null : null
            if (targetId && nodes.some(n => n.id === targetId)) {
              edges.push({
                id: `edge_${nodeId}_${port}_${targetId}`,
                from: nodeId, fromPort: port, to: targetId, mapping,
              })
            }
          }
        }
      }
    }
  } else {
    for (let i = 0; i < topResult.ids.length; i++) {
      const nodeId = topResult.ids[i]
      if (i === 0) {
        edges.push({
          id: `edge___start___done_${nodeId}`,
          from: '__start__', fromPort: 'done', to: nodeId, mapping: null,
        })
      } else {
        edges.push({
          id: `edge_${topResult.ids[i-1]}_done_${nodeId}`,
          from: topResult.ids[i-1], fromPort: 'done', to: nodeId, mapping: null,
        })
      }
    }
  }

  // Connect last top-level actions with no outgoing → stop
  // Skip nodes with independent triggers (time, tick, event, periodic) — they run
  // on their own schedule and shouldn't auto-connect to stop.
  const stopNodeId = nodes.find(n => n.type === '__stop__')?.id
  if (stopNodeId) {
    const hasOutgoing = new Set(edges.map(e => e.from))
    for (const nodeId of topResult.ids) {
      if (!hasOutgoing.has(nodeId)) {
        const node = nodes.find(n => n.id === nodeId)
        if (!node) continue
        // Don't auto-connect nodes with non-transition triggers
        if (node.trigger && node.trigger.type !== 'transition' && node.trigger.type !== 'immediate') continue
        if ((node._outPorts || ['done']).length > 0) {
          edges.push({
            id: `edge_${nodeId}_done_${stopNodeId}`,
            from: nodeId, fromPort: 'done', to: stopNodeId, mapping: null,
          })
        }
      }
    }
  }

  // ── Arrange independent chains horizontally ─────────────────────────
  // Nodes reachable from __start__ via edges stay in the center column.
  // Independent nodes (time/tick/event/periodic triggers, not in main chain)
  // get placed in columns to the left.
  if (isCanonical) {
    const mainChainIds = new Set()
    const bfsQueue = ['__start__']
    mainChainIds.add('__start__')
    while (bfsQueue.length > 0) {
      const id = bfsQueue.shift()
      for (const edge of edges) {
        if (edge.from === id && !mainChainIds.has(edge.to)) {
          mainChainIds.add(edge.to)
          bfsQueue.push(edge.to)
        }
      }
    }

    // Collect independent top-level action nodes (not in main chain, not special)
    const independentNodes = nodes.filter(n =>
      !mainChainIds.has(n.id) &&
      n.type !== '__start__' && n.type !== '__stop__' &&
      n.type !== '__entry__' && n.type !== '__exit__' &&
      !n.parentId && !n.isRequirement
    )

    if (independentNodes.length > 0) {
      // Group independent nodes into chains (connected to each other via edges)
      const independentIds = new Set(independentNodes.map(n => n.id))
      const assigned = new Set()
      const chains = []

      for (const node of independentNodes) {
        if (assigned.has(node.id)) continue
        // BFS within independent nodes
        const chain = []
        const q = [node.id]
        assigned.add(node.id)
        while (q.length > 0) {
          const nid = q.shift()
          chain.push(nid)
          for (const edge of edges) {
            if (edge.from === nid && independentIds.has(edge.to) && !assigned.has(edge.to)) {
              assigned.add(edge.to)
              q.push(edge.to)
            }
            if (edge.to === nid && independentIds.has(edge.from) && !assigned.has(edge.from)) {
              assigned.add(edge.from)
              q.push(edge.from)
            }
          }
        }
        chains.push(chain)
      }

      // Place each independent chain in a column to the left
      const COL_GAP = NODE_W + 60  // horizontal gap between columns
      for (let ci = 0; ci < chains.length; ci++) {
        const colX = BASE_X - (ci + 1) * COL_GAP
        // Sort chain nodes by their current Y to preserve relative order
        const chainNodes = chains[ci]
          .map(id => nodes.find(n => n.id === id))
          .filter(Boolean)
          .sort((a, b) => a.y - b.y)

        let y = firstActionY
        for (const node of chainNodes) {
          node.x = colX
          node.y = y
          const nodeH = estimateNodeHeight(node.type, node.params, node.wait_before, node.wait_after, node.message_before, node.message_after)
          y += nodeH + GAP_Y
        }
      }
    }
  }

  // ── Clear immediate/transition triggers ───────────────────────────────
  // These are represented visually by edges, not by the trigger field.
  // Only keep non-standard triggers (tick, time, event, periodic).
  for (const node of nodes) {
    if (node.trigger && (node.trigger.type === 'immediate' || node.trigger.type === 'transition')) {
      node.trigger = null
    }
  }

  // ── Import setup/cleanup actions as container groups ─────────────────
  const PHASE_COL_GAP = NODE_W + 140

  function importPhaseGroup(rawList, groupType, baseX) {
    if (rawList.length === 0) return
    counter++
    const groupId = `${groupType}_${counter}`
    const containerW = Math.max(240, NODE_W + 120)
    const groupY = START_Y

    // Create the container node
    const groupNode = {
      id: groupId, type: groupType, x: baseX, y: groupY,
      parentId: null, params: {},
      trigger: null, wait_before: null, wait_after: null, message_before: null, message_after: null,
      _summaryText: '', _paramLineCount: 0,
      _outPorts: [],
      width: containerW, height: 300,
    }
    nodes.push(groupNode)

    // Entry node
    const entryId = `__entry_${groupId}__`
    const entryX = baseX + (containerW - 80) / 2
    const entryY = groupY + HEADER_H + INNER_PAD
    nodes.push({
      id: entryId, type: '__entry__',
      x: entryX, y: entryY,
      parentId: groupId, _outPorts: ['done'],
    })

    // Add children
    const childBaseX = baseX + (containerW - NODE_W) / 2
    const childBaseY = entryY + ENTRY_H + GAP_Y
    const childResult = addActions(rawList, groupId, childBaseX, childBaseY)

    // Exit node
    const exitId = `__exit_${groupId}__`
    const exitY = childResult.totalHeight > 0
      ? childBaseY + childResult.totalHeight + GAP_Y
      : entryY + ENTRY_H + GAP_Y
    nodes.push({
      id: exitId, type: '__exit__',
      x: entryX, y: exitY,
      parentId: groupId, _outPorts: [],
    })

    // Size container
    groupNode.height = Math.max(200, exitY + ENTRY_H + INNER_PAD + PORTS_H - groupY)

    // Wire children sequentially: entry → first, chain, last → exit
    if (childResult.ids.length > 0) {
      edges.push({
        id: `edge_${entryId}_done_${childResult.ids[0]}`,
        from: entryId, fromPort: 'done', to: childResult.ids[0], mapping: null,
      })
      for (let j = 1; j < childResult.ids.length; j++) {
        edges.push({
          id: `edge_${childResult.ids[j-1]}_done_${childResult.ids[j]}`,
          from: childResult.ids[j-1], fromPort: 'done', to: childResult.ids[j], mapping: null,
        })
      }
      const lastId = childResult.ids[childResult.ids.length - 1]
      edges.push({
        id: `edge_${lastId}_done_${exitId}`,
        from: lastId, fromPort: 'done', to: exitId, mapping: null,
      })
    }
  }

  if (rawSetupActions.length > 0) {
    importPhaseGroup(rawSetupActions, 'setup_group', BASE_X + PHASE_COL_GAP)
  }
  if (rawCleanupActions.length > 0) {
    importPhaseGroup(rawCleanupActions, 'cleanup_group', BASE_X + PHASE_COL_GAP * 2)
  }

  return { nodes, edges, meta }
}

function parseTriggerValue(trigger) {
  if (!trigger) return null
  if (typeof trigger === 'string') {
    if (trigger === 'immediate') return { type: 'immediate' }
    if (trigger === 'transition') return { type: 'transition' }
    if (trigger.startsWith('tick:')) return { type: 'tick', tick: parseInt(trigger.slice(5)) }
    if (trigger.startsWith('time:')) return { type: 'time', time: parseFloat(trigger.slice(5)) }
    if (trigger.startsWith('event:')) return { type: 'event', event: trigger.slice(6) }
    return { type: trigger }
  }
  if (typeof trigger === 'object') {
    return { type: trigger.type || 'immediate', ...trigger }
  }
  return null
}
