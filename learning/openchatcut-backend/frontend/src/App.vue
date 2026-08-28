<script setup lang="ts">
import { ref } from 'vue'
import AssetPanel from './components/AssetPanel.vue'
import ChatPanel from './components/ChatPanel.vue'
import TimelineView from './components/TimelineView.vue'
import ToolCallLog from './components/ToolCallLog.vue'
import { useEditor } from './editor/store'
import { defaultProject } from './editor/types'
import { executeTool } from './agent/tools'
import { createAndStartRun, type ToolCallEvent } from './bridge/serverRun'

const { doc, commands, canUndo, canRedo } = useEditor(defaultProject())

const messages = ref<{ role: 'user' | 'assistant'; text: string }[]>([])
const toolCalls = ref<ToolCallEvent[]>([])
const busy = ref(false)

// 内部 run 的 ctx 直接落在真库 store（editor.commands），executeTool 派发 action → 本地 reducer 更新 doc。
const ctx = { getDoc: () => doc.value, commands }

async function send(message: string) {
  messages.value.push({ role: 'user', text: message })
  toolCalls.value = []
  busy.value = true
  messages.value.push({ role: 'assistant', text: '' })

  try {
    await createAndStartRun(message, doc.value, executeTool, ctx, {
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
      onState() {
        // browser 权威：doc 已由 executeTool 经本地 reducer 更新，server 的 state 事件无需回填。
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

function undo() {
  commands.undo()
}

function redo() {
  commands.redo()
}
</script>

<template>
  <div class="app">
    <header class="topbar">
      <h1>OpenChatCut 后端 · Agent 测试台</h1>
      <div class="actions">
        <button class="undo" :disabled="busy || !canUndo" @click="undo">撤销</button>
        <button class="undo" :disabled="busy || !canRedo" @click="redo">重做</button>
      </div>
    </header>
    <main class="layout">
      <section class="left">
        <ChatPanel :messages="messages" :busy="busy" @send="send" />
        <AssetPanel :project="doc" />
      </section>
      <section class="right">
        <TimelineView :project="doc" />
        <ToolCallLog :calls="toolCalls" />
      </section>
    </main>
  </div>
</template>
