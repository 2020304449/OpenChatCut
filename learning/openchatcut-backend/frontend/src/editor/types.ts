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

export interface ZoomEffect {
  magnification?: number | null
  focalPointX?: number | null
  focalPointY?: number | null
  shape?: string | null
}

export interface ClipEffect {
  id: string
  assetId: string
  overrides?: Record<string, unknown> | null
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

export interface TranscriptVariantWord {
  i: number
  text: string
}

export interface TranscriptVariant {
  id: string
  lang: string
  kind: string
  label: string
  words?: TranscriptVariantWord[]
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
  zoom?: ZoomEffect | null
  effects?: ClipEffect[]
  playbackRate?: number | null
  transcript?: TranscriptWord[] | null
  transcriptGenerationId?: string | null
  transcriptStale?: boolean
  variants?: TranscriptVariant[]
  deletedWordIdx?: number[]
  silenceFrames?: number | null
  cutPadFrames?: number | null
  gapCapsMs?: Record<string, number> | null
  transcriptPlayOrder?: number[] | null
  backgroundFill?: boolean
  backgroundFillStrength?: number | null
  denoisedSrc?: string | null
  denoiseStrength?: number | null
  reframeKeyframes?: ReframeKeyframe[]
  multicamGroupId?: string | null
  multicamAngleId?: string | null
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
  transcript?: TranscriptWord[]
  transcriptSourceRevision?: string | null
  transcriptStale?: boolean
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

export interface Watermark {
  enabled?: boolean
  text?: string
  position?: string
  opacity?: number
}

export interface TimelineLinkGroup {
  id: string
  itemIds: string[]
  anchorItemId: string
  mode: string
}

export interface MulticamAngle {
  id: string
  itemId: string
  label: string
  offsetFrames?: number
  confidence?: number
}

export interface MulticamAngleDecision {
  id: string
  fromFrame: number
  toFrame: number
  angleId: string
}

export interface MulticamGroup {
  id: string
  referenceAngleId: string
  masterAngleId: string
  angles?: MulticamAngle[]
  syncMethod?: string
  decisions?: MulticamAngleDecision[]
}

export interface Timeline {
  id: string
  name: string
  order?: number
  hidden?: boolean
  fps: number
  width?: number | null
  height?: number | null
  fit?: string | null
  items: TimelineItem[]
  trackOrder?: string[]
  tracks?: Record<string, TrackFlags>
  transitions: TransitionItem[]
  markers: Marker[]
  captionsHidden?: boolean
  captions: CaptionsData | null
  selectedId?: string | null
  selectedIds?: string[]
  watermark?: Watermark | null
  linkGroups?: TimelineLinkGroup[]
  multicamGroups?: MulticamGroup[]
}

export interface ProjectDoc {
  version: number
  assets: MediaAsset[]
  mediaFolders?: MediaFolder[]
  timelines: Timeline[]
  activeTimelineId: string
  designStyle?: Record<string, unknown> | null
}

export function activeTimeline(doc: ProjectDoc): Timeline {
  return doc.timelines.find((t) => t.id === doc.activeTimelineId) ?? doc.timelines[0]
}

export function defaultProject(): ProjectDoc {
  const tl: Timeline = { id: 'tl1', name: '时间线 1', order: 0, fps: 30, items: [], transitions: [], markers: [], captions: null }
  return { version: 1, assets: [], timelines: [tl], activeTimelineId: 'tl1' }
}
