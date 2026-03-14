/**
 * Recent files storage using IndexedDB for file handles.
 *
 * File System Access API file handles can be stored in IndexedDB and
 * later used to re-open files (after requesting permission).
 * Falls back to name-only entries for browsers without the API.
 *
 * Stores up to MAX_RECENT entries, most recent first.
 */

import { ref } from 'vue'

const DB_NAME = 'experiment-designer'
const STORE_RECENT = 'recent-files'
const STORE_TAB_HANDLES = 'tab-handles'
const DB_VERSION = 2
const MAX_RECENT = 10

// ── Reactive state ──────────────────────────────────────────────────────────
export const recentFiles = ref([])  // [{ name, timestamp, handle? }]

// ── IndexedDB helpers ───────────────────────────────────────────────────────

export function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = (event) => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE_RECENT)) {
        db.createObjectStore(STORE_RECENT, { keyPath: 'id', autoIncrement: true })
      }
      if (!db.objectStoreNames.contains(STORE_TAB_HANDLES)) {
        db.createObjectStore(STORE_TAB_HANDLES, { keyPath: 'tabId' })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

function txStore(db, storeName, mode) {
  const tx = db.transaction(storeName, mode)
  return tx.objectStore(storeName)
}

export function idbGetAll(store) {
  return new Promise((resolve, reject) => {
    const req = store.getAll()
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

export function idbClear(store) {
  return new Promise((resolve, reject) => {
    const req = store.clear()
    req.onsuccess = () => resolve()
    req.onerror = () => reject(req.error)
  })
}

export function idbPut(store, value) {
  return new Promise((resolve, reject) => {
    const req = store.put(value)
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

// ── Public API ──────────────────────────────────────────────────────────────

/** Load recent files from IndexedDB into the reactive ref. */
export async function loadRecentFiles() {
  try {
    const db = await openDB()
    const store = txStore(db, STORE_RECENT, 'readonly')
    const all = await idbGetAll(store)
    db.close()
    // Sort by timestamp descending
    all.sort((a, b) => b.timestamp - a.timestamp)
    recentFiles.value = all.slice(0, MAX_RECENT)
  } catch {
    recentFiles.value = []
  }
}

/**
 * Add or update a recent file entry.
 * If a handle with the same name exists, it's moved to the top.
 */
export async function addRecentFile(name, handle) {
  try {
    const db = await openDB()

    // Read all, filter out duplicate by name, prepend new, trim to MAX
    const store = txStore(db, STORE_RECENT, 'readwrite')
    const all = await idbGetAll(store)
    await idbClear(store)

    const filtered = all.filter(e => e.name !== name)
    const updated = [
      { name, handle: handle || null, timestamp: Date.now() },
      ...filtered,
    ].slice(0, MAX_RECENT)

    // Re-insert with fresh auto-increment ids
    const writeStore = txStore(db, STORE_RECENT, 'readwrite')
    for (const entry of updated) {
      delete entry.id
      await idbPut(writeStore, entry)
    }

    db.close()
    recentFiles.value = updated
  } catch {
    // Silently fail — recent files are non-critical
  }
}

/**
 * Open a recent file by re-requesting permission on its handle.
 * Returns { text, handle, name } on success, or null on failure/cancel.
 */
export async function openRecentFile(entry) {
  if (!entry.handle) return null

  try {
    // Request read permission (may show a prompt)
    const perm = await entry.handle.queryPermission({ mode: 'readwrite' })
    if (perm !== 'granted') {
      const req = await entry.handle.requestPermission({ mode: 'readwrite' })
      if (req !== 'granted') return null
    }

    const file = await entry.handle.getFile()
    const text = await file.text()
    return { text, handle: entry.handle, name: entry.name }
  } catch {
    return null
  }
}
