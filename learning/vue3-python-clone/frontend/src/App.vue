<script setup lang="ts">
import { onMounted, ref } from 'vue'
import ChatPanel from './components/ChatPanel.vue'
import TimelineView from './components/TimelineView.vue'
import ToolCallLog from './components/ToolCallLog.vue'
import { getState, streamChat, undo as undoApi, type Timeline, type ToolCallEvent } from './api'

const timeline = ref<Timeline>({ tracks: [] })
const messages = ref<{ role: 'user' | 'assistant'; text: string }[]>([])
const toolCalls = ref<ToolCallEvent[]>([])
const busy = ref(false)

onMounted(async () => {
  timeline.value = await getState()
})

async function send(message: string) {
  messages.value.push({ role: 'user', text: message })
  toolCalls.value = []
  busy.value = true
  messages.value.push({ role: 'assistant', text: '' })

  try {
    await streamChat(message, {
      onAssistant(text) {
        const last = messages.value[messages.value.length - 1]
        last.text += text
      },
      onToolCall(name, args) {
        toolCalls.value.push({ name, args })
      },
      onToolResult(result) {
        const last = toolCalls.value[toolCalls.value.length - 1]
        if (last) last.result = result
      },
      onState(tl) {
        timeline.value = tl
      },
      onError(msg) {
        messages.value[messages.value.length - 1].text = '出错：' + msg
        busy.value = false
      },
      onDone() {
        busy.value = false
      },
    })
  } catch (e) {
    busy.value = false
    messages.value[messages.value.length - 1].text = '请求失败：' + (e as Error).message
  }
}

async function undo() {
  timeline.value = await undoApi()
}
</script>

<template>
  <div class="app">
    <header class="topbar">
      <h1>AI 剪辑智能体 · 最小克隆</h1>
      <button class="undo" :disabled="busy" @click="undo">撤销</button>
    </header>
    <main class="layout">
      <section class="left">
        <ChatPanel :messages="messages" :busy="busy" @send="send" />
      </section>
      <section class="right">
        <TimelineView :timeline="timeline" />
        <ToolCallLog :calls="toolCalls" />
      </section>
    </main>
  </div>
</template>
