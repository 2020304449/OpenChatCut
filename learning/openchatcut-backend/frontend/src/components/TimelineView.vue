<script setup lang="ts">
import { computed } from 'vue'
import { activeTimeline, type ProjectDoc, type Clip } from '../api'

const props = defineProps<{ project: ProjectDoc }>()

const PX_PER_SEC = 40

const timeline = computed(() => activeTimeline(props.project))

// 按轨道分组 items
const tracks = computed(() => {
  const tl = timeline.value
  if (!tl) return []
  const map = new Map<string, Clip[]>()
  for (const item of tl.items) {
    if (!map.has(item.track)) map.set(item.track, [])
    map.get(item.track)!.push(item)
  }
  return [...map.entries()].map(([id, clips]) => ({ id, clips }))
})

function leftPx(clip: Clip, fps: number): number {
  return (clip.startFrame / fps) * PX_PER_SEC
}

function widthPx(clip: Clip, fps: number): number {
  return Math.max((clip.durationInFrames / fps) * PX_PER_SEC, 20)
}

function sec(frames: number, fps: number): string {
  return (frames / fps).toFixed(2) + 's'
}
</script>

<template>
  <div class="timeline">
    <h2>时间线{{ timeline ? ' · ' + timeline.name : '' }}</h2>
    <div v-if="!timeline || !timeline.items.length" class="empty">（空时间线）</div>
    <template v-else>
      <div v-for="track in tracks" :key="track.id" class="track">
        <div class="track-label">{{ track.id }}</div>
        <div class="track-lane">
          <div
            v-for="clip in track.clips"
            :key="clip.id"
            class="clip"
            :class="clip.kind"
            :style="{
              left: leftPx(clip, timeline.fps) + 'px',
              width: widthPx(clip, timeline.fps) + 'px',
            }"
            :title="`${clip.name} (${sec(clip.startFrame, timeline.fps)} ~ ${sec(clip.startFrame + clip.durationInFrames, timeline.fps)})`"
          >
            {{ clip.name }}
          </div>
        </div>
      </div>
      <div v-if="timeline.transitions.length" class="track-label">
        转场：{{ timeline.transitions.map((t) => t.transType).join(', ') }}
      </div>
      <div v-if="timeline.captions && timeline.captions.items.length" class="track-label">
        字幕：{{ timeline.captions.items.map((c) => c.text).join(' / ') }}
      </div>
    </template>
  </div>
</template>
