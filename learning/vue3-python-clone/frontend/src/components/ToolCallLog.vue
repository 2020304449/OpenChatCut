<script setup lang="ts">
import type { ToolCallEvent } from '../api'

defineProps<{ calls: ToolCallEvent[] }>()
</script>

<template>
  <div class="tool-log">
    <h2>工具调用</h2>
    <div v-if="!calls.length" class="empty">（尚未调用工具）</div>
    <div v-for="(c, i) in calls" :key="i" class="tool-entry">
      <div class="tool-name">{{ c.name }}</div>
      <pre class="tool-args">{{ JSON.stringify(c.args, null, 2) }}</pre>
      <div v-if="c.result" class="tool-result" :class="{ ok: c.result.ok }">
        {{ JSON.stringify(c.result) }}
      </div>
    </div>
  </div>
</template>
