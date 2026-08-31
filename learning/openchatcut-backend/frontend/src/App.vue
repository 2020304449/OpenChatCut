<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import AssetPanel from './components/AssetPanel.vue'
import ChatPanel from './components/ChatPanel.vue'
import PreviewPanel from './components/PreviewPanel.vue'
import TimelineView from './components/TimelineView.vue'
import ToolCallLog from './components/ToolCallLog.vue'
import { useEditor } from './editor/store'
import { demoProject } from './editor/demo'
import { executeTool } from './agent/tools'
import { createAndStartRun, type ToolCallEvent } from './bridge/serverRun'
import { loadProject, saveProject } from './bridge/project'

const { doc, commands, canUndo, canRedo, reset } = useEditor(demoProject())

const messages = ref<{ role: 'user' | 'assistant'; text: string }[]>([])
const toolCalls = ref<ToolCallEvent[]>([])
const busy = ref(false)
const playing = ref(false)
const playhead = ref(0)

// 内部 run 的 ctx 直接落在真库 store（editor.commands），executeTool 派发 action → 本地 reducer 更新 doc。
const ctx = { getDoc: () => doc.value, commands }

// 多项目：projectId 走 URL 参数；无则生成 UUID 写回 URL（刷新/分享链接可定位到同一项目）。
function resolveProjectId(): string {
  const params = new URLSearchParams(window.location.search)
  const id = params.get('projectId')
  if (id) return id
  const nid = crypto.randomUUID()
  const url = new URL(window.location.href)
  url.searchParams.set('projectId', nid)
  history.replaceState(null, '', url.toString())
  return nid
}
const projectId = resolveProjectId()

// 项目持久化：启动加载存档（无存档回退 demo），编辑后防抖自动保存。
const hydrated = ref(false)

onMounted(async () => {
  try {
    const saved = await loadProject(projectId)
    if (saved) reset(saved)
  } catch (e) {
    console.warn('加载项目失败', e)
  } finally {
    hydrated.value = true
  }
})

let saveTimer: ReturnType<typeof setTimeout> | undefined
watch(doc, () => {
  if (!hydrated.value) return
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveProject(projectId, doc.value).catch((e) => console.warn('保存项目失败', e))
  }, 500)
})

// 审批弹框：高风险工具挂起，等用户 approve/reject。
const pendingApproval = ref<{ name: string; args: Record<string, unknown>; resolve: (d: 'approved' | 'rejected') => void } | null>(null)

function requestApproval(name: string, args: Record<string, unknown>): Promise<'approved' | 'rejected'> {
  return new Promise((resolve) => {
    pendingApproval.value = { name, args, resolve }
  })
}

function decideApproval(decision: 'approved' | 'rejected') {
  pendingApproval.value?.resolve(decision)
  pendingApproval.value = null
}

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
      onApprovalRequest(name, args) {
        return requestApproval(name, args)
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

const exporting = ref(false)

async function exportVideo() {
  exporting.value = true
  try {
    const res = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state: doc.value, name: 'demo', format: 'video', codec: 'h264' }),
    })
    if (!res.ok) {
      const body = (await res.json().catch(() => null)) as { error?: string } | null
      alert('导出失败：' + (body?.error ?? res.status))
      return
    }

    // 后端 OSS 模式返回 { ok, url, name }；无 OSS 时降级回传视频字节流。
    // 用 clone + try-json 判定，不依赖 Content-Type（兼容 jimanweb 旧版本可能误标 video/*）。
    const data = (await res.clone().json().catch(() => null)) as { ok?: boolean; url?: string; name?: string } | null
    if (data?.url) {
      window.open(data.url, '_blank')
      return
    }

    // 降级：视频字节流
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'demo.mp4'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    alert('导出失败：' + (e as Error).message)
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <div class="app">
    <header class="topbar">
      <h1>OpenChatCut 后端 · Agent 测试台</h1>
      <div class="actions">
        <ToolCallLog :calls="toolCalls" />
        <button class="undo" :disabled="busy || !canUndo" @click="undo">撤销</button>
        <button class="undo" :disabled="busy || !canRedo" @click="redo">重做</button>
        <button class="undo" :disabled="exporting" @click="exportVideo">{{ exporting ? '导出中…' : '导出视频' }}</button>
      </div>
    </header>
    <main class="layout">
      <section class="left">
        <ChatPanel :messages="messages" :busy="busy" @send="send" />
        <AssetPanel :project="doc" />
      </section>
      <section class="right">
        <PreviewPanel
          :project="doc"
          :playing="playing"
          :playhead="playhead"
          @update:playing="playing = $event"
          @update:playhead="playhead = $event"
        />
        <TimelineView :project="doc" :playhead="playhead" @seek="playhead = $event" />
      </section>
    </main>
    <div v-if="pendingApproval" class="approval-overlay">
      <div class="approval-box">
        <h3>审批请求</h3>
        <p>是否允许执行工具「{{ pendingApproval.name }}」？</p>
        <pre class="approval-args">{{ JSON.stringify(pendingApproval.args, null, 2) }}</pre>
        <div class="approval-actions">
          <button class="approve" @click="decideApproval('approved')">批准</button>
          <button class="reject" @click="decideApproval('rejected')">拒绝</button>
        </div>
      </div>
    </div>
  </div>
</template>
