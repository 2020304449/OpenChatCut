<script setup lang="ts">
import { computed } from 'vue'
import type { ProjectDoc, MediaAsset } from '../api'

const props = defineProps<{ project: ProjectDoc }>()

const folders = computed(() => props.project.mediaFolders ?? [])
const assets = computed(() => props.project.assets ?? [])

const KIND_LABEL: Record<string, string> = {
  video: '视频',
  image: '图片',
  audio: '音频',
  gif: 'GIF',
  svg: 'SVG',
  text: '文字',
  solid: '纯色',
  'motion-graphic': '动效',
  sequence: '序列',
}

function kindLabel(kind: string): string {
  return KIND_LABEL[kind] ?? kind
}

function folderName(id: string | null | undefined): string {
  if (!id) return ''
  return folders.value.find((f) => f.id === id)?.name ?? ''
}

function dims(a: MediaAsset): string {
  if (a.width != null && a.height != null) return `${a.width}×${a.height}`
  return ''
}

function duration(a: MediaAsset): string {
  if (a.durationInFrames == null) return ''
  return `${a.durationInFrames}帧`
}
</script>

<template>
  <div class="assets">
    <div class="assets-head">
      <h2>素材池</h2>
      <span class="count">{{ assets.length }} 项{{ folders.length ? ' · ' + folders.length + ' 文件夹' : '' }}</span>
    </div>
    <div v-if="!assets.length" class="empty">（暂无素材）</div>
    <div v-else class="asset-grid">
      <div v-for="a in assets" :key="a.id" class="asset" :title="a.src || a.name">
        <div class="asset-top">
          <span class="kind" :class="a.kind">{{ kindLabel(a.kind) }}</span>
          <span v-if="a.favorite" class="fav">★</span>
        </div>
        <div class="asset-name">{{ a.name }}</div>
        <div class="asset-meta">
          <span v-if="dims(a)">{{ dims(a) }}</span>
          <span v-if="duration(a)">{{ duration(a) }}</span>
          <span v-if="folderName(a.folderId)">{{ folderName(a.folderId) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
