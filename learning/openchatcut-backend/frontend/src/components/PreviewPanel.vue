<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { activeTimeline, type ProjectDoc, type TimelineItem } from '../editor/types'

const props = defineProps<{ project: ProjectDoc; playing: boolean; playhead: number }>()
const emit = defineEmits<{ (e: 'update:playing', v: boolean): void; (e: 'update:playhead', v: number): void }>()

const videoEl = ref<HTMLVideoElement | null>(null)
const audioEl = ref<HTMLAudioElement | null>(null)

const tl = computed(() => activeTimeline(props.project))
const fps = computed(() => tl.value?.fps ?? 30)

const videoClips = computed(() =>
  tl.value.items.filter((i) => i.track === 'V1' && i.kind === 'video' && i.src).sort((a, b) => a.startFrame - b.startFrame),
)
const audioClips = computed(() =>
  tl.value.items.filter((i) => i.track === 'A1' && i.src).sort((a, b) => a.startFrame - b.startFrame),
)
const overlayItems = computed(() =>
  tl.value.items
    .filter((i) => i.track !== 'V1' && ['image', 'gif', 'svg'].includes(i.kind) && i.src)
    .sort((a, b) => a.startFrame - b.startFrame),
)

const totalFrames = computed(() => {
  let m = 0
  for (const it of tl.value.items) m = Math.max(m, it.startFrame + it.durationInFrames)
  return m
})

const durationSec = computed(() => totalFrames.value / fps.value)

function timeLabel(frames: number): string {
  const s = frames / fps.value
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`
}

function activeClip(clips: TimelineItem[], frame: number): TimelineItem | undefined {
  return clips.find((c) => frame >= c.startFrame && frame < c.startFrame + c.durationInFrames)
}

function activeAtFrame(item: TimelineItem, frame: number): boolean {
  return frame >= item.startFrame && frame < item.startFrame + item.durationInFrames
}

function positionClass(position: string | null | undefined, fallback = 'bc'): string {
  const valid = ['tl', 'tc', 'tr', 'ml', 'mc', 'mr', 'bl', 'bc', 'br']
  return `position-${valid.includes(position ?? '') ? position : fallback}`
}

function overlayStyle(item: TimelineItem): Record<string, string> {
  const transform = item.transform ?? {}
  const scale = transform.scale ?? 1
  const scaleX = transform.scaleX ?? scale
  const scaleY = transform.scaleY ?? scale
  const x = transform.x ?? 0
  const y = transform.y ?? 0
  const style: Record<string, string> = {
    left: `calc(50% + ${x}%)`,
    top: `calc(50% + ${y}%)`,
    transform: `translate(-50%, -50%) scale(${scaleX}, ${scaleY}) rotate(${transform.rotation ?? 0}deg)`,
    opacity: String(transform.opacity ?? 1),
  }
  // 已知素材尺寸时，用画布百分比预览，避免不同窗口大小下 Logo 跳动。
  if (item.width && tl.value.width) style.width = `${(item.width / tl.value.width) * 100}%`
  return style
}

const activeCaption = computed(() => {
  const captions = tl.value.captions
  if (!captions || !captions.enabled || tl.value.captionsHidden) return null
  return captions.items.find((cue) => props.playhead >= cue.startFrame && props.playhead < cue.endFrame) ?? null
})

const captionStyle = computed(() => {
  const captions = tl.value.captions
  return {
    fontSize: `${captions?.fontSize ?? 42}px`,
    color: captions?.color ?? '#ffffff',
    WebkitTextStroke: `${captions?.outlineWidth ?? 2}px ${captions?.outlineColor ?? '#000000'}`,
    textShadow: `0 0 ${captions?.outlineWidth ?? 2}px ${captions?.outlineColor ?? '#000000'}`,
  }
})

const watermarkStyle = computed(() => ({
  opacity: String(tl.value.watermark?.opacity ?? 0.7),
  fontSize: `${tl.value.watermark?.fontSize ?? 28}px`,
  color: tl.value.watermark?.color ?? '#ffffff',
  '--overlay-margin': `${tl.value.watermark?.margin ?? 24}px`,
}))

// ── 播放：播放头为墙钟主时钟，<video>/<audio> 跟随 ─────────────────────────

let rafId = 0
let lastTs = 0
let loadedVideoId: string | null = null
let loadedAudioId: string | null = null

function syncVideo(frame: number): void {
  const v = videoEl.value
  if (!v) return
  const clip = activeClip(videoClips.value, frame)
  if (!clip) {
    loadedVideoId = null
    v.pause()
    v.removeAttribute('src')
    v.load()
    return
  }
  const t = ((clip.srcInFrame ?? 0) + (frame - clip.startFrame)) / fps.value
  if (loadedVideoId !== clip.id) {
    loadedVideoId = clip.id
    v.src = clip.src ?? ''
    const onMeta = () => {
      v.currentTime = t
      v.removeEventListener('loadedmetadata', onMeta)
    }
    v.addEventListener('loadedmetadata', onMeta)
    v.muted = true
    v.play().catch(() => {})
  } else if (Math.abs(v.currentTime - t) > 0.35) {
    v.currentTime = t
  }
}

function syncAudio(frame: number): void {
  const a = audioEl.value
  if (!a) return
  const clip = activeClip(audioClips.value, frame)
  if (!clip) {
    loadedAudioId = null
    a.pause()
    a.removeAttribute('src')
    return
  }
  if (loadedAudioId !== clip.id) {
    loadedAudioId = clip.id
    a.src = clip.src ?? ''
    a.volume = clip.volume ?? 1
    a.currentTime = ((clip.srcInFrame ?? 0) + (frame - clip.startFrame)) / fps.value
    a.play().catch(() => {})
  }
}

function tick(now: number): void {
  if (!props.playing) return
  const dt = lastTs ? (now - lastTs) / 1000 : 0
  lastTs = now
  const next = props.playhead + dt * fps.value
  if (next >= totalFrames.value) {
    emit('update:playhead', totalFrames.value)
    stop()
    return
  }
  emit('update:playhead', next)
  syncVideo(next)
  syncAudio(next)
  rafId = requestAnimationFrame(tick)
}

function toggle(): void {
  emit('update:playing', !props.playing)
}

function stop(): void {
  emit('update:playing', false)
}

watch(
  () => props.playing,
  (p) => {
    if (p) {
      lastTs = 0
      loadedVideoId = null
      loadedAudioId = null
      syncVideo(props.playhead)
      syncAudio(props.playhead)
      rafId = requestAnimationFrame(tick)
    } else {
      cancelAnimationFrame(rafId)
      videoEl.value?.pause()
      audioEl.value?.pause()
    }
  },
)

// 非播放态下拖动时间线时刷新预览帧
watch(
  () => props.playhead,
  (frame) => {
    if (!props.playing) {
      syncVideo(frame)
      syncAudio(frame)
    }
  },
)

onUnmounted(() => cancelAnimationFrame(rafId))
</script>

<template>
  <div class="preview">
    <div class="preview-head">
      <h2>预览</h2>
      <button class="play" @click="toggle">{{ playing ? '暂停' : '播放' }}</button>
      <span class="preview-time">{{ timeLabel(playhead) }} / {{ timeLabel(totalFrames) }}</span>
    </div>
    <div class="preview-stage" :style="{ aspectRatio: `${tl.width ?? 16} / ${tl.height ?? 9}` }">
      <video ref="videoEl" class="preview-video" muted playsinline></video>
      <img
        v-for="item in overlayItems"
        v-show="activeAtFrame(item, playhead)"
        :key="item.id"
        class="preview-overlay"
        :src="item.src ?? ''"
        :alt="item.name"
        :style="overlayStyle(item)"
      />
      <div
        v-if="tl.watermark?.enabled && tl.watermark.text"
        class="preview-watermark"
        :class="positionClass(tl.watermark.position, 'br')"
        :style="watermarkStyle"
      >{{ tl.watermark.text }}</div>
      <div
        v-if="activeCaption"
        class="preview-caption"
        :class="positionClass(tl.captions?.position, 'bc')"
        :style="captionStyle"
      >{{ activeCaption.text }}</div>
      <audio ref="audioEl"></audio>
      <div v-if="!videoClips.length" class="empty">（无视频片段可预览）</div>
    </div>
    <input
      class="preview-scrub"
      type="range"
      :min="0"
      :max="Math.max(totalFrames, 1)"
      :value="playhead"
      @input="emit('update:playhead', Number(($event.target as HTMLInputElement).value))"
    />
    <div class="preview-meta">{{ durationSec.toFixed(1) }}s · {{ videoClips.length }} 视频片段 · {{ audioClips.length }} 音频片段</div>
  </div>
</template>
