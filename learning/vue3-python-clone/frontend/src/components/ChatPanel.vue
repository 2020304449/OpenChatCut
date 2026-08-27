<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  messages: { role: string; text: string }[]
  busy: boolean
}>()

const emit = defineEmits<{ (e: 'send', message: string): void }>()

const input = ref('')

function submit() {
  const m = input.value.trim()
  if (!m) return
  emit('send', m)
  input.value = ''
}
</script>

<template>
  <div class="chat">
    <div class="messages">
      <div v-for="(m, i) in messages" :key="i" :class="['msg', m.role]">
        <template v-if="m.text">{{ m.text }}</template>
        <span v-else class="typing">…</span>
      </div>
    </div>
    <div class="input-row">
      <input
        v-model="input"
        placeholder="描述你的剪辑意图，例如：加两个片段和一个字幕"
        :disabled="busy"
        @keyup.enter="submit"
      />
      <button :disabled="busy" @click="submit">发送</button>
    </div>
  </div>
</template>
