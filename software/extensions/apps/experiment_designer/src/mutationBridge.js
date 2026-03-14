/**
 * Mutation bridge for experiment designer.
 *
 * Intercepts local graph mutations and forwards them to the Python backend.
 * Receives remote mutations (from Python or other views) and applies them
 * locally without echoing back.
 *
 * Loop prevention: each mutation carries a `source` ID. The bridge suppresses
 * notifyMutation() when applying a remote mutation, and frontends ignore
 * mutations from their own source.
 */

let _instanceId = null
let _emitFn = null      // (mutation) => void — sends mutation to Python
let _applyingRemote = false

/**
 * Initialize the bridge with a unique instance ID and an emit function.
 * @param {string} instanceId  Unique ID for this frontend instance
 * @param {Function} emitFn    Called with mutation object to send to Python
 */
export function initBridge(instanceId, emitFn) {
    _instanceId = instanceId
    _emitFn = emitFn
}

/**
 * Called by graphState.js after each local mutation.
 * Forwards the mutation to Python (via emitFn) with the local source ID.
 */
export function notifyMutation(type, data) {
    if (_applyingRemote) return  // suppress echo during remote apply
    if (!_emitFn) return

    _emitFn({
        mutation: type,
        data,
        source: _instanceId,
    })
}

/**
 * Apply a remote mutation to the local graph state.
 * Sets _applyingRemote = true so that:
 *   - notifyMutation() is suppressed (no echo)
 *   - snapshot() is suppressed (via isApplyingRemote())
 *
 * @param {object} mutation  { mutation, data, source }
 * @param {object} graphOps  Object with graphState.js functions to call
 */
export function applyRemoteMutation(mutation, graphOps) {
    // Ignore mutations from our own source
    if (mutation.source === _instanceId) return

    _applyingRemote = true
    try {
        _dispatchMutation(mutation, graphOps)
    } finally {
        _applyingRemote = false
    }
}

/**
 * Check if we're currently applying a remote mutation.
 * Used by graphState.js to skip snapshot() during remote applies.
 */
export function isApplyingRemote() {
    return _applyingRemote
}

/**
 * Dispatch a mutation to the appropriate graphState.js function.
 */
function _dispatchMutation(mutation, ops) {
    const { mutation: type, data } = mutation

    switch (type) {
        case 'add_node':
            ops.addNodeDirect(data.node)
            break
        case 'remove_node':
            ops.removeNodeDirect(data.id)
            break
        case 'move_nodes':
            if (data.positions) {
                for (const [nodeId, pos] of Object.entries(data.positions)) {
                    ops.updateNodePosition(nodeId, pos.x, pos.y)
                }
            }
            break
        case 'update_node_params':
            ops.updateNodeParams(data.id, data.params)
            break
        case 'update_node_field':
            ops.updateNodeField(data.id, data.field, data.value)
            break
        case 'rename_node':
            ops.renameNode(data.oldId, data.newId)
            break
        case 'move_node_to_container':
            ops.moveNodeToContainer(data.id, data.containerId)
            break
        case 'remove_node_from_container':
            ops.removeNodeFromContainer(data.id)
            break
        case 'add_edge':
            ops.addEdgeDirect(data.edge)
            break
        case 'remove_edge':
            ops.removeEdgeDirect(data.id)
            break
        case 'update_edge_mapping':
            ops.updateEdgeMapping(data.id, data.mapping)
            break
        case 'update_meta':
            ops.updateMeta(data.field, data.value)
            break
        case 'add_variable':
            ops.addVariable(data.name, data.value)
            break
        case 'remove_variable':
            ops.removeVariable(data.name)
            break
        case 'update_variable':
            ops.updateVariable(data.name, data.value)
            break
        case 'add_event':
            ops.addEvent(data.name)
            break
        case 'remove_event':
            ops.removeEvent(data.name)
            break
        case 'load_state':
            ops.loadStateFromMutation(data)
            break
    }
}
