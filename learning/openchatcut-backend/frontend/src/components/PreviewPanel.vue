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
    <div class="preview-stage">
      <video ref="videoEl" class="preview-video" muted playsinline></video>
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
