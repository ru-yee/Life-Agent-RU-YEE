<template>
  <div class="flex flex-col h-full">
    <!-- Tab 切换 -->
    <div class="flex border-b border-gray-200 bg-white px-4 shrink-0">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        data-testid="tab"
        class="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px"
        :class="activeTab === tab.key
          ? 'border-blue-600 text-blue-600'
          : 'border-transparent text-gray-500 hover:text-gray-700'"
        @click="switchTab(tab.key)"
      >
        {{ tab.label }}
        <span v-if="tab.key === 'installed' && installedPlugins.length" class="ml-1 text-xs text-gray-400">
          ({{ installedPlugins.length }})
        </span>
      </button>
    </div>

    <!-- 已安装 Tab -->
    <div v-if="activeTab === 'installed'" data-testid="installed-panel" class="flex-1 overflow-y-auto px-4 py-4 space-y-4">
      <div v-if="loadingInstalled" class="flex items-center justify-center h-40 text-gray-400 text-sm animate-pulse">
        {{ t('skillhub.loading') }}
      </div>
      <div v-else-if="errorInstalled" class="flex flex-col items-center justify-center h-40 text-sm">
        <p class="text-red-500">{{ errorInstalled }}</p>
        <button class="mt-2 text-blue-600 underline text-xs" @click="loadInstalled">{{ t('skillhub.retry') }}</button>
      </div>
      <template v-else>
        <div v-for="group in groupedPlugins" :key="group.type">
          <div class="flex items-center gap-2 mb-2">
            <span class="text-sm">{{ group.icon }}</span>
            <span class="text-sm font-medium text-gray-700">{{ group.label }}</span>
            <span class="text-xs text-gray-400">({{ group.items.length }})</span>
          </div>
          <div class="space-y-3">
            <PluginCard
              v-for="p in group.items"
              :key="p.name"
              :name="p.name"
              :version="p.version"
              :type="p.type"
              :description="p.description"
              :status="p.status"
              :capabilities="p.capabilities"
              :tools="p.tools"
              :source="p.source"
              mode="installed"
              @uninstall="handleUninstall"
              @reload="handleReload"
            />
          </div>
        </div>
        <div v-if="installedPlugins.length === 0" class="flex flex-col items-center justify-center h-40 text-gray-400 text-sm">
          <p class="text-2xl mb-2">🧩</p>
          <p>{{ t('skillhub.empty') }}</p>
        </div>
      </template>
    </div>

    <!-- 市场 Tab -->
    <div v-if="activeTab === 'market'" data-testid="market-panel" class="flex flex-col flex-1 overflow-hidden">
      <div class="px-4 pt-4 pb-2 shrink-0">
        <SearchBar @search="handleSearch" />
      </div>

      <div class="flex-1 overflow-y-auto px-4 pb-4 space-y-3">
        <div v-if="loadingMarket" class="flex items-center justify-center h-40 text-gray-400 text-sm animate-pulse">
          {{ t('skillhub.loading') }}
        </div>
        <div v-else-if="errorMarket" class="flex flex-col items-center justify-center h-40 text-sm">
          <p class="text-red-500">{{ errorMarket }}</p>
          <button class="mt-2 text-blue-600 underline text-xs" @click="loadMarket">{{ t('skillhub.retry') }}</button>
        </div>
        <template v-else>
          <PluginCard
            v-for="p in marketPlugins"
            :key="p.name"
            :name="p.name"
            :version="p.version"
            :type="p.type"
            :description="p.description"
            :author="p.author"
            :tags="p.tags"
            :verified="p.verified"
            :repository-url="p.manifest_url"
            mode="market"
            :is-installed="installedNames.has(p.name)"
            :installing="installingSet.has(p.name)"
            @install="handleInstall"
          />
          <div v-if="marketPlugins.length === 0" class="flex flex-col items-center justify-center h-40 text-gray-400 text-sm">
            <p class="text-2xl mb-2">🔍</p>
            <p>{{ t('skillhub.notFound') }}</p>
          </div>
        </template>
      </div>
    </div>

    <!-- Toast 通知 -->
    <Transition name="fade">
      <div
        v-if="toast"
        class="fixed bottom-20 left-1/2 -translate-x-1/2 px-4 py-2 rounded-lg text-sm shadow-lg z-50"
        :class="toast.type === 'error' ? 'bg-red-600 text-white' : 'bg-green-600 text-white'"
      >
        {{ toast.message }}
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import PluginCard from '../components/skillhub/PluginCard.vue'
import SearchBar from '../components/skillhub/SearchBar.vue'
import {
  fetchInstalled,
  fetchRegistry,
  searchPlugins,
  installPlugin,
  uninstallPlugin,
} from '../api/skillhub'
import type { InstalledPlugin, RegistryPlugin } from '../types'

const { t } = useI18n()

const tabs = computed(() => [
  { key: 'installed' as const, label: t('skillhub.tab.installed') },
  // { key: 'market' as const, label: t('skillhub.tab.market') },
])

type TabKey = 'installed' | 'market'

const activeTab = ref<TabKey>('installed')

// 已安装
const installedPlugins = ref<InstalledPlugin[]>([])
const loadingInstalled = ref(false)
const errorInstalled = ref<string | null>(null)

// 市场
const marketPlugins = ref<RegistryPlugin[]>([])
const loadingMarket = ref(false)
const errorMarket = ref<string | null>(null)
const installingSet = ref<Set<string>>(new Set())

// Toast
const toast = ref<{ message: string; type: 'success' | 'error' } | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | null = null

const installedNames = computed(() => new Set(installedPlugins.value.map(p => p.name)))

const TYPE_META: Record<string, { icon: string; labelKey: string; order: number }> = {
  agent: { icon: '🤖', labelKey: 'skillhub.type.agent', order: 0 },
  memory: { icon: '🧠', labelKey: 'skillhub.type.memory', order: 1 },
  extension: { icon: '🔌', labelKey: 'skillhub.type.extension', order: 2 },
  search: { icon: '🔍', labelKey: 'skillhub.type.search', order: 3 },
}

const groupedPlugins = computed(() => {
  const map = new Map<string, InstalledPlugin[]>()
  for (const p of installedPlugins.value) {
    const list = map.get(p.type) ?? []
    list.push(p)
    map.set(p.type, list)
  }
  return Array.from(map.entries())
    .map(([type, items]) => ({
      type,
      icon: TYPE_META[type]?.icon ?? '📦',
      label: TYPE_META[type] ? t(TYPE_META[type].labelKey) : type,
      order: TYPE_META[type]?.order ?? 99,
      items,
    }))
    .sort((a, b) => a.order - b.order)
})

function showToast(message: string, type: 'success' | 'error' = 'success') {
  if (toastTimer) clearTimeout(toastTimer)
  toast.value = { message, type }
  toastTimer = setTimeout(() => { toast.value = null }, 3000)
}

async function loadInstalled() {
  loadingInstalled.value = true
  errorInstalled.value = null
  try {
    installedPlugins.value = await fetchInstalled()
  } catch (e) {
    errorInstalled.value = (e as Error).message
  } finally {
    loadingInstalled.value = false
  }
}

async function loadMarket() {
  loadingMarket.value = true
  errorMarket.value = null
  try {
    const index = await fetchRegistry()
    marketPlugins.value = index.plugins
  } catch (e) {
    errorMarket.value = (e as Error).message
  } finally {
    loadingMarket.value = false
  }
}

function switchTab(tab: TabKey) {
  activeTab.value = tab
  if (tab === 'market' && marketPlugins.value.length === 0 && !loadingMarket.value) {
    loadMarket()
  }
}

async function handleSearch(params: { q: string; tags: string; type: string }) {
  if (!params.q && !params.tags && !params.type) {
    loadMarket()
    return
  }
  loadingMarket.value = true
  errorMarket.value = null
  try {
    marketPlugins.value = await searchPlugins(params)
  } catch (e) {
    errorMarket.value = (e as Error).message
  } finally {
    loadingMarket.value = false
  }
}

async function handleInstall(name: string) {
  const next = new Set(installingSet.value)
  next.add(name)
  installingSet.value = next

  try {
    const result = await installPlugin(name)
    if (result.status === 'already_latest') {
      showToast(`${name} 已是最新版本`)
    } else {
      showToast(`${name} v${result.version} 安装成功`)
    }
    await loadInstalled()
  } catch (e) {
    showToast((e as Error).message, 'error')
  } finally {
    const cleaned = new Set(installingSet.value)
    cleaned.delete(name)
    installingSet.value = cleaned
  }
}

async function handleUninstall(name: string) {
  try {
    await uninstallPlugin(name)
    showToast(`${name} 已卸载`)
    await loadInstalled()
  } catch (e) {
    showToast((e as Error).message, 'error')
  }
}

async function handleReload(name: string) {
  showToast(`${name} 重载中...`)
  await loadInstalled()
  showToast(`${name} 已重载`)
}

onMounted(loadInstalled)
</script>

<style scoped>
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.3s;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
</style>
