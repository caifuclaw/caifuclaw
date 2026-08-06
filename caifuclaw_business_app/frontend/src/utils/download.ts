/** 浏览器下载二进制 / Blob URL 的辅助函数 */

type SavePickerResult =
  | { status: 'picked'; write: (blob: Blob) => Promise<void> }
  | { status: 'cancelled' }
  | { status: 'unsupported' }

type SavePickerWindow = Window & {
  showDirectoryPicker?: (options?: { mode?: 'read' | 'readwrite' }) => Promise<FileSystemDirectoryHandle>
  showSaveFilePicker?: (options?: {
    suggestedName?: string
    types?: Array<{
      description?: string
      accept: Record<string, string[]>
    }>
  }) => Promise<{
    createWritable: () => Promise<{
      write: (data: Blob) => Promise<void>
      close: () => Promise<void>
      abort?: () => Promise<void>
    }>
  }>
}

export async function pickSaveDirectory() {
  const picker = (window as SavePickerWindow).showDirectoryPicker
  if (!picker) return null
  return picker.call(window, { mode: 'readwrite' })
}

export function canPickSaveDirectory() {
  return Boolean((window as SavePickerWindow).showDirectoryPicker)
}

export async function pickSaveFile(
  filename: string,
  options?: { description?: string; mimeType?: string; extensions?: string[] }
): Promise<SavePickerResult> {
  const picker = (window as SavePickerWindow).showSaveFilePicker
  if (!picker) return { status: 'unsupported' }

  try {
    const handle = await picker.call(window, {
      suggestedName: filename,
      types:
        options?.mimeType && options?.extensions?.length
          ? [
              {
                description: options.description || 'Export file',
                accept: { [options.mimeType]: options.extensions }
              }
            ]
          : undefined
    })

    return {
      status: 'picked',
      write: async (blob: Blob) => {
        const writable = await handle.createWritable()
        try {
          await writable.write(blob)
          await writable.close()
        } catch (error) {
          await writable.abort?.()
          throw error
        }
      }
    }
  } catch (error) {
    if ((error as DOMException)?.name === 'AbortError') return { status: 'cancelled' }
    throw error
  }
}

export function canPickSaveFile() {
  return Boolean((window as SavePickerWindow).showSaveFilePicker)
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function downloadUrl(url: string, filename?: string) {
  const a = document.createElement('a')
  a.href = url
  if (filename) a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
}

export function openDownloadWindow() {
  return window.open('about:blank', '_blank')
}

export function navigateDownloadWindow(win: Window | null, url: string, filename?: string) {
  if (win && !win.closed) {
    win.location.href = url
    return
  }
  downloadUrl(url, filename)
}

/** base64 → Uint8Array */
export function base64ToBytes(base64: string): Uint8Array {
  const binary = atob(base64)
  const len = binary.length
  const bytes = new Uint8Array(len)
  for (let i = 0; i < len; i++) bytes[i] = binary.charCodeAt(i)
  return bytes
}

/** base64 PDF → 在新标签页打开 */
export function openPdfInNewTab(base64: string, filename = 'document.pdf') {
  const bytes = base64ToBytes(base64)
  const blob = new Blob([bytes], { type: 'application/pdf' })
  const url = URL.createObjectURL(blob)
  const win = window.open(url, '_blank')
  if (!win) {
    // 弹窗被拦：回退为下载
    downloadBlob(blob, filename)
  }
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
