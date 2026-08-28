// 编辑器权威类型层（对齐 Python domain/，是 browser 权威的唯一真源类型）。
// 与 api.ts 的「传输类型」分开：这里是完整权威类型，api.ts 后续改为从这里导入。

export interface ClipTransform {
  scale?: number | null
  scaleX?: number | null
  scaleY?: number | null
  x?: number | null
  y?: number | null
  rotation?: number | null
  opacity?: number | null
  borderRadius?: number | null
}

export interface ClipFilters {
  brightness?: number | null
  contrast?: number | null
  saturate?: number | null
  blur?: number | null
}

export interface Keyframe {
  frame: number
  value: number
  easing?: string | null
}

export interface ReframeKeyframe {
  frame: number
  focalPointX: number
  focalPointY: number
  magnification: number
}

export interface TranscriptWord {
  text: string
  startMs: number
  endMs: number
  speaker?: string | null
  id?: string | null
}

export type ItemKind =
  | 'motion-graphic' | 'audio' | 'video' | 'image' | 'text'
  | 'gif' | 'svg' | 'solid' | 'sequence'

export interface TimelineItem {
  id: string
  track: string
  startFrame: number
  durationInFrames: number
  name: string
  kind: ItemKind
  templateId?: string | null
  code?: string | null
  props?: Record<string, unknown> | null
  width?: number | null
  height?: number | null
  src?: string | null
  sourceAssetId?: string | null
  sourceFilename?: string | null
  sourceRevision?: string | null
  sourceContentHash?: string | null
  volume?: number | null
  srcInFrame?: number | null
  fadeInFrames?: number | null
  fadeOutFrames?: number | null
  transform?: ClipTransform | null
  keyframes?: Record<string, Keyframe[]> | null
  filters?: ClipFilters | null
  playbackRate?: number | null
  transcript?: TranscriptWord[] | null
  backgroundFill?: boolean
  reframeKeyframes?: ReframeKeyframe[]
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
  items: TimelineItem[]
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

export function activeTimeline(doc: ProjectDoc): Timeline {
  return doc.timelines.find((t) => t.id === doc.activeTimelineId) ?? doc.timelines[0]
}

export function defaultProject(): ProjectDoc {
  const tl: Timeline = { id: 'tl1', name: '时间线 1', order: 0, fps: 30, items: [], transitions: [], markers: [], captions: null }
  return { version: 1, assets: [], timelines: [tl], activeTimelineId: 'tl1' }
}
