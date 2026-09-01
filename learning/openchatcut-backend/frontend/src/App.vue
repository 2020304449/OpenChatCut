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
import { ProposalCoordinator } from './agent/proposal'
import { createAndStreamRun, type ToolCallEvent } from './bridge/serverRun'
import { loadProject, saveProject } from './bridge/project'
import { activeTimeline } from './editor/types'

const { doc, commands, canUndo, canRedo, reset, commitProposal } = useEditor(demoProject())

const messages = ref<{ role: 'user' | 'assistant'; text: string }[]>([])
const toolCalls = ref<ToolCallEvent[]>([])
const busy = ref(false)
const playing = ref(false)
const playhead = ref(0)

const proposalCoordinator = new ProposalCoordinator({
  getDoc: () => doc.value,
  commitProposal,
  executeTool,
})

// 多项目：projectId 走 URL 参数；无则生成不超过 20 位的十进制 ID 写回 URL。
// 以字符串保存和传输，避免 bigint 项目 ID 在 JavaScript Number 中发生精度丢失。
function resolveProjectId(): string {
  const params = new URLSearchParams(window.location.search)
  const id = params.get('projectId')
  if (id) return id
  const nid = `${Date.now()}${Math.floor(Math.random() * 1000).toString().padStart(3, '0')}`.slice(0, 20)
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
    await createAndStreamRun({ message, projectId, state: doc.value, proposalCoordinator, handlers: {
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
        // 浏览器是工程权威；state 事件只用于展示服务端状态，不能覆盖本地未保存编辑。
      },
      async onApprovedSideEffect(name, args) {
        if (name !== 'submit_export') return { ok: false, error: `不支持的副作用工具：${name}` }
        // 审批后的顺序固定为 save -> export，避免渲染读取到旧工程快照。
        await saveProject(projectId, doc.value, true)
        return exportProject(args)
      },
      onError(msg) {
        messages.value[messages.value.length - 1].text = '出错：' + msg
        busy.value = false
      },
      onDone() {
        busy.value = false
      },
    }})
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
    await saveProject(projectId, doc.value, true)
    const result = await exportProject({ format: 'video', codec: 'h264', fps: activeTimeline(doc.value).fps, name: 'demo' })
    if (result.url) window.open(String(result.url), '_blank')
  } catch (e) {
    alert('导出失败：' + (e as Error).message)
  } finally {
    exporting.value = false
  }
}

async function exportProject(args: Record<string, unknown>): Promise<Record<string, unknown>> {
  const format = args.format === 'audio' ? 'audio' : 'video'
  const codec = typeof args.codec === 'string' ? args.codec : (format === 'audio' ? 'mp3' : 'h264')
  const fps = typeof args.fps === 'number' ? args.fps : activeTimeline(doc.value).fps
  const name = typeof args.name === 'string' && args.name ? args.name : 'demo'
  const response = await fetch('/api/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    // 导出接口只接受五字段；工程由 jimanweb 按当前用户 projectId 读取。
    body: JSON.stringify({ projectId, format, codec, fps, name }),
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: string; message?: string } | null
    throw new Error(body?.error ?? body?.message ?? `HTTP ${response.status}`)
  }
  const payload = (await response.clone().json().catch(() => null)) as Record<string, unknown> | null
  if (payload) {
    // jimanweb 统一 ResultResponse 时取 data；兼容旧网关直返 {ok,url}。
    const data = payload.data && typeof payload.data === 'object' ? payload.data as Record<string, unknown> : payload
    return data
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${name}.${format === 'audio' ? codec : 'mp4'}`
  a.click()
  URL.revokeObjectURL(url)
  return { ok: true, name }
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
