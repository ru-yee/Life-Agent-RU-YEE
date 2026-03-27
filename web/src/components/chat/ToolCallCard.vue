<template>
  <div class="my-2 rounded-lg border border-gray-200 bg-gray-50 text-sm overflow-hidden">
    <button
      class="flex items-center gap-2 w-full px-3 py-2 text-left hover:bg-gray-100 transition"
      @click="$emit('toggle')"
    >
      <span class="text-base">{{ toolIcon }}</span>
      <span class="font-medium text-gray-700 flex-1">{{ toolLabel }}</span>
      <span v-if="info.streaming" class="text-xs text-blue-500 animate-pulse">{{ t('tool.status.receiving') }}</span>
      <span v-else-if="info.result" class="text-xs" :class="resultSuccess ? 'text-green-600' : 'text-red-500'">
        {{ resultSuccess ? t('tool.status.done') : t('tool.status.failed') }}
      </span>
      <span v-else-if="info.progressStep" class="text-xs text-blue-500 animate-pulse truncate max-w-[180px]">{{ info.progressStep }}</span>
      <span v-else class="text-xs text-yellow-600 animate-pulse">{{ t('tool.status.running') }}</span>
      <span class="text-gray-400 text-xs">{{ info.collapsed ? '▶' : '▼' }}</span>
    </button>

    <div v-if="!info.collapsed" class="px-3 pb-3">
      <!-- 参数摘要 -->
      <div class="flex flex-wrap gap-1.5 mb-2">
        <span
          v-for="tag in paramTags"
          :key="tag"
          class="inline-block px-2 py-0.5 text-xs rounded-full bg-blue-50 text-blue-700"
        >{{ tag }}</span>
      </div>

      <!-- profile_get 画像展示 -->
      <template v-if="info.tool === 'profile_get' && resultData">
        <div class="text-xs text-gray-500 mb-1.5">
          {{ t('tool.profile.collected', { filled: resultData.filled_count ?? 0, total: resultData.total ?? 9 }) }}
          <span v-if="resultData.ready" class="text-green-600 ml-1">{{ t('tool.profile.complete') }}</span>
          <span v-else class="text-orange-500 ml-1">{{ t('tool.profile.incomplete') }}</span>
        </div>
        <div v-if="resultData.filled && Object.keys(resultData.filled).length" class="space-y-1 mb-2">
          <div
            v-for="(val, label) in resultData.filled"
            :key="label"
            class="flex items-center gap-2 bg-white rounded px-2.5 py-1.5 border border-gray-100"
          >
            <span class="text-xs text-gray-500 w-16 shrink-0">{{ label }}</span>
            <span class="text-xs text-gray-800 font-medium">{{ val }}</span>
          </div>
        </div>
        <div v-if="resultData.missing?.length" class="flex flex-wrap gap-1">
          <span
            v-for="item in resultData.missing"
            :key="item"
            class="text-xs px-1.5 py-0.5 rounded bg-orange-50 text-orange-600"
          >{{ item }}</span>
        </div>
      </template>

      <!-- profile_save 保存结果 -->
      <template v-else-if="info.tool === 'profile_save' && resultData">
        <div class="space-y-1">
          <div
            v-for="(val, key) in resultData.profile"
            :key="key"
            class="flex items-center gap-2 bg-white rounded px-2.5 py-1.5 border border-gray-100"
          >
            <span class="text-xs text-gray-500 w-16 shrink-0">{{ slotLabel(String(key)) }}</span>
            <span class="text-xs text-gray-800 font-medium">{{ val }}</span>
            <span
              v-if="resultData.updated_slots?.includes(key)"
              class="text-xs text-green-500 ml-auto"
            >{{ t('tool.shopping.new') }}</span>
          </div>
        </div>
      </template>

      <!-- dish_query 结果 -->
      <template v-else-if="info.tool === 'dish_query' && dishes.length">
        <div class="text-xs text-gray-500 mb-1.5">{{ t('tool.dish.found', { count: resultTotal }) }}</div>
        <div class="space-y-2">
          <div
            v-for="dish in dishes"
            :key="dish.name"
            class="bg-white rounded-lg p-2.5 border border-gray-100"
          >
            <div class="flex items-center justify-between mb-1">
              <span class="font-medium text-gray-800">{{ dish.name }}</span>
              <span v-if="dish.calories" class="text-xs text-orange-600 font-medium">
                {{ Math.round(dish.calories) }} kcal
              </span>
            </div>
            <div class="flex flex-wrap gap-1 mb-1.5">
              <span class="tag tag-type">{{ dish.dish_type }}</span>
              <span class="tag tag-method">{{ dish.cooking_method }}</span>
              <span class="tag tag-flavor">{{ dish.flavor_profile }}</span>
              <span v-if="dish.regional && dish.regional !== '通用家常'" class="tag tag-region">{{ dish.regional }}</span>
            </div>
            <div v-if="dish.main_ingredients?.length" class="text-xs text-gray-500">
              {{ t('tool.dish.ingredients', { list: ingredientNames(dish.main_ingredients) }) }}
            </div>
          </div>
        </div>
      </template>

      <!-- meal_recommend 结果 -->
      <template v-else-if="info.tool === 'meal_recommend' && mealPlan.length">
        <div class="text-xs text-gray-500 mb-1.5">
          {{ t('tool.meal.plan', { days: mealPlan.length, avg: avgCalories }) }}
        </div>
        <div v-for="day in mealPlan" :key="day.day" class="bg-white rounded-lg p-2.5 border border-gray-100 mb-2 last:mb-0">
          <div v-if="mealPlan.length > 1" class="text-xs font-medium text-gray-600 mb-1.5">
            {{ t('tool.meal.day', { day: day.day, cal: day.total_calories }) }}
          </div>
          <div class="space-y-1.5">
            <MealRow icon="🌅" :label="t('tool.meal.breakfast')" :items="day.breakfast" :calories="day.breakfast_calories" />
            <MealRow icon="☀️" :label="t('tool.meal.lunch')" :items="day.lunch" :calories="day.lunch_calories" />
            <MealRow icon="🌙" :label="t('tool.meal.dinner')" :items="day.dinner" :calories="day.dinner_calories" />
          </div>
        </div>
      </template>

      <!-- shopping_list 结果 -->
      <template v-else-if="info.tool === 'shopping_list' && shoppingList">
        <div class="flex items-center justify-between mb-1.5">
          <div class="text-xs text-gray-500">
            {{ t('tool.shopping.total', { count: shoppingList.total_items }) }}
            <span v-if="checkedCount < shoppingList.total_items" class="text-blue-600 ml-1">
              {{ t('tool.shopping.selected', { count: checkedCount }) }}
            </span>
          </div>
          <button
            class="text-xs text-blue-600 hover:text-blue-800"
            @click="toggleAllChecked"
          >{{ allChecked ? t('tool.shopping.unselectAll') : t('tool.shopping.selectAll') }}</button>
        </div>
        <div class="space-y-1.5">
          <div
            v-for="(items, category) in shoppingList.shopping_list"
            :key="category"
            class="bg-white rounded p-2 border border-gray-100"
          >
            <div class="text-xs font-medium text-gray-600 mb-1.5">{{ category }}</div>
            <div class="space-y-1">
              <label
                v-for="item in (items as ShoppingItem[])"
                :key="item.name"
                class="flex items-center gap-2 cursor-pointer group"
              >
                <input
                  type="checkbox"
                  :checked="checkedItems[item.name] !== false"
                  class="w-3.5 h-3.5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  @change="toggleItem(item.name)"
                />
                <span
                  class="text-xs text-gray-700 group-hover:text-gray-900"
                  :class="{ 'line-through text-gray-400': checkedItems[item.name] === false }"
                >{{ item.name }}</span>
                <span v-if="item.amount" class="text-xs text-gray-400">{{ item.amount }}</span>
                <span v-if="item.count > 1" class="text-xs text-gray-400">×{{ t('tool.tag.dishes', { count: item.count }) }}</span>
              </label>
            </div>
          </div>
        </div>
      </template>

      <!-- address_get 收货地址查询 -->
      <template v-else-if="info.tool === 'address_get' && resultData">
        <div v-if="resultData.found" class="bg-white rounded-lg p-2.5 border border-gray-100 space-y-1">
          <div class="flex items-center gap-2">
            <span class="text-xs text-gray-500 w-14 shrink-0">{{ t('tool.address.recipient') }}</span>
            <span class="text-xs text-gray-800 font-medium">{{ resultData.name || t('tool.address.notSet') }}</span>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-xs text-gray-500 w-14 shrink-0">{{ t('tool.address.phone') }}</span>
            <span class="text-xs text-gray-800 font-medium">{{ resultData.phone }}</span>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-xs text-gray-500 w-14 shrink-0">{{ t('tool.address.address') }}</span>
            <span class="text-xs text-gray-800 font-medium">{{ resultData.address }}</span>
          </div>
        </div>
        <div v-else class="text-xs text-orange-500">{{ t('tool.address.noAddress') }}</div>
      </template>

      <!-- address_save 保存收货地址 -->
      <template v-else-if="info.tool === 'address_save' && resultData">
        <div class="bg-white rounded-lg p-2.5 border border-gray-100 space-y-1">
          <div class="flex items-center gap-2">
            <span class="text-xs text-green-600">{{ t('tool.address.saved') }}</span>
          </div>
          <div v-if="resultData.phone" class="flex items-center gap-2">
            <span class="text-xs text-gray-500 w-14 shrink-0">{{ t('tool.address.phone') }}</span>
            <span class="text-xs text-gray-800 font-medium">{{ resultData.phone }}</span>
          </div>
          <div v-if="resultData.address" class="flex items-center gap-2">
            <span class="text-xs text-gray-500 w-14 shrink-0">{{ t('tool.address.address') }}</span>
            <span class="text-xs text-gray-800 font-medium">{{ resultData.address }}</span>
          </div>
        </div>
      </template>

      <!-- hema_search 搜索结果 -->
      <template v-else-if="info.tool === 'hema_search' && resultData">
        <div class="text-xs text-gray-500 mb-1.5">{{ resultData.message }}</div>
        <div v-if="resultData.products?.length" class="space-y-1.5">
          <div
            v-for="p in resultData.products"
            :key="p.index"
            class="flex items-center justify-between bg-white rounded px-2.5 py-1.5 border border-gray-100"
          >
            <span class="text-xs text-gray-800 flex-1 truncate">{{ p.name || t('tool.hema.product', { index: p.index }) }}</span>
            <span v-if="p.price" class="text-xs text-orange-600 font-medium ml-2 shrink-0">{{ p.price }}</span>
          </div>
        </div>
      </template>

      <!-- hema_add_cart 加购结果 -->
      <template v-else-if="info.tool === 'hema_add_cart' && resultData">
        <div class="bg-white rounded-lg p-2.5 border border-gray-100">
          <div class="text-xs text-gray-700">{{ resultData.message }}</div>
          <div v-if="resultData.cart_count" class="text-xs text-gray-500 mt-1">{{ t('tool.cart.total', { total: resultData.cart_count }) }}</div>
        </div>
      </template>

      <!-- hema_cart_status 购物车状态 -->
      <template v-else-if="info.tool === 'hema_cart_status' && resultData">
        <div class="text-xs text-gray-500 mb-1.5">{{ resultData.message }}</div>
        <div v-if="resultData.items?.length" class="space-y-1.5">
          <div
            v-for="item in resultData.items"
            :key="item.index"
            class="flex items-center justify-between bg-white rounded px-2.5 py-1.5 border border-gray-100"
          >
            <span class="text-xs text-gray-800 flex-1 truncate">{{ item.name }}</span>
            <span class="text-xs text-gray-500 mx-2">x{{ item.quantity }}</span>
            <span v-if="item.price" class="text-xs text-orange-600 font-medium shrink-0">{{ item.price }}</span>
          </div>
        </div>
        <div v-if="resultData.total_price" class="text-xs text-right text-gray-600 mt-1.5 font-medium">
          {{ t('tool.cart.total', { total: resultData.total_price }) }}
        </div>
      </template>

      <!-- hema_set_location 地址设置结果 -->
      <template v-else-if="info.tool === 'hema_set_location' && resultData">
        <div class="bg-white rounded-lg p-2.5 border border-gray-100">
          <div class="text-xs text-gray-700">{{ resultData.message }}</div>
          <div v-if="resultData.current_location" class="text-xs text-gray-500 mt-1">{{ t('tool.address.current', { location: resultData.current_location }) }}</div>
        </div>
      </template>

      <!-- agent_call Agent 间调用 -->
      <template v-else-if="info.tool === 'agent_call'">
        <div class="bg-white rounded-lg p-2.5 border border-gray-100">
          <div class="flex items-center gap-2 mb-1.5">
            <span class="text-xs text-gray-500">{{ t('tool.agent.call') }}</span>
            <span class="text-xs font-medium text-blue-700 bg-blue-50 px-1.5 py-0.5 rounded">{{ agentCallTarget }}</span>
            <span v-if="childCallStats" class="text-xs text-gray-400 ml-auto">{{ childCallStats }}</span>
          </div>
          <!-- 子 agent 文字输出（自动折叠） -->
          <div v-if="info.agentContent" class="mb-1.5">
            <button
              class="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 transition"
              @click="agentLogExpanded = !agentLogExpanded"
            >
              <span>{{ agentLogExpanded ? '▼' : '▶' }}</span>
              <span>{{ t('tool.agent.log') }}</span>
              <span class="text-gray-300">{{ t('tool.agent.logLines', { count: info.agentContent.split('\n').filter((l: string) => l.trim()).length }) }}</span>
            </button>
            <div v-if="agentLogExpanded" class="text-xs text-gray-700 whitespace-pre-wrap leading-relaxed mt-1 pl-3 border-l-2 border-gray-200">{{ info.agentContent }}</div>
          </div>
          <!-- 子 agent 工具调用列表（采购任务清单，search+add_cart 配对分组） -->
          <div v-if="info.childCalls?.length" class="space-y-1 mb-1.5">
            <template v-for="(group, gi) in childCallGroups" :key="gi">
              <!-- 配对分组：搜索 + 加购 -->
              <div v-if="group.length > 1" class="rounded border border-gray-100 overflow-hidden">
                <template v-for="child in group" :key="child.toolCallId ?? child.tool + gi">
                  <div
                    class="flex items-center gap-2 px-2 py-1 text-xs"
                    :class="childCallClass(child)"
                  >
                    <span class="shrink-0">{{ childCallIcon(child) }}</span>
                    <span class="font-medium shrink-0">{{ childCallLabel(child) }}</span>
                    <span v-if="child.progressStep" class="text-blue-500 truncate animate-pulse">{{ child.progressStep }}</span>
                    <span v-else-if="child.result && childCallSummary(child)" class="text-gray-600 truncate">{{ childCallSummary(child) }}</span>
                    <span v-if="child.result" class="ml-auto shrink-0" :class="isSkipped(child) ? 'text-gray-400' : child.result.success ? 'text-green-600' : 'text-red-500'">
                      {{ isSkipped(child) ? '⏭' : child.result.success ? '✓' : '✗' }}
                    </span>
                  </div>
                  <InlineInput
                    v-if="child.inputRequest && !child.inputRequest.resolved"
                    :request="child.inputRequest"
                    @submit="handleInputSubmit"
                  />
                </template>
              </div>
              <!-- 独立项（地址、购物车状态等） -->
              <template v-else>
                <div
                  class="flex items-center gap-2 px-2 py-1 rounded text-xs"
                  :class="childCallClass(group[0])"
                >
                  <span class="shrink-0">{{ childCallIcon(group[0]) }}</span>
                  <span class="font-medium shrink-0">{{ childCallLabel(group[0]) }}</span>
                  <span v-if="group[0].progressStep" class="text-blue-500 truncate animate-pulse">{{ group[0].progressStep }}</span>
                  <span v-else-if="group[0].result && childCallSummary(group[0])" class="text-gray-600 truncate">{{ childCallSummary(group[0]) }}</span>
                  <span v-if="group[0].result" class="ml-auto shrink-0" :class="isSkipped(group[0]) ? 'text-gray-400' : group[0].result.success ? 'text-green-600' : 'text-red-500'">
                    {{ isSkipped(group[0]) ? '⏭' : group[0].result.success ? '✓' : '✗' }}
                  </span>
                </div>
                <InlineInput
                  v-if="group[0].inputRequest && !group[0].inputRequest.resolved"
                  :request="group[0].inputRequest"
                  @submit="handleInputSubmit"
                />
              </template>
            </template>
          </div>
          <!-- agent_call 自身的内联输入 -->
          <InlineInput
            v-if="info.inputRequest && !info.inputRequest.resolved"
            :request="info.inputRequest"
            @submit="handleInputSubmit"
          />
          <!-- 购物车汇总（agent_call 完成后展示最终商品） -->
          <div v-if="cartSummary" class="mt-2 rounded-lg border border-orange-200 bg-orange-50/50 p-2.5">
            <div class="flex items-center gap-1.5 mb-1.5">
              <span class="text-sm">🛒</span>
              <span class="text-xs font-medium text-orange-700">{{ t('tool.cart.title') }}</span>
            </div>
            <div class="space-y-1">
              <div
                v-for="(item, idx) in cartSummary.items"
                :key="idx"
                class="flex items-center justify-between bg-white rounded px-2.5 py-1.5 border border-orange-100"
              >
                <span class="text-xs text-gray-800 flex-1 truncate">{{ item.name }}</span>
                <span class="text-xs text-gray-500 mx-2">x{{ item.quantity }}</span>
                <span v-if="item.price" class="text-xs text-orange-600 font-medium shrink-0">{{ item.price }}</span>
              </div>
            </div>
          </div>
          <!-- 当前执行步骤 -->
          <div v-if="info.progressStep && !info.result" class="text-xs text-blue-500 animate-pulse">{{ info.progressStep }}</div>
          <!-- 等待中（无内容时） -->
          <div v-else-if="!info.agentContent && !info.childCalls?.length && !info.result" class="text-xs text-blue-500 animate-pulse">{{ t('tool.status.executing') }}</div>
          <!-- 完成后的错误 -->
          <div v-if="info.result?.error" class="text-xs text-red-500 mt-1">{{ info.result.error }}</div>
        </div>
      </template>

      <!-- 通用 fallback -->
      <template v-else-if="info.result">
        <div v-if="info.result?.error" class="text-xs text-red-500">{{ info.result.error }}</div>
        <pre v-else class="text-xs bg-white rounded p-2 overflow-x-auto max-h-48 overflow-y-auto">{{ JSON.stringify(resultData, null, 2) }}</pre>
      </template>

      <!-- 直接工具卡片的内联输入（非 agent_call 场景） -->
      <InlineInput
        v-if="info.tool !== 'agent_call' && info.inputRequest && !info.inputRequest.resolved"
        :request="info.inputRequest"
        @submit="handleInputSubmit"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ToolCallInfo, InputRequest } from '../../types'
import { submitInput } from '../../api/chat'
import MealRow from './MealRow.vue'
import InlineInput from './InlineInput.vue'

const { t } = useI18n()

interface ShoppingItem {
  name: string
  amount?: string
  count: number
  checked?: boolean
}

const props = defineProps<{ info: ToolCallInfo }>()
const emit = defineEmits<{ toggle: []; 'tool-data-change': [] }>()

const agentLogExpanded = ref(false)

async function handleInputSubmit(request: InputRequest, value: string) {
  // 先标记 UI 状态（通过 emit 通知父组件，而非直接 mutation）
  // 此处是响应式对象引用，Vue 允许在组件内修改嵌套对象
  request.resolved = true
  request.userValue = value

  try {
    const ok = await submitInput(request.requestId, value)
    if (!ok) {
      // 提交失败，回滚 UI 状态
      request.resolved = false
      request.userValue = undefined
    }
  } catch {
    request.resolved = false
    request.userValue = undefined
  }
}

const TOOL_ICONS: Record<string, string> = {
  profile_get: '👤',
  profile_save: '💾',
  dish_query: '🔍',
  meal_recommend: '📋',
  shopping_list: '🛒',
  address_get: '📍',
  address_save: '📍',
  agent_call: '🤖',
  hema_set_location: '📍',
  hema_search: '🔍',
  hema_add_cart: '🛒',
  hema_cart_status: '🛒',
}

const toolIcon = computed(() => TOOL_ICONS[props.info.tool] ?? '🔧')

const agentCallTarget = computed(() => {
  return props.info.params?.target_agent ?? t('tool.agent.unknown')
})

const toolLabel = computed(() => {
  const key = `tool.${props.info.tool}`
  if (props.info.tool === 'agent_call') {
    const agentKey = `tool.agent.${agentCallTarget.value}`
    const agentName = t(agentKey) !== agentKey ? t(agentKey) : agentCallTarget.value
    return t('tool.agent_call', { target: agentName })
  }
  const label = t(key)
  return label !== key ? label : props.info.tool
})

// ── childCalls helpers ──────────────────────────
const CHILD_ICONS: Record<string, string> = {
  hema_set_location: '📍',
  hema_search: '🔍',
  hema_add_cart: '🛒',
  hema_cart_status: '🛒',
  address_get: '📍',
  address_save: '📍',
}

const CHILD_LABEL_KEYS: Record<string, string> = {
  hema_set_location: 'tool.child.setLocation',
  hema_search: 'tool.child.search',
  hema_add_cart: 'tool.child.addCart',
  hema_cart_status: 'tool.child.cartStatus',
  address_get: 'tool.child.addressGet',
  address_save: 'tool.child.addressSave',
}

/** 将 childCalls 按 groupId 分组（同 groupId 归入同组，无 groupId 独立成组） */
const childCallGroups = computed((): ToolCallInfo[][] => {
  const calls = props.info.childCalls ?? []
  const groupMap = new Map<string, ToolCallInfo[]>()
  const groups: ToolCallInfo[][] = []
  const seen = new Set<string>()

  for (const call of calls) {
    if (call.groupId) {
      if (!groupMap.has(call.groupId)) {
        groupMap.set(call.groupId, [])
      }
      groupMap.get(call.groupId)!.push(call)
    }
  }

  // 保持原始顺序
  for (const call of calls) {
    if (call.groupId) {
      if (!seen.has(call.groupId)) {
        seen.add(call.groupId)
        groups.push(groupMap.get(call.groupId)!)
      }
    } else {
      groups.push([call])
    }
  }
  return groups
})

const childCallStats = computed(() => {
  const calls = props.info.childCalls
  if (!calls?.length) return ''
  const done = calls.filter((c) => c.result).length
  return t('tool.agent.stats', { done, total: calls.length })
})

/** 从 childCalls 中提取购物车汇总（agent_call 完成后展示） */
const cartSummary = computed(() => {
  if (props.info.tool !== 'agent_call' || !props.info.result?.success) return null
  const children = props.info.childCalls ?? []

  // 优先从 hema_cart_status 提取完整购物车
  const cartStatus = [...children].reverse().find(
    (c) => c.tool === 'hema_cart_status' && c.result?.success && c.result.data?.items?.length,
  )
  if (cartStatus) {
    return {
      items: cartStatus.result!.data.items as { name: string; quantity: number; price: string }[],
      totalPrice: cartStatus.result!.data.total_price as string,
    }
  }

  // 兜底：从 hema_add_cart 成功结果聚合
  const addResults = children.filter(
    (c) => c.tool === 'hema_add_cart' && c.result?.success && c.result.data?.product_name,
  )
  if (!addResults.length) return null

  const items = addResults.map((c) => ({
    name: c.result!.data.product_name as string,
    quantity: (c.result!.data.quantity ?? 1) as number,
    price: '',
  }))
  return { items, totalPrice: '' }
})

function isSkipped(child: ToolCallInfo): boolean {
  return !!child.result?.data?.skipped || !!child.result?.data?.skipped_reason
}

function childCallClass(child: ToolCallInfo): string {
  if (child.result) {
    if (isSkipped(child)) return 'bg-gray-50 opacity-60'
    return child.result.success ? 'bg-green-50' : 'bg-red-50'
  }
  if (child.progressStep) return 'bg-blue-50'
  return 'bg-gray-50'
}

function childCallIcon(child: ToolCallInfo): string {
  return CHILD_ICONS[child.tool] ?? '🔧'
}

function childCallLabel(child: ToolCallInfo): string {
  const key = CHILD_LABEL_KEYS[child.tool]
  const base = key ? t(key) : child.tool
  if (child.tool === 'hema_search' && child.params?.keyword) {
    return `${base}：${child.params.keyword}`
  }
  if (child.tool === 'hema_add_cart') {
    return base
  }
  return base
}

function childCallSummary(child: ToolCallInfo): string {
  const r = child.result
  if (!r) return ''
  if (isSkipped(child)) {
    const reason = r.data?.skipped_reason
    if (reason === 'not_found') return t('tool.child.notFound')
    if (reason === 'search_error') return t('tool.child.searchError')
    if (reason === 'agent_skip') {
      // 检查目标商品是否已在其他组成功加购
      const targetName = child.params?.product_name
      if (targetName) {
        const allChildren = props.info.childCalls ?? []
        const addedElsewhere = allChildren.find(
          (c) => c !== child
            && c.tool === 'hema_add_cart'
            && c.result?.success
            && c.result.data?.product_name
            && (c.result.data.product_name.includes(targetName) || targetName.includes(c.result.data.product_name)),
        )
        if (addedElsewhere) {
          return t('tool.child.alreadyAdded')
        }
      }
      return t('tool.child.agentSkip')
    }
    return t('tool.child.skipped')
  }
  if (r.error) return r.error
  const d = r.data
  if (!d) return ''
  if (child.tool === 'hema_search' && d.products?.length != null) {
    return t('tool.child.found', { count: d.products.length })
  }
  if (child.tool === 'hema_add_cart') {
    if (r.success && d.product_name) return `${d.product_name} x${d.quantity ?? 1}`
    if (r.error) return r.error
    return d.message ?? ''
  }
  if (child.tool === 'hema_set_location' && d.address) {
    return d.address
  }
  if (child.tool === 'hema_cart_status' && d.total_items != null) {
    return t('tool.child.items', { count: d.total_items, price: d.total_price ?? '—' })
  }
  if (child.tool === 'address_get') {
    return d.found ? d.address ?? t('tool.child.addressFound') : t('tool.child.addressNotSaved')
  }
  return ''
}

const SLOT_LABEL_KEYS: Record<string, string> = {
  family_size: 'tool.slot.family_size',
  family_members: 'tool.slot.family_members',
  taste: 'tool.slot.taste',
  cuisine: 'tool.slot.cuisine',
  restrictions: 'tool.slot.restrictions',
  health_goal: 'tool.slot.health_goal',
  cooking_skill: 'tool.slot.cooking_skill',
  budget: 'tool.slot.budget',
  scene: 'tool.slot.scene',
}

function slotLabel(key: string): string {
  const k = SLOT_LABEL_KEYS[key]
  return k ? t(k) : key
}

const resultSuccess = computed(() => {
  const r = props.info.result
  if (!r) return false
  // result 可能是 partial-json 解析的中间态
  if (typeof r === 'object' && 'success' in r) return r.success
  return true
})

const paramTags = computed(() => {
  const p = props.info.params
  const tags: string[] = []
  if (p.keyword) tags.push(p.keyword)
  if (p.regional) tags.push(p.regional)
  if (p.dish_type) tags.push(p.dish_type)
  if (p.flavor) tags.push(p.flavor)
  if (p.cooking_method) tags.push(p.cooking_method)
  if (p.goal) tags.push(p.goal)
  if (p.max_calories) tags.push(`≤${p.max_calories}kcal`)
  if (p.daily_calories) tags.push(t('tool.tag.dailyCal', { cal: p.daily_calories }))
  if (p.days) tags.push(t('tool.tag.days', { days: p.days }))
  if (p.suitability) tags.push(p.suitability)
  if (p.exclude_flavors?.length) tags.push(...p.exclude_flavors.map((f: string) => t('tool.tag.excludeFlavor', { flavor: f })))
  if (p.exclude_ingredients?.length) tags.push(...p.exclude_ingredients.map((i: string) => t('tool.tag.excludeIngredient', { ingredient: i })))
  if (p.cuisine_preference?.length) tags.push(...p.cuisine_preference)
  if (p.dish_names?.length) tags.push(t('tool.tag.dishes', { count: p.dish_names.length }))
  if (p.dietary_goal) tags.push(p.dietary_goal)
  if (p.tags?.length) tags.push(...p.tags)
  if (p.phone) tags.push(p.phone)
  if (p.address) tags.push(p.address.length > 20 ? p.address.slice(0, 20) + '...' : p.address)
  if (p.product_name) tags.push(p.product_name)
  if (p.product_index != null) tags.push(t('tool.tag.product', { index: p.product_index }))
  if (p.quantity && p.quantity > 1) tags.push(`x${p.quantity}`)
  if (p.target_agent) {
    const agentKey = `tool.agent.${p.target_agent}`
    tags.push(t(agentKey) !== agentKey ? t(agentKey) : p.target_agent)
  }
  return tags
})

const resultData = computed(() => {
  const r = props.info.result
  if (!r) return null
  // 完整结果: {success, data, error}; partial-json 可能直接是对象
  return r.data ?? r
})

const dishes = computed(() => {
  return resultData.value?.dishes ?? []
})

const resultTotal = computed(() => {
  return resultData.value?.total ?? dishes.value.length
})

const mealPlan = computed(() => {
  return resultData.value?.meal_plan ?? []
})

const avgCalories = computed(() => {
  return resultData.value?.avg_daily_calories ?? 0
})

const shoppingList = computed(() => {
  const d = resultData.value
  if (d?.shopping_list) return d
  return null
})

// 采购清单 checkbox 状态，从后端 checked 字段初始化
const checkedItems: Record<string, boolean> = reactive({})

// 当 shoppingList 数据到达时，用后端返回的 checked 字段初始化勾选状态
watch(shoppingList, (val) => {
  if (!val?.shopping_list) return
  const list = val.shopping_list as Record<string, ShoppingItem[]>
  for (const items of Object.values(list)) {
    for (const item of items) {
      // 仅首次初始化，不覆盖用户手动操作
      if (!(item.name in checkedItems)) {
        checkedItems[item.name] = item.checked !== false
      }
    }
  }
}, { immediate: true })

const checkedCount = computed(() => {
  if (!shoppingList.value) return 0
  const list = shoppingList.value.shopping_list as Record<string, ShoppingItem[]>
  let count = 0
  for (const items of Object.values(list)) {
    for (const item of items) {
      if (checkedItems[item.name] !== false) count++
    }
  }
  return count
})

const allChecked = computed(() => {
  return shoppingList.value ? checkedCount.value === shoppingList.value.total_items : true
})

function toggleItem(name: string) {
  checkedItems[name] = checkedItems[name] === false
  syncCheckedToResult()
}

function toggleAllChecked() {
  const target = !allChecked.value
  if (!shoppingList.value) return
  const list = shoppingList.value.shopping_list as Record<string, ShoppingItem[]>
  for (const items of Object.values(list)) {
    for (const item of items) {
      checkedItems[item.name] = target
    }
  }
  syncCheckedToResult()
}

/** 将勾选状态同步回 result.data，并通知父组件持久化 */
function syncCheckedToResult() {
  const d = props.info.result?.data
  if (!d?.shopping_list) return
  const list = d.shopping_list as Record<string, ShoppingItem[]>
  for (const items of Object.values(list)) {
    for (const item of items) {
      item.checked = checkedItems[item.name] !== false
    }
  }
  emit('tool-data-change')
}

/** 返回已勾选的食材列表（供父组件在"一键加购物车"时读取） */
function getCheckedIngredients(): { name: string; amount: string }[] {
  if (!shoppingList.value?.shopping_list) return []
  const list = shoppingList.value.shopping_list as Record<string, ShoppingItem[]>
  const result: { name: string; amount: string }[] = []
  for (const items of Object.values(list)) {
    for (const item of items) {
      if (checkedItems[item.name] !== false) {
        result.push({ name: item.name, amount: item.amount ?? '' })
      }
    }
  }
  return result
}

defineExpose({ getCheckedIngredients })

function ingredientNames(ingredients: any[]): string {
  return ingredients
    .map((i: any) => typeof i === 'string' ? i : i.name)
    .filter(Boolean)
    .join('、')
}
</script>

<style scoped>
.tag {
  @apply inline-block px-1.5 py-0.5 text-xs rounded;
}
.tag-type {
  @apply bg-purple-50 text-purple-700;
}
.tag-method {
  @apply bg-green-50 text-green-700;
}
.tag-flavor {
  @apply bg-orange-50 text-orange-700;
}
.tag-region {
  @apply bg-blue-50 text-blue-700;
}
</style>
