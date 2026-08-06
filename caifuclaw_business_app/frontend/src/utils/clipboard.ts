interface ClipboardEnvironment {
  isSecureContext: boolean
  clipboard?: Pick<Clipboard, 'writeText'>
  document?: Document
}

function currentClipboardEnvironment(): ClipboardEnvironment {
  return {
    isSecureContext: globalThis.isSecureContext === true,
    clipboard: globalThis.navigator?.clipboard,
    document: globalThis.document
  }
}

function restoreFocus(element: HTMLElement | null) {
  if (!element || typeof element.focus !== 'function') return
  try {
    element.focus({ preventScroll: true })
  } catch {
    element.focus()
  }
}

function copyWithExecCommand(text: string, document: Document) {
  if (!document.body || typeof document.execCommand !== 'function') return false

  const activeElement = document.activeElement as HTMLElement | null
  const selection = document.getSelection()
  const selectedRanges = selection
    ? Array.from({ length: selection.rangeCount }, (_, index) => selection.getRangeAt(index).cloneRange())
    : []
  const textarea = document.createElement('textarea')

  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.setAttribute('aria-hidden', 'true')
  Object.assign(textarea.style, {
    position: 'fixed',
    top: '0',
    left: '0',
    width: '1px',
    height: '1px',
    padding: '0',
    border: '0',
    opacity: '0',
    pointerEvents: 'none'
  })

  document.body.appendChild(textarea)
  try {
    try {
      textarea.focus({ preventScroll: true })
    } catch {
      textarea.focus()
    }
    textarea.select()
    textarea.setSelectionRange(0, text.length)
    return document.execCommand('copy')
  } finally {
    textarea.remove()
    restoreFocus(activeElement)
    if (selection) {
      selection.removeAllRanges()
      selectedRanges.forEach((range) => selection.addRange(range))
    }
  }
}

export async function copyTextToClipboard(
  text: string,
  environment: ClipboardEnvironment = currentClipboardEnvironment()
) {
  if (environment.isSecureContext && environment.clipboard?.writeText) {
    try {
      await environment.clipboard.writeText(text)
      return
    } catch {
      // Permission policies can reject the modern API even in a secure context.
    }
  }

  if (environment.document && copyWithExecCommand(text, environment.document)) return
  throw new Error('Clipboard copy is unavailable')
}
