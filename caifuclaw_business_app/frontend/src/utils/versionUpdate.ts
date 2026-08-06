const VERSION_CHECK_INTERVAL_MS = 60_000
const PENDING_RELOAD_RETRY_MS = 30_000
const VERSION_URL = '/version.json'
const RELOADED_VERSION_STORAGE_KEY = 'caifuclaw:auto-reloaded-version'
const RELOADED_CHUNK_STORAGE_KEY = 'caifuclaw:auto-reloaded-chunk'
const DYNAMIC_IMPORT_ERROR_PATTERNS = [
  'Failed to fetch dynamically imported module',
  'Importing a module script failed',
  'error loading dynamically imported module'
]

type VersionPayload = {
  version?: string
}

let currentVersion = __APP_VERSION__
let reloading = false
let lastReloadedVersion: string | null = null
let pendingServerVersion: string | null = null
let pendingChunkReload = false
let pendingReloadTimer: number | null = null
let userInteracted = false

function isEditableElement(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false

  const editable = target.closest('input, textarea, select, [contenteditable="true"], [contenteditable=""]')
  if (!(editable instanceof HTMLElement)) return false

  if (
    editable instanceof HTMLInputElement ||
    editable instanceof HTMLTextAreaElement ||
    editable instanceof HTMLSelectElement
  ) {
    if (editable instanceof HTMLInputElement) {
      if (editable.disabled || editable.readOnly) return false
      return !['button', 'checkbox', 'file', 'hidden', 'radio', 'reset', 'submit'].includes(editable.type)
    }
    if (editable instanceof HTMLTextAreaElement) return !editable.disabled && !editable.readOnly
    if (editable.disabled) return false
    return true
  }

  return editable.isContentEditable
}

function hasFocusedEditableElement() {
  return isEditableElement(document.activeElement)
}

function trackUserActivity(event: Event) {
  userInteracted = true
}

function canReloadWithoutInterruptingUser() {
  if (userInteracted || hasFocusedEditableElement()) return false
  return true
}

function getLastReloadedVersion() {
  try {
    return window.sessionStorage.getItem(RELOADED_VERSION_STORAGE_KEY) || lastReloadedVersion
  } catch {
    return lastReloadedVersion
  }
}

function setLastReloadedVersion(version: string) {
  lastReloadedVersion = version
  try {
    window.sessionStorage.setItem(RELOADED_VERSION_STORAGE_KEY, version)
    return true
  } catch {
    // sessionStorage may be unavailable in restrictive browser modes.
    return false
  }
}

function clearLastReloadedVersion() {
  lastReloadedVersion = null
  try {
    window.sessionStorage.removeItem(RELOADED_VERSION_STORAGE_KEY)
  } catch {
    // sessionStorage may be unavailable in restrictive browser modes.
  }
}

function reloadOnce(delay = 0) {
  if (reloading) return

  reloading = true
  window.setTimeout(() => window.location.reload(), delay)
}

function setChunkReloaded() {
  try {
    const marker = currentVersion || 'unknown'
    if (window.sessionStorage.getItem(RELOADED_CHUNK_STORAGE_KEY) === marker) return false
    window.sessionStorage.setItem(RELOADED_CHUNK_STORAGE_KEY, marker)
    return true
  } catch {
    return false
  }
}

function schedulePendingReload(delay = 0) {
  if (pendingReloadTimer !== null) return

  pendingReloadTimer = window.setTimeout(() => {
    pendingReloadTimer = null
    flushPendingReload()
  }, delay)
}

function queueVersionReload(serverVersion: string) {
  pendingServerVersion = serverVersion
  schedulePendingReload()
}

function queueChunkReload() {
  if (setChunkReloaded()) reloadOnce()
}

function flushPendingReload() {
  if (reloading || (!pendingServerVersion && !pendingChunkReload)) return

  if (!canReloadWithoutInterruptingUser()) {
    schedulePendingReload(PENDING_RELOAD_RETRY_MS)
    return
  }

  if (pendingServerVersion) {
    if (getLastReloadedVersion() === pendingServerVersion) {
      currentVersion = pendingServerVersion
      pendingServerVersion = null
      return
    }

    if (!setLastReloadedVersion(pendingServerVersion)) {
      currentVersion = pendingServerVersion
      pendingServerVersion = null
      return
    }

    reloadOnce(document.visibilityState === 'visible' ? 500 : 0)
    return
  }

  if (pendingChunkReload && setChunkReloaded()) reloadOnce()
}

function isDynamicImportError(reason: unknown) {
  const message = reason instanceof Error ? reason.message : String(reason || '')
  return DYNAMIC_IMPORT_ERROR_PATTERNS.some((pattern) => message.includes(pattern))
}

async function loadServerVersion() {
  const response = await fetch(`${VERSION_URL}?t=${Date.now()}`, {
    cache: 'no-store',
    headers: {
      'Cache-Control': 'no-cache'
    }
  })

  if (!response.ok) return null

  const payload = (await response.json()) as VersionPayload
  return typeof payload.version === 'string' && payload.version ? payload.version : null
}

async function checkForNewVersion() {
  if (reloading) return

  try {
    const serverVersion = await loadServerVersion()
    if (!serverVersion) return

    if (currentVersion && serverVersion !== currentVersion) {
      if (getLastReloadedVersion() === serverVersion) {
        currentVersion = serverVersion
        return
      }

      queueVersionReload(serverVersion)
      return
    }

    clearLastReloadedVersion()
    currentVersion = serverVersion
  } catch {
    // Version checks should never interrupt normal business operations.
  }
}

export function startVersionUpdateChecker() {
  if (import.meta.env.DEV) return

  window.addEventListener('vite:preloadError', (event) => {
    queueChunkReload()
  })
  window.addEventListener('unhandledrejection', (event) => {
    if (isDynamicImportError(event.reason)) queueChunkReload()
  })

  ;['pointerdown', 'keydown', 'wheel', 'touchstart', 'input', 'change'].forEach((eventName) => {
    document.addEventListener(eventName, trackUserActivity, { capture: true, passive: true })
  })

  const check = () => {
    void checkForNewVersion()
    flushPendingReload()
  }
  const checkWhenVisible = () => {
    if (document.visibilityState === 'visible') check()
    else flushPendingReload()
  }

  window.setInterval(check, VERSION_CHECK_INTERVAL_MS)
  window.addEventListener('focus', check)
  window.addEventListener('online', check)
  document.addEventListener('visibilitychange', checkWhenVisible)

  check()
}
