<script setup lang="ts">
import { ref } from 'vue'
import type { ToolCallEvent } from '../bridge/serverRun'

defineProps<{ calls: ToolCallEvent[] }>()

const open = ref(false)
</script>

<template>
  <button class="tool-toggle" @click="open = true">
    工具调用 <span v-if="calls.length" class="tool-badge">{{ calls.length }}</span>
  </button>

  <Teleport to="body">
    <div v-if="open" class="tool-modal" @click.self="open = false">
      <div class="tool-modal-box">
        <div class="tool-modal-head">
          <h2>工具调用</h2>
          <button class="tool-modal-close" @click="open = false">✕</button>
        </div>
        <div class="tool-modal-body">
          <div v-if="!calls.length" class="empty">（尚未调用工具）</div>
          <div v-for="(c, i) in calls" :key="i" class="tool-entry">
            <div class="tool-name">{{ c.name }}</div>
            <pre class="tool-args">{{ JSON.stringify(c.args, null, 2) }}</pre>
            <div v-if="c.result" class="tool-result" :class="{ ok: c.result.ok }">
              {{ JSON.stringify(c.result) }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
