import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from '@/router/navigation'
import * as pdfjsLib from 'pdfjs-dist/legacy/build/pdf.mjs'
import pdfWorker from 'pdfjs-dist/legacy/build/pdf.worker.mjs?url'
import './PrintPreview.less'

;(pdfjsLib as unknown as { GlobalWorkerOptions: { workerSrc: string } }).GlobalWorkerOptions.workerSrc = pdfWorker

const CHANNEL_NAME = 'caifuclaw-print-preview'

export function PrintPreview() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''
  const pageContainerRef = useRef<HTMLDivElement | null>(null)
  const channelRef = useRef<BroadcastChannel | null>(null)
  const readyTimerRef = useRef<number | null>(null)
  const timeoutTimerRef = useRef<number | null>(null)
  const [rendered, setRendered] = useState(false)
  const [errorText, setErrorText] = useState('')
  const [pageCount, setPageCount] = useState(0)
  const [fileName, setFileName] = useState('打印预览')

  const title = fileName || '打印预览'
  const statusText = useMemo(() => {
    if (errorText) return '生成失败'
    if (rendered) return `共 ${pageCount} 页`
    return '等待 PDF 数据'
  }, [errorText, pageCount, rendered])

  function clearTimers() {
    if (readyTimerRef.current) window.clearInterval(readyTimerRef.current)
    if (timeoutTimerRef.current) window.clearTimeout(timeoutTimerRef.current)
    readyTimerRef.current = null
    timeoutTimerRef.current = null
  }

  function announceReady() {
    channelRef.current?.postMessage({ type: 'print-preview-ready', token })
  }

  async function renderPdf(buffer: Uint8Array | ArrayBuffer) {
    clearTimers()
    setErrorText('')
    setRendered(false)
    pageContainerRef.current?.replaceChildren()
    const data = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer)
    const pdf = await (
      pdfjsLib as unknown as {
        getDocument: (opts: { data: Uint8Array }) => {
          promise: Promise<{
            numPages: number
            getPage: (n: number) => Promise<{
              getViewport: (opts: { scale: number }) => { width: number; height: number }
              render: (opts: { canvasContext: CanvasRenderingContext2D; viewport: unknown }) => { promise: Promise<void> }
            }>
          }>
        }
      }
    ).getDocument({ data }).promise

    setPageCount(pdf.numPages)
    for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
      const page = await pdf.getPage(pageNumber)
      const viewport = page.getViewport({ scale: 1.35 })
      const outputScale = Math.min(window.devicePixelRatio || 1, 2)
      const canvas = document.createElement('canvas')
      const context = canvas.getContext('2d')
      if (!context) continue
      canvas.className = 'print-preview-page-canvas'
      canvas.width = Math.floor(viewport.width * outputScale)
      canvas.height = Math.floor(viewport.height * outputScale)
      canvas.style.width = `${Math.floor(viewport.width)}px`
      canvas.style.height = `${Math.floor(viewport.height)}px`
      context.setTransform(outputScale, 0, 0, outputScale, 0, 0)
      pageContainerRef.current?.appendChild(canvas)
      await page.render({ canvasContext: context, viewport }).promise
    }
    setRendered(true)
    channelRef.current?.postMessage({ type: 'print-preview-rendered', token })
  }

  useEffect(() => {
    if (!('BroadcastChannel' in window)) {
      setErrorText('当前浏览器不支持预览消息通道')
      return undefined
    }
    const channel = new BroadcastChannel(CHANNEL_NAME)
    channelRef.current = channel
    channel.onmessage = async (event) => {
      const payload = (event.data || {}) as {
        type?: string
        token?: string
        filename?: string
        buffer?: Uint8Array | ArrayBuffer
      }
      if (payload.type !== 'print-preview-pdf' || payload.token !== token) return
      setFileName(payload.filename || '打印预览')
      try {
        if (payload.buffer) await renderPdf(payload.buffer)
      } catch (error) {
        clearTimers()
        setErrorText((error as Error)?.message || 'PDF 预览生成失败')
      }
    }
    announceReady()
    readyTimerRef.current = window.setInterval(announceReady, 500)
    timeoutTimerRef.current = window.setTimeout(() => {
      setErrorText('未收到 PDF 数据，请关闭页签后重试')
      clearTimers()
    }, 30000)
    return () => {
      clearTimers()
      channel.close()
      channelRef.current = null
    }
  }, [token])

  return (
    <div className="print-preview-page">
      <header className="print-preview-toolbar">
        <div className="print-preview-title">
          <span>{title}</span>
          <small>{statusText}</small>
        </div>
        <div className="print-preview-actions">
          <button type="button" disabled={!rendered} onClick={() => window.print()}>
            打印
          </button>
        </div>
      </header>
      <main className="print-preview-canvas-wrap">
        {!rendered && !errorText ? <div className="print-preview-loading">PDF 正在生成，请稍候...</div> : null}
        {errorText ? <div className="print-preview-error">{errorText}</div> : null}
        <div ref={pageContainerRef} className="print-preview-pages" />
      </main>
    </div>
  )
}
