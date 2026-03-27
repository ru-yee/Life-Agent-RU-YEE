<template>
  <div class="flex flex-col h-full">
    <!-- Error toast -->
    <div
      v-if="error"
      class="mx-4 mt-2 px-4 py-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 flex items-center justify-between"
    >
      <span>{{ error }}</span>
      <button class="text-red-500 underline text-xs ml-2" @click="retryLast">{{ t('chat.retry') }}</button>
    </div>

    <!-- Messages -->
    <div ref="scrollContainer" class="flex-1 overflow-y-auto px-4 py-4 space-y-3" @scroll="onScroll">
      <!-- 加载更多 -->
      <div v-if="loadingMore" class="flex justify-center py-2">
        <span class="text-xs text-gray-400 animate-pulse">{{ t('chat.loading.more') }}</span>
      </div>
      <div v-else-if="hasMore" class="flex justify-center py-2">
        <button class="text-xs text-blue-500 hover:text-blue-700" @click="handleLoadMore">{{ t('chat.loading.loadMore') }}</button>
      </div>

      <WelcomeCard
        v-if="messages.length === 0 && openingConfig"
        :config="openingConfig"
        @ask="handleQuickReply"
      />
      <MessageBubble
        v-for="(msg, i) in messages"
        :key="msg.id"
        :msg="msg"
        :streaming="isStreaming && i === messages.length - 1 && msg.role === 'assistant'"
        @toggle-tool="toggleTool(msg.id, $event)"
        @quick-reply="handleQuickReply"
        @tool-data-change="persistToolData(msg)"
      />
      <div ref="scrollAnchor" />
    </div>

    <!-- Input -->
    <div class="border-t border-gray-200 bg-white px-4 py-3">
      <form class="flex gap-2" @submit.prevent="handleSend">
        <button
          v-if="messages.length > 0"
          type="button"
          class="shrink-0 w-10 h-10 rounded-full border border-gray-300 text-gray-400 flex items-center justify-center hover:text-red-500 hover:border-red-300 transition-colors"
          :title="t('chat.input.clear')"
          :disabled="isStreaming"
          @click="handleClear"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd" />
          </svg>
        </button>
        <input
          ref="inputEl"
          v-model="input"
          type="text"
          :placeholder="t('chat.input.placeholder')"
          class="flex-1 rounded-full border border-gray-300 px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          :disabled="isStreaming"
        />
        <button
          type="submit"
          class="shrink-0 w-10 h-10 rounded-full bg-blue-600 text-white flex items-center justify-center disabled:opacity-40"
          :disabled="isStreaming || !input.trim()"
        >
          <span class="text-lg">↑</span>
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSSE } from '../composables/useSSE'
import { fetchOpening, updateMessageToolData } from '../api/chat'
import type { OpeningConfig } from '../api/chat'
import type { Message } from '../types'
import MessageBubble from '../components/chat/MessageBubble.vue'
import WelcomeCard from '../components/chat/WelcomeCard.vue'

const { t } = useI18n()
const { messages, isStreaming, error, hasMore, loadingMore, send, clear, loadHistory, loadMoreHistory } = useSSE()

const openingConfig = ref<OpeningConfig | null>(null)

onMounted(async () => {
  const [_, config] = await Promise.all([
    loadHistory(),
    fetchOpening(),
  ])
  openingConfig.value = config
})

const input = ref('')
const scrollContainer = ref<HTMLElement | null>(null)
const scrollAnchor = ref<HTMLElement | null>(null)
let lastInput = ''

function handleSend() {
  const text = input.value.trim()
  if (!text || isStreaming.value) return
  lastInput = text
  input.value = ''
  send(text)
}

function retryLast() {
  if (lastInput) {
    error.value = null
    send(lastInput)
  }
}

async function handleClear() {
  if (isStreaming.value) return
  await clear()
}

function handleQuickReply(value: string) {
  if (isStreaming.value) return
  input.value = ''
  lastInput = value
  send(value)
}

function toggleTool(msgId: string, toolIdx: number) {
  const idx = messages.value.findIndex((m) => m.id === msgId)
  if (idx === -1) return
  const msg = { ...messages.value[idx] }
  const calls = [...(msg.toolCalls ?? [])]
  calls[toolIdx] = { ...calls[toolIdx], collapsed: !calls[toolIdx].collapsed }
  msg.toolCalls = calls
  const updated = [...messages.value]
  updated[idx] = msg
  messages.value = updated
}

let persistTimer: ReturnType<typeof setTimeout> | null = null
function persistToolData(msg: Message) {
  if (!msg.dbId || !msg.toolCalls?.length) return
  // 防抖 500ms，避免连续勾选多次请求
  if (persistTimer) clearTimeout(persistTimer)
  persistTimer = setTimeout(() => {
    const toolData = msg.toolCalls!.map((tc) => ({
      tool: tc.tool,
      tool_call_id: tc.toolCallId,
      params: tc.params,
      result: tc.result,
    }))
    updateMessageToolData(msg.dbId!, toolData)
  }, 500)
}

async function handleLoadMore() {
  const container = scrollContainer.value
  if (!container) return

  // 记录当前滚动高度，加载后恢复位置
  const prevHeight = container.scrollHeight

  const loaded = await loadMoreHistory()
  if (loaded) {
    await nextTick()
    // 保持用户当前可视位置不跳动
    container.scrollTop = container.scrollHeight - prevHeight
  }
}

function onScroll() {
  const container = scrollContainer.value
  if (!container || loadingMore.value || !hasMore.value) return
  // 滚动到顶部 50px 以内时自动加载
  if (container.scrollTop < 50) {
    handleLoadMore()
  }
}

// auto scroll (only for new messages, not history loading)
watch(
  () => messages.value.length + (messages.value[messages.value.length - 1]?.content.length ?? 0),
  () => {
    if (loadingMore.value) return
    nextTick(() => {
      scrollAnchor.value?.scrollIntoView({ behavior: 'smooth' })
    })
  }
)
</script>
