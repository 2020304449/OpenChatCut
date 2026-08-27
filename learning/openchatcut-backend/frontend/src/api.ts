export interface Clip {
  id: string
  track: string
  startFrame: number
  durationInFrames: number
  name: string
  kind: string
  src?: string | null
  volume?: number | null
  sourceAssetId?: string | null
  fadeInFrames?: number | null
  fadeOutFrames?: number | null
}

export interface TransitionItem {
  id: string
  incomingItemId: string
  transType: string
  durationInFrames?: number | null
}

export interface CaptionCue {
  startFrame: number
  endFrame: number
  text: string
  speakerId?: string | null
}

export interface CaptionsData {
  enabled: boolean
  items: CaptionCue[]
}

export interface Marker {
  id: string
  name: string
  frame?: number | null
  startFrame?: number | null
  endFrame?: number | null
  color?: string | null
}

export interface MediaAsset {
  id: string
  name: string
  kind: string
  src?: string | null
  durationInFrames?: number | null
  width?: number | null
  height?: number | null
  favorite?: boolean
  folderId?: string | null
}

export interface MediaFolder {
  id: string
  name: string
}

export interface TrackFlags {
  kind?: string | null
  name?: string | null
  hidden?: boolean
  muted?: boolean
  locked?: boolean
  collapsed?: boolean
  role?: string | null
}

export interface Timeline {
  id: string
  name: string
  order?: number
  hidden?: boolean
  fps: number
  width?: number | null
  height?: number | null
  items: Clip[]
  trackOrder?: string[]
  tracks?: Record<string, TrackFlags>
  transitions: TransitionItem[]
  markers: Marker[]
  captionsHidden?: boolean
  captions: CaptionsData | null
}

export interface ProjectDoc {
  version: number
  assets: MediaAsset[]
  mediaFolders?: MediaFolder[]
  timelines: Timeline[]
  activeTimelineId: string
}

export interface ToolCallEvent {
  name: string
  args: Record<string, unknown>
  result?: Record<string, unknown>
}

export interface StreamHandlers {
  onAssistant: (text: string) => void
  onToolCall: (name: string, args: Record<string, unknown>) => void
  onToolResult: (result: Record<string, unknown>) => void
  onState: (doc: ProjectDoc) => void
  onDone: () => void
  onError: (message: string) => void
}

export async function getState(): Promise<ProjectDoc> {
  const res = await fetch('/api/state')
  return res.json()
}

export async function undo(): Promise<ProjectDoc> {
  const res = await fetch('/api/undo', { method: 'POST' })
  return res.json()
}

export async function redo(): Promise<ProjectDoc> {
  const res = await fetch('/api/redo', { method: 'POST' })
  return res.json()
}

export function activeTimeline(doc: ProjectDoc): Timeline | undefined {
  return doc.timelines.find((t) => t.id === doc.activeTimelineId) ?? doc.timelines[0]
}

interface SseEvent {
  event: string
  data: Record<string, any>
}

function parseSse(raw: string): SseEvent | null {
  let event = 'message'
  let data = ''
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data += line.slice(5).trim()
  }
  if (!data) return null
  try {
    return { event, data: JSON.parse(data) }
  } catch {
    return { event, data: {} }
  }
}

function dispatch(ev: SseEvent, h: StreamHandlers) {
  switch (ev.event) {
    case 'assistant':
      h.onAssistant(ev.data.text ?? '')
      break
    case 'tool_call':
      h.onToolCall(ev.data.name, ev.data.arguments ?? {})
      break
    case 'tool_result':
      h.onToolResult(ev.data)
      break
    case 'state':
      h.onState(ev.data as ProjectDoc)
      break
    case 'error':
      h.onError(ev.data.message ?? 'unknown error')
      break
    case 'done':
      h.onDone()
      break
  }
}

export async function streamChat(message: string, handlers: StreamHandlers): Promise<void> {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })

  if (!res.ok || !res.body) {
    handlers.onError(`HTTP ${res.status}`)
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let sep: number
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      const ev = parseSse(raw)
      if (ev) dispatch(ev, handlers)
    }
  }
}
