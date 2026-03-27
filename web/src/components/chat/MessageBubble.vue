<template>
  <div class="flex" :class="msg.role === 'user' ? 'justify-end' : 'justify-start'">
    <div
      class="max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed"
      :class="msg.role === 'user'
        ? 'bg-blue-600 text-white rounded-br-md'
        : 'bg-white text-gray-800 border border-gray-200 rounded-bl-md'"
    >
      <template v-if="msg.role === 'assistant'">
        <!-- 工具卡片（先执行的在上面） -->
        <div v-if="msg.toolCalls?.length" class="not-prose">
          <ToolCallCard
            v-for="(tc, i) in msg.toolCalls"
            :key="i"
            ref="toolCardRefs"
            :info="tc"
            @toggle="$emit('toggleTool', i)"
            @tool-data-change="$emit('toolDataChange')"
          />
        </div>
        <!-- thinking 状态（工具完成后等待 LLM） -->
        <div v-if="msg.thinking" class="flex items-center gap-2 py-2 text-xs text-gray-500">
          <span class="inline-flex gap-1">
            <span class="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" />
            <span class="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce [animation-delay:0.15s]" />
            <span class="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce [animation-delay:0.3s]" />
          </span>
          <span>{{ msg.thinking }}</span>
        </div>
        <!-- 文字内容 -->
        <StreamingText
          v-if="textContent"
          :content="textContent"
          :streaming="streaming"
        />
        <!-- 快捷选项 -->
        <QuickReply
          v-if="quickOptions.length && !streaming"
          :options="quickOptions"
          :disabled="false"
          @select="handleQuickSelect"
        />
        <div v-if="streaming && !msg.content && !msg.toolCalls?.length && !msg.thinking"
          class="flex gap-1 py-1">
          <span class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
          <span class="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0.15s]" />
          <span class="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0.3s]" />
        </div>
      </template>
      <template v-else>
        {{ msg.content }}
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Message } from '../../types'
import StreamingText from './StreamingText.vue'
import ToolCallCard from './ToolCallCard.vue'
import QuickReply from './QuickReply.vue'

const props = defineProps<{ msg: Message; streaming?: boolean }>()
const emit = defineEmits<{ toggleTool: [index: number]; quickReply: [value: string]; toolDataChange: [] }>()

const toolCardRefs = ref<InstanceType<typeof ToolCallCard>[]>([])

const OPTION_RE = /\[\[([^\]]+)\]\]/g

const quickOptions = computed(() => {
  if (!props.msg.content) return []
  const options: string[] = []
  let match: RegExpExecArray | null
  const re = new RegExp(OPTION_RE.source, 'g')
  while ((match = re.exec(props.msg.content)) !== null) {
    options.push(...match[1].split('|').map((s) => s.trim()).filter(Boolean))
  }
  return options
})

const textContent = computed(() => {
  if (!props.msg.content) return ''
  return props.msg.content.replace(OPTION_RE, '').trim()
})

/** 拦截快捷选项点击，"一键加购物车"时附带已勾选的食材清单 */
function handleQuickSelect(value: string) {
  if (value === '一键加购物车') {
    const checkedItems: { name: string; amount: string }[] = []
    for (const card of toolCardRefs.value ?? []) {
      if (card?.getCheckedIngredients) {
        checkedItems.push(...card.getCheckedIngredients())
      }
    }
    if (checkedItems.length) {
      const itemList = checkedItems
        .map((i) => i.amount ? `${i.name}(${i.amount})` : i.name)
        .join('、')
      emit('quickReply', `一键加购物车\n已选食材：${itemList}`)
      return
    }
  }
  emit('quickReply', value)
}
</script>
