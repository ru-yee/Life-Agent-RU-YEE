import { ref } from 'vue'
import { streamChat, fetchHistory, clearHistory } from '../api/chat'
import type { Message, ToolCallInfo } from '../types'
import { parse as parsePartialJson } from 'partial-json'

const PAGE_SIZE = 20

function uid(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

function findLastIndex<T>(arr: T[], predicate: (item: T) => boolean): number {
  for (let i = arr.length - 1; i >= 0; i--) {
    if (predicate(arr[i])) return i
  }
  return -1
}

const SESSION_KEY = 'lary_session_id'

function generateSessionId(): string {
  return 'xxxx-xxxx-4xxx-yxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  }) + '-' + Date.now().toString(36)
}

function getSessionId(): string {
  let id = localStorage.getItem(SESSION_KEY)
  if (!id) {
    id = generateSessionId()
    localStorage.setItem(SESSION_KEY, id)
  }
  return id
}

function turnsToMessages(turns: any[]): Message[] {
  return turns.map((turn: any) => {
    const msg: Message = {
      id: uid(),
      dbId: turn.id ?? undefined,
      role: turn.role as 'user' | 'assistant',
      content: turn.content,
      timestamp: turn.created_at ? new Date(turn.created_at).getTime() : Date.now(),
    }
    if (turn.tool_calls?.length) {
      msg.toolCalls = turn.tool_calls.map((tc: any) => {
        const info: ToolCallInfo = {
          toolCallId: tc.tool_call_id,
          tool: tc.tool,
          params: tc.params ?? {},
          result: tc.result ?? undefined,
          collapsed: false,
        }
        // 恢复 agent_call 的子 agent 输出
        if (tc.tool === 'agent_call' && tc.result?.data) {
          const d = tc.result.data
          if (d.summary) info.agentContent = d.summary

          // 用 tool_results 建立 tool_call_id → result 的索引
          const resultMap = new Map<string, any>()
          const resultsByGroupTool = new Map<string, any>()
          if (d.tool_results?.length) {
            for (const tr of d.tool_results) {
              if (tr.tool_call_id) resultMap.set(tr.tool_call_id, tr)
              if (tr.group_id && tr.tool) {
                resultsByGroupTool.set(`${tr.group_id}:${tr.tool}`, tr)
              }
            }
          }

          if (d.plan?.length) {
            // 从 plan 构建完整骨架，用 tool_results 填充实际结果
            const notFoundResult = { success: false, data: { skipped_reason: 'not_found' }, error: null }
            const searchErrorResult = { success: false, data: { skipped_reason: 'search_error' }, error: null }
            const agentSkipResult = { success: true, data: { skipped_reason: 'agent_skip' }, error: null }
            info.childCalls = d.plan.map((item: any) => {
              const gid = item.group_id ?? ''
              const key = `${gid}:${item.tool}`
              const tr = resultsByGroupTool.get(key)
              let result = tr?.result ?? (item.done ? item.result : undefined)

              // plan 中 add_cart 无实际结果 → 检查同组 search 状态，推断跳过原因
              if (!result && item.tool === 'hema_add_cart' && gid) {
                const searchTr = resultsByGroupTool.get(`${gid}:hema_search`)
                if (searchTr?.result) {
                  const sr = searchTr.result
                  if (!sr.success) {
                    // search 本身报错（设备断连等）
                    result = searchErrorResult
                  } else if (!sr.data?.products?.length) {
                    // search 成功但无商品
                    result = notFoundResult
                  } else {
                    result = agentSkipResult
                  }
                } else if (d.tool_results?.length) {
                  // agent_call 已完成但 add_cart 无结果 → agent 跳过
                  result = agentSkipResult
                }
              }

              return {
                toolCallId: tr?.tool_call_id,
                tool: item.tool,
                params: tr?.params ?? item.params ?? {},
                result,
                collapsed: true,
                groupId: gid || undefined,
              } as ToolCallInfo
            })
          } else if (d.tool_results?.length) {
            // 无 plan 时直接从 tool_results 恢复
            info.childCalls = d.tool_results.map((tr: any) => ({
              toolCallId: tr.tool_call_id,
              tool: tr.tool ?? '',
              params: tr.params ?? {},
              result: tr.result,
              collapsed: true,
              groupId: tr.group_id,
            }))
          }
        }
        return info
      })
    }
    return msg
  })
}

export function useSSE() {
  const messages = ref<Message[]>([])
  const isStreaming = ref(false)
  const error = ref<string | null>(null)
  const hasMore = ref(false)
  const loadingMore = ref(false)
  let sessionId = getSessionId()
  let abortCtrl: AbortController | null = null
  let historyTotal = 0
  let historyLoaded = 0

  async function send(text: string) {
    if (isStreaming.value || !text.trim()) return

    error.value = null
    isStreaming.value = true

    // user message
    messages.value = [
      ...messages.value,
      { id: uid(), role: 'user', content: text, timestamp: Date.now() },
    ]

    // assistant placeholder
    const assistantId = uid()
    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      toolCalls: [],
    }
    messages.value = [...messages.value, assistantMsg]

    abortCtrl = new AbortController()

    try {
      await streamChat(
        text,
        sessionId,
        (event, data) => {
          const idx = messages.value.findIndex((m) => m.id === assistantId)
          if (idx === -1) return
          const msg = { ...messages.value[idx] }

          // 按 tool_call_id 查找工具调用，找不到时按 tool name 兜底
          const findCall = (calls: ToolCallInfo[], tcId?: string, toolName?: string): number => {
            if (tcId) {
              const i = findLastIndex(calls, (c) => c.toolCallId === tcId)
              if (i !== -1) return i
            }
            return toolName ? findLastIndex(calls, (c) => c.tool === toolName) : -1
          }

          switch (event) {
            case 'text_delta':
              msg.content += data.content ?? ''
              msg.thinking = undefined
              break
            case 'tool_call': {
              const tc: ToolCallInfo = {
                toolCallId: data.tool_call_id,
                tool: data.tool,
                params: data.params,
                collapsed: false,
              }
              msg.toolCalls = [...(msg.toolCalls ?? []), tc]
              break
            }
            case 'tool_output_delta': {
              const calls = [...(msg.toolCalls ?? [])]
              const tcIdx = findCall(calls, data.tool_call_id, data.tool)
              if (tcIdx !== -1) {
                const raw = (calls[tcIdx].rawJson ?? '') + (data.chunk ?? '')
                let partialResult: any = undefined
                try {
                  partialResult = parsePartialJson(raw)
                } catch { /* not parseable yet */ }
                calls[tcIdx] = {
                  ...calls[tcIdx],
                  rawJson: raw,
                  streaming: true,
                  result: partialResult != null ? partialResult : calls[tcIdx].result,
                }
              }
              msg.toolCalls = calls
              break
            }
            case 'tool_output_done': {
              const calls = [...(msg.toolCalls ?? [])]
              const tcIdx = findCall(calls, data.tool_call_id, data.tool)
              if (tcIdx !== -1) {
                calls[tcIdx] = {
                  ...calls[tcIdx],
                  result: data.result,
                  rawJson: undefined,
                  streaming: false,
                }
              }
              msg.toolCalls = calls
              break
            }
            case 'tool_error': {
              const calls = [...(msg.toolCalls ?? [])]
              const tcIdx = findCall(calls, data.tool_call_id, data.tool)
              if (tcIdx !== -1) {
                calls[tcIdx] = {
                  ...calls[tcIdx],
                  result: { success: false, data: null, error: data.error },
                }
              }
              msg.toolCalls = calls
              break
            }
            case 'thinking':
              msg.thinking = data.status ?? '思考中...'
              break
            case 'input_request': {
              // 内联输入请求 → 挂到对应工具卡片上
              const inputReq = {
                requestId: data.request_id,
                prompt: data.prompt,
                options: data.options ?? [],
                inputType: (data.input_type ?? 'select') as 'select' | 'text',
              }
              const allCalls = [...(msg.toolCalls ?? [])]
              // 优先匹配 tool name 的卡片
              let targetIdx = findLastIndex(allCalls, (c) => c.tool === data.tool && !c.result)
              if (targetIdx === -1) {
                // 可能在子 agent 中，查找 agent_call 的 childCalls
                const acIdx2 = findLastIndex(allCalls, (c: ToolCallInfo) => c.tool === 'agent_call')
                if (acIdx2 !== -1) {
                  const ac2 = { ...allCalls[acIdx2] }
                  const ch = [...(ac2.childCalls ?? [])]
                  const ci = findLastIndex(ch, (c) => c.tool === data.tool && !c.result)
                  if (ci !== -1) {
                    ch[ci] = { ...ch[ci], inputRequest: inputReq }
                    ac2.childCalls = ch
                    allCalls[acIdx2] = ac2
                  } else {
                    // 挂到 agent_call 自身
                    ac2.inputRequest = inputReq
                    allCalls[acIdx2] = ac2
                  }
                }
              } else {
                allCalls[targetIdx] = { ...allCalls[targetIdx], inputRequest: inputReq }
              }
              msg.toolCalls = allCalls
              msg.thinking = undefined
              break
            }
            case 'agent_delegate':
              msg.thinking = `正在咨询 ${data.target}...`
              break
            case 'agent_delegate_done': {
              msg.thinking = undefined
              // 标记所有未完成的子计划项为"已跳过"
              const doneCalls = [...(msg.toolCalls ?? [])]
              const doneAcIdx = findLastIndex(doneCalls, (c: ToolCallInfo) => c.tool === 'agent_call')
              if (doneAcIdx !== -1) {
                const doneAc = { ...doneCalls[doneAcIdx] }
                const doneChildren = [...(doneAc.childCalls ?? [])]
                let changed = false
                for (let si = 0; si < doneChildren.length; si++) {
                  if (!doneChildren[si].result) {
                    doneChildren[si] = {
                      ...doneChildren[si],
                      result: { success: true, data: { skipped: true }, error: null },
                    }
                    changed = true
                  }
                }
                if (changed) {
                  doneAc.childCalls = doneChildren
                  doneCalls[doneAcIdx] = doneAc
                  msg.toolCalls = doneCalls
                }
              }
              break
            }
            case 'tool_progress': {
              const calls = [...(msg.toolCalls ?? [])]
              const tcIdx = findCall(calls, data.tool_call_id, data.tool)
              if (tcIdx !== -1) {
                calls[tcIdx] = { ...calls[tcIdx], progressStep: data.step }
              }
              msg.toolCalls = calls
              break
            }
            case 'agent_progress': {
              // 子 agent 事件 → 更新对应 agent_call 卡片的 childCalls
              const agentCalls = [...(msg.toolCalls ?? [])]
              const acIdx = findLastIndex(agentCalls, (c: ToolCallInfo) => c.tool === 'agent_call')
              if (acIdx === -1) break
              const ac = { ...agentCalls[acIdx] }
              const children = [...(ac.childCalls ?? [])]

              if (data.type === 'plan' && data.items?.length) {
                // 预生成计划 → 一次性创建全部 childCalls（含 group_id）
                const planned: ToolCallInfo[] = data.items.map((item: any) => ({
                  tool: item.tool,
                  params: item.params ?? {},
                  collapsed: true,
                  groupId: item.group_id,
                  ...(item.done ? { result: item.result } : {}),
                }))
                ac.childCalls = planned
              } else if (data.type === 'text' && data.content) {
                ac.agentContent = (ac.agentContent ?? '') + data.content
                msg.thinking = undefined
              } else if (data.type === 'tool_call' && data.tool) {
                // ── 匹配策略：group_id 精确匹配 > 顺序兜底 ──
                const groupId: string | undefined = data.group_id

                // 重试检测：同 group_id 的 search 已绑定但 add_cart 未绑定 → 覆盖上次 search
                const isRetry = (() => {
                  if (data.tool !== 'hema_search' || !groupId) return false
                  const prevIdx = findLastIndex(children, (c) =>
                    c.tool === 'hema_search' && c.groupId === groupId && !!c.toolCallId,
                  )
                  if (prevIdx === -1) return false
                  // 同组 add_cart 未执行 → 说明是重试
                  const cartPending = children.some((c) =>
                    c.tool === 'hema_add_cart' && c.groupId === groupId && !c.toolCallId,
                  )
                  if (cartPending) {
                    children[prevIdx] = {
                      ...children[prevIdx],
                      toolCallId: data.tool_call_id,
                      params: data.params ?? children[prevIdx].params,
                      result: undefined,
                      progressStep: undefined,
                    }
                    return true
                  }
                  return false
                })()

                if (!isRetry) {
                  let planned = -1
                  // 1. group_id 精确匹配
                  if (groupId) {
                    planned = children.findIndex((c) =>
                      c.tool === data.tool && !c.toolCallId && !c.result && c.groupId === groupId,
                    )
                  }
                  // 2. 兜底：顺序匹配
                  if (planned === -1) {
                    planned = children.findIndex((c) => c.tool === data.tool && !c.toolCallId && !c.result)
                  }

                  if (planned !== -1) {
                    children[planned] = { ...children[planned], toolCallId: data.tool_call_id, params: data.params ?? children[planned].params }
                  } else {
                    children.push({
                      toolCallId: data.tool_call_id,
                      tool: data.tool,
                      params: data.params ?? {},
                      groupId,
                      collapsed: true,
                    })
                  }
                }
                ac.childCalls = children
                ac.progressStep = `执行 ${data.tool}...`
                msg.thinking = `${data.agent} 正在执行 ${data.tool}...`
              } else if (data.type === 'tool_progress' && data.step) {
                const ci = findCall(children, data.tool_call_id, data.tool)
                if (ci !== -1) {
                  children[ci] = { ...children[ci], progressStep: data.step }
                  ac.childCalls = children
                }
                ac.progressStep = data.step
                msg.thinking = `${data.tool ?? data.agent}: ${data.step}`
              } else if (data.type === 'tool_result') {
                const ci = findCall(children, data.tool_call_id, data.tool)
                if (ci !== -1) {
                  children[ci] = { ...children[ci], result: data.result, progressStep: undefined }

                  // search 失败或无商品 → 自动标记同组 add_cart 为跳过
                  const child = children[ci]
                  if (child.tool === 'hema_search' && child.groupId) {
                    const sr = data.result
                    const searchError = sr && !sr.success
                    const noProducts = sr?.success && !sr?.data?.products?.length
                    if (searchError || noProducts) {
                      const cartIdx = children.findIndex(
                        (c) => c.tool === 'hema_add_cart' && c.groupId === child.groupId && !c.result,
                      )
                      if (cartIdx !== -1) {
                        const reason = searchError ? 'search_error' : 'not_found'
                        children[cartIdx] = {
                          ...children[cartIdx],
                          result: { success: false, data: { skipped_reason: reason }, error: null },
                          progressStep: undefined,
                        }
                      }
                    }
                  }

                  ac.childCalls = children
                }
                ac.progressStep = undefined
                msg.thinking = undefined
              } else {
                msg.thinking = data.content ?? data.step ?? `${data.agent} 处理中...`
              }

              agentCalls[acIdx] = ac
              msg.toolCalls = agentCalls
              break
            }
            case 'error':
              error.value = data.error
              break
            case 'message_saved':
              msg.dbId = data.message_id
              break
            case 'done':
              msg.thinking = undefined
              // 新消息发送后，更新已加载计数
              historyLoaded += 2 // user + assistant
              historyTotal += 2
              break
          }

          const updated = [...messages.value]
          updated[idx] = msg
          messages.value = updated
        },
        abortCtrl.signal
      )
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      isStreaming.value = false
      abortCtrl = null
    }
  }

  function stop() {
    abortCtrl?.abort()
  }

  async function loadHistory() {
    // 首次加载：取最新的一页（从末尾开始）
    const result = await fetchHistory(sessionId, PAGE_SIZE, 0)
    historyTotal = result.total
    if (!result.data.length) {
      hasMore.value = false
      return
    }

    // 后端按 id 正序返回，offset=0 是最早的消息
    // 我们需要先加载最新的消息，所以计算 offset
    if (historyTotal <= PAGE_SIZE) {
      // 总数不超过一页，全部加载
      const restored = turnsToMessages(result.data)
      messages.value = restored
      historyLoaded = result.data.length
      hasMore.value = false
    } else {
      // 加载最后一页
      const lastPageOffset = historyTotal - PAGE_SIZE
      const lastPage = await fetchHistory(sessionId, PAGE_SIZE, lastPageOffset)
      const restored = turnsToMessages(lastPage.data)
      messages.value = restored
      historyLoaded = PAGE_SIZE
      hasMore.value = historyLoaded < historyTotal
    }
  }

  async function loadMoreHistory(): Promise<boolean> {
    if (loadingMore.value || !hasMore.value) return false
    loadingMore.value = true

    try {
      // 计算要加载的 offset（往前翻页）
      const remaining = historyTotal - historyLoaded
      const nextSize = Math.min(PAGE_SIZE, remaining)
      const nextOffset = remaining - nextSize

      const result = await fetchHistory(sessionId, nextSize, nextOffset)
      if (!result.data.length) {
        hasMore.value = false
        return false
      }

      const older = turnsToMessages(result.data)
      messages.value = [...older, ...messages.value]
      historyLoaded += result.data.length
      hasMore.value = historyLoaded < historyTotal
      return true
    } finally {
      loadingMore.value = false
    }
  }

  async function clear() {
    await clearHistory(sessionId)
    messages.value = []
    error.value = null
    hasMore.value = false
    historyTotal = 0
    historyLoaded = 0
  }

  return { messages, isStreaming, error, hasMore, loadingMore, send, stop, clear, loadHistory, loadMoreHistory }
}
