<script setup lang="ts">
import { computed } from 'vue'
import { activeTimeline, type ProjectDoc, type Clip, type TransitionItem } from '../api'

const props = defineProps<{ project: ProjectDoc }>()

const PX_PER_SEC = 40
const GUTTER = 64
const DEFAULT_TRACK_ORDER = ['V2', 'V1', 'A1', 'A2']

const timeline = computed(() => activeTimeline(props.project))
const fps = computed(() => timeline.value?.fps ?? 30)

const trackOrder = computed<string[]>(() => {
  const tl = timeline.value
  if (!tl) return []
  const base = tl.trackOrder && tl.trackOrder.length ? tl.trackOrder : DEFAULT_TRACK_ORDER
  const extra = new Set<string>()
  for (const it of tl.items) if (!base.includes(it.track)) extra.add(it.track)
  return [...base, ...extra]
})

interface TrackRow {
  id: string
  name?: string | null
  muted?: boolean
  locked?: boolean
  clips: Clip[]
}

const tracks = computed<TrackRow[]>(() => {
  const tl = timeline.value
  if (!tl) return []
  return trackOrder.value.map((id) => ({
    id,
    name: tl.tracks?.[id]?.name,
    muted: tl.tracks?.[id]?.muted,
    locked: tl.tracks?.[id]?.locked,
    clips: tl.items.filter((it) => it.track === id).sort((a, b) => a.startFrame - b.startFrame),
  }))
})

const transitionByClip = computed<Record<string, TransitionItem>>(() => {
  const map: Record<string, TransitionItem> = {}
  for (const t of timeline.value?.transitions ?? []) map[t.incomingItemId] = t
  return map
})

const totalFrames = computed(() => {
  const tl = timeline.value
  if (!tl) return 0
  let m = 0
  for (const it of tl.items) m = Math.max(m, it.startFrame + it.durationInFrames)
  for (const c of tl.captions?.items ?? []) m = Math.max(m, c.endFrame)
  for (const mk of tl.markers) {
    if (mk.frame != null) m = Math.max(m, mk.frame)
    if (mk.endFrame != null) m = Math.max(m, mk.endFrame)
  }
  for (const t of tl.transitions) {
    const clip = tl.items.find((i) => i.id === t.incomingItemId)
    if (clip) m = Math.max(m, clip.startFrame + (t.durationInFrames ?? 0))
  }
  return m
})

const contentWidth = computed(() =>
  Math.max((totalFrames.value / fps.value) * PX_PER_SEC + 120, 480),
)

const rulerTicks = computed(() => {
  const step = Math.max(1, fps.value)
  const ticks: { frame: number; label: string }[] = []
  for (let f = 0; f <= totalFrames.value; f += step) {
    ticks.push({ frame: f, label: `${Math.round(f / fps.value)}s` })
  }
  return ticks
})

function xPx(frame: number): number {
  return (frame / fps.value) * PX_PER_SEC
}
function wPx(frames: number): number {
  return Math.max((frames / fps.value) * PX_PER_SEC, 4)
}
function sec(frames: number): string {
  return (frames / fps.value).toFixed(2) + 's'
}
</script>

<template>
  <div class="timeline">
    <div class="timeline-head">
      <h2>时间线{{ timeline ? ' · ' + timeline.name : '' }}</h2>
      <span v-if="timeline" class="meta">
        {{ timeline.width }}×{{ timeline.height }} · {{ timeline.fps }}fps · 全长 {{ sec(totalFrames) }}
      </span>
    </div>

    <div
      v-if="!timeline || (!timeline.items.length && !(timeline.captions?.items.length) && !timeline.markers.length)"
      class="empty"
    >
      （空时间线）
    </div>

    <div v-else class="timeline-scroll">
      <div class="timeline-inner" :style="{ width: GUTTER + contentWidth + 'px' }">
        <!-- 刻度尺 -->
        <div class="row ruler-row">
          <div class="gutter"></div>
          <div class="lane ruler" :style="{ width: contentWidth + 'px' }">
            <div v-for="t in rulerTicks" :key="t.frame" class="tick" :style="{ left: xPx(t.frame) + 'px' }">
              <span>{{ t.label }}</span>
            </div>
          </div>
        </div>

        <!-- 轨道 -->
        <div v-for="track in tracks" :key="track.id" class="row">
          <div class="gutter">
            {{ track.name || track.id }}
            <span v-if="track.muted" class="flag">M</span>
            <span v-if="track.locked" class="flag">L</span>
          </div>
          <div class="lane" :style="{ width: contentWidth + 'px' }">
            <div
              v-for="clip in track.clips"
              :key="clip.id"
              class="clip"
              :class="clip.kind"
              :style="{ left: xPx(clip.startFrame) + 'px', width: wPx(clip.durationInFrames) + 'px' }"
              :title="`${clip.name} (${sec(clip.startFrame)} ~ ${sec(clip.startFrame + clip.durationInFrames)})`"
            >
              <span class="clip-name">{{ clip.name }}</span>
              <span v-if="transitionByClip[clip.id]" class="transition">
                ⟡ {{ transitionByClip[clip.id].transType }}
              </span>
            </div>
          </div>
        </div>

        <!-- 字幕轨 -->
        <div v-if="timeline.captions && timeline.captions.items.length" class="row caption-row">
          <div class="gutter">字幕</div>
          <div class="lane" :style="{ width: contentWidth + 'px' }">
            <div
              v-for="(c, i) in timeline.captions.items"
              :key="i"
              class="caption-cue"
              :style="{ left: xPx(c.startFrame) + 'px', width: wPx(c.endFrame - c.startFrame) + 'px' }"
              :title="`${sec(c.startFrame)} ~ ${sec(c.endFrame)}${c.speakerId ? ' · ' + c.speakerId : ''}`"
            >
              {{ c.text }}
            </div>
          </div>
        </div>

        <!-- 标记轨 -->
        <div v-if="timeline.markers.length" class="row marker-row">
          <div class="gutter">标记</div>
          <div class="lane" :style="{ width: contentWidth + 'px' }">
            <template v-for="m in timeline.markers" :key="m.id">
              <div
                v-if="m.frame != null"
                class="marker-point"
                :style="{ left: xPx(m.frame) + 'px', background: m.color || '#f59e0b' }"
                :title="m.name"
              >
                <span class="marker-name">{{ m.name }}</span>
              </div>
              <div
                v-else
                class="marker-range"
                :style="{
                  left: xPx(m.startFrame ?? 0) + 'px',
                  width: wPx((m.endFrame ?? 0) - (m.startFrame ?? 0)) + 'px',
                  borderColor: m.color || '#f59e0b',
                }"
                :title="m.name"
              >
                {{ m.name }}
              </div>
            </template>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
