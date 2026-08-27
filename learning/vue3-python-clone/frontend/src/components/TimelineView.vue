<script setup lang="ts">
import type { Timeline } from '../api'

defineProps<{ timeline: Timeline }>()

const PX_PER_SEC = 40
</script>

<template>
  <div class="timeline">
    <h2>时间线</h2>
    <div v-if="!timeline.tracks.length" class="empty">（空）</div>
    <div v-for="track in timeline.tracks" :key="track.id" class="track">
      <div class="track-label">{{ track.id }} · {{ track.kind }}</div>
      <div class="track-lane">
        <div
          v-for="clip in track.clips"
          :key="clip.id"
          class="clip"
          :class="clip.kind"
          :style="{
            left: clip.start * PX_PER_SEC + 'px',
            width: Math.max(clip.duration * PX_PER_SEC, 20) + 'px',
          }"
        >
          {{ clip.label }}
        </div>
      </div>
    </div>
  </div>
</template>
