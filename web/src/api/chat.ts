import { localeHeaders } from './locale'

export interface OpeningConfig {
  agent_name: string
  agent_avatar: string
  agent_intro: string
  suggested_questions: string[]
}

export async function fetchOpening(): Promise<OpeningConfig | null> {
  try {
    const res = await fetch('/api/chat/opening', { headers: localeHeaders() })
    if (!res.ok) return null
    const json = await res.json()
    return json.success ? json.data : null
  } catch {
    return null
  }
}

export interface HistoryResult {
  data: { id?: number; role: string; content: string; created_at?: string; tool_calls?: any[] }[]
  total: number
}

export async function fetchHistory(
  sessionId: string,
  limit = 20,
  offset = 0
): Promise<HistoryResult> {
  try {
    const params = new URLSearchParams({
      session_id: sessionId,
      limit: String(limit),
      offset: String(offset),
    })
    const res = await fetch(`/api/chat/history?${params}`, { headers: localeHeaders() })
    if (!res.ok) return { data: [], total: 0 }
    const json = await res.json()
    return json.success
      ? { data: json.data ?? [], total: json.total ?? 0 }
      : { data: [], total: 0 }
  } catch {
    return { data: [], total: 0 }
  }
}

export async function clearHistory(sessionId: string): Promise<boolean> {
  try {
    const params = new URLSearchParams({ session_id: sessionId })
    const res = await fetch(`/api/chat/history?${params}`, {
      method: 'DELETE',
      headers: localeHeaders(),
    })
    if (!res.ok) return false
    const json = await res.json()
    return json.success === true
  } catch {
    return false
  }
}

export async function submitInput(requestId: string, value: string): Promise<boolean> {
  try {
    const res = await fetch('/api/chat/input', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...localeHeaders() },
      body: JSON.stringify({ request_id: requestId, value }),
    })
    if (!res.ok) return false
    const json = await res.json()
    return json.success === true
  } catch {
    return false
  }
}

export async function updateMessageToolData(
  messageId: number,
  toolData: any[],
): Promise<boolean> {
  try {
    const res = await fetch(`/api/chat/message/${messageId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...localeHeaders() },
      body: JSON.stringify({ tool_data: toolData }),
    })
    if (!res.ok) return false
    const json = await res.json()
    return json.success === true
  } catch {
    return false
  }
}

export async function streamChat(
  message: string,
  sessionId?: string,
  onEvent?: (event: string, data: any) => void,
  signal?: AbortSignal
): Promise<void> {
  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...localeHeaders() },
      body: JSON.stringify({ message, session_id: sessionId }),
      signal,
    })

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`)
    }

    const reader = res.body?.getReader()
    if (!reader) {
      throw new Error('No readable stream')
    }

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      let currentEvent = ''
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim()
        } else if (line.startsWith('data: ') && currentEvent) {
          try {
            const data = JSON.parse(line.slice(6))
            onEvent?.(currentEvent, data)
          } catch { /* ignore parse errors */ }
          currentEvent = ''
        }
      }
    }
  } catch (err) {
    if ((err as Error).name === 'AbortError') {
      return // abort 不视为错误
    }
    throw err
  }
}
