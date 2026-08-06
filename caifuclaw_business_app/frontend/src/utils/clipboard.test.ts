import { describe, expect, it, vi } from 'vitest'
import { copyTextToClipboard } from './clipboard'

function fallbackDocument(copyResult = true) {
  const textarea = {
    value: '',
    style: {},
    setAttribute: vi.fn(),
    focus: vi.fn(),
    select: vi.fn(),
    setSelectionRange: vi.fn(),
    remove: vi.fn()
  }
  const activeElement = { focus: vi.fn() }
  const document = {
    body: { appendChild: vi.fn() },
    activeElement,
    createElement: vi.fn(() => textarea),
    getSelection: vi.fn(() => null),
    execCommand: vi.fn(() => copyResult)
  } as unknown as Document

  return { document, textarea, activeElement }
}

describe('copyTextToClipboard', () => {
  it('uses the Clipboard API in a secure context', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)

    await copyTextToClipboard('field description', {
      isSecureContext: true,
      clipboard: { writeText }
    })

    expect(writeText).toHaveBeenCalledWith('field description')
  })

  it('uses the synchronous fallback in an insecure Windows-style context', async () => {
    const writeText = vi.fn()
    const { document, textarea, activeElement } = fallbackDocument()

    await copyTextToClipboard('line 1\nline 2', {
      isSecureContext: false,
      clipboard: { writeText },
      document
    })

    expect(writeText).not.toHaveBeenCalled()
    expect(textarea.value).toBe('line 1\nline 2')
    expect(textarea.select).toHaveBeenCalledOnce()
    expect(document.execCommand).toHaveBeenCalledWith('copy')
    expect(textarea.remove).toHaveBeenCalledOnce()
    expect(activeElement.focus).toHaveBeenCalledWith({ preventScroll: true })
  })

  it('falls back when the Clipboard API is rejected', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('denied'))
    const { document } = fallbackDocument()

    await copyTextToClipboard('field description', {
      isSecureContext: true,
      clipboard: { writeText },
      document
    })

    expect(document.execCommand).toHaveBeenCalledWith('copy')
  })

  it('rejects when neither copy method succeeds', async () => {
    const { document } = fallbackDocument(false)

    await expect(copyTextToClipboard('field description', {
      isSecureContext: false,
      document
    })).rejects.toThrow('Clipboard copy is unavailable')
  })
})
