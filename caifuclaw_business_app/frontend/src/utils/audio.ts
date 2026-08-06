/**
 * 扫码出库声音反馈 —— 预解码音频文件优先，beep 兜底
 */

import { errorSoundData, repeatSoundData, successSoundData } from './scanSoundData'

type ScanSound = 'success' | 'duplicate' | 'error'

const SOUND_DATA: Record<ScanSound, string> = {
  success: successSoundData,
  duplicate: repeatSoundData,
  error: errorSoundData
}

const fallbackBeeps: Record<ScanSound, () => Promise<void>> = {
  success: () => beep(880, 90, 0.18),
  duplicate: async () => {
    await beep(660, 80, 0.18)
    await beep(660, 80, 0.18, 0.04)
  },
  error: () => beep(260, 280, 0.22)
}

let audioCtx: AudioContext | null = null
const decodedSounds = new Map<ScanSound, AudioBuffer>()
const loadingSounds = new Map<ScanSound, Promise<AudioBuffer | null>>()

function getCtx(): AudioContext | null {
  if (typeof window === 'undefined') return null
  if (!audioCtx) {
    const Ctor =
      window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!Ctor) return null
    audioCtx = new Ctor()
  }
  return audioCtx
}

function dataUrlToArrayBuffer(dataUrl: string): ArrayBuffer {
  const marker = ';base64,'
  const index = dataUrl.indexOf(marker)
  if (index === -1) throw new Error('Unsupported scan sound data URL')

  const binary = atob(dataUrl.slice(index + marker.length))
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  return bytes.buffer
}

function loadSound(name: ScanSound): Promise<AudioBuffer | null> {
  const cached = decodedSounds.get(name)
  if (cached) return Promise.resolve(cached)

  const loading = loadingSounds.get(name)
  if (loading) return loading

  const promise = (async () => {
    const ctx = getCtx()
    if (!ctx) return null
    const buffer = dataUrlToArrayBuffer(SOUND_DATA[name])
    const decoded = await ctx.decodeAudioData(buffer)
    decodedSounds.set(name, decoded)
    return decoded
  })().catch(() => {
    loadingSounds.delete(name)
    return null
  })

  loadingSounds.set(name, promise)
  return promise
}

function playBuffer(buffer: AudioBuffer): Promise<void> {
  return new Promise((resolve) => {
    const ctx = getCtx()
    if (!ctx) return resolve()
    const source = ctx.createBufferSource()
    source.buffer = buffer
    source.connect(ctx.destination)
    source.start(ctx.currentTime)
    source.onended = () => resolve()
  })
}

async function playSound(name: ScanSound) {
  const cached = decodedSounds.get(name)
  if (cached) {
    await playBuffer(cached)
    return
  }

  void loadSound(name)
  await fallbackBeeps[name]()
}

function beep(freq: number, durationMs: number, gain = 0.2, when = 0): Promise<void> {
  return new Promise((resolve) => {
    const ctx = getCtx()
    if (!ctx) return resolve()
    const osc = ctx.createOscillator()
    const g = ctx.createGain()
    osc.frequency.value = freq
    osc.type = 'sine'
    g.gain.value = gain
    osc.connect(g)
    g.connect(ctx.destination)
    const start = ctx.currentTime + when
    osc.start(start)
    osc.stop(start + durationMs / 1000)
    osc.onended = () => resolve()
  })
}

export async function playSuccess() {
  await playSound('success')
}

export async function playDuplicate() {
  await playSound('duplicate')
}

export async function playError() {
  await playSound('error')
}

export function preloadScanSounds() {
  void Promise.all((Object.keys(SOUND_DATA) as ScanSound[]).map((name) => loadSound(name)))
}

/** 用户首次交互后调用，避免 autoplay 限制 */
export function unlockAudio() {
  const ctx = getCtx()
  if (ctx?.state === 'suspended') ctx.resume().catch(() => undefined)
  preloadScanSounds()
}
