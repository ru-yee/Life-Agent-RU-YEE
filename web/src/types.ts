export interface Message {
  id: string
  dbId?: number           // 数据库记录 id，用于持久化更新
  role: 'user' | 'assistant'
  content: string
  timestamp: number
  toolCalls?: ToolCallInfo[]
  thinking?: string
}

export interface InputRequest {
  requestId: string
  prompt: string
  options: { label: string; value: string }[]
  inputType: 'select' | 'text'
  resolved?: boolean      // 用户已回复
  userValue?: string      // 用户选择/输入的值
}

export interface ToolCallInfo {
  toolCallId?: string     // LLM 分配的工具调用 ID，用于精确匹配更新
  tool: string
  params: Record<string, any>
  result?: { success: boolean; data: any; error: string | null }
  rawJson?: string        // 流式接收中的原始 JSON 片段
  streaming?: boolean     // 是否正在流式接收
  progressStep?: string   // 工具执行中的当前步骤描述
  agentContent?: string   // 子 Agent 流式文字输出（agent_call 专用）
  childCalls?: ToolCallInfo[]  // 子 Agent 的工具调用列表（agent_call 专用）
  inputRequest?: InputRequest  // 工具请求用户内联输入
  groupId?: string        // 同组搜索/加购的唯一标识（由后端分配）
  collapsed: boolean
}

export type SSEEvent =
  | { event: 'text_delta'; data: { content: string } }
  | { event: 'tool_call'; data: { tool: string; params: Record<string, any>; tool_call_id?: string } }
  | { event: 'tool_output_delta'; data: { tool: string; chunk: string; tool_call_id?: string } }
  | { event: 'tool_output_done'; data: { tool: string; result: { success: boolean; data: any; error: string | null }; tool_call_id?: string } }
  | { event: 'tool_error'; data: { tool: string; error: string; tool_call_id?: string } }
  | { event: 'done'; data: { session_id: string; agent: string } }
  | { event: 'error'; data: { error: string; suggestion?: string } }
  | { event: 'thinking'; data: { status: string } }
  | { event: 'tool_progress'; data: { tool: string; step: string; tool_call_id?: string } }
  | { event: 'agent_delegate'; data: { source: string; target: string; message: string } }
  | { event: 'agent_delegate_done'; data: { source: string; target: string; summary: string } }
  | { event: 'agent_progress'; data: { agent: string; type: string; content?: string; tool?: string; tool_call_id?: string; step?: string; params?: Record<string, any>; result?: { success: boolean; data: any; error: string | null }; items?: { tool: string; params?: Record<string, any> }[] } }
  | { event: 'input_request'; data: { request_id: string; tool: string; prompt: string; options: { label: string; value: string }[]; input_type: 'select' | 'text' } }
  | { event: 'message_saved'; data: { message_id: number } }

export interface Plugin {
  name: string
  type: 'agent' | 'memory' | 'search' | 'extension'
  version: string
  status: 'loaded' | 'unloaded'
  capabilities: string[]
}

export interface Device {
  device_id: string
  name: string
  device_type: string
  status: 'online' | 'offline'
  last_heartbeat: string
  capabilities: string[]
}

// ── SkillHub 类型 ──────────────────────────────

export interface RegistryPlugin {
  name: string
  version: string
  type: 'agent' | 'memory' | 'extension' | 'search'
  description: string
  author: string
  tags: string[]
  min_framework_version: string
  download_url: string
  manifest_url: string
  sha256: string
  verified: boolean
  created_at: string
  updated_at: string
}

export interface RegistryIndex {
  version: number
  updated_at: string
  plugins: RegistryPlugin[]
}

export interface InstalledPlugin {
  name: string
  version: string
  type: 'agent' | 'memory' | 'extension' | 'search'
  status?: string
  capabilities?: string[]
  description?: string
  tools?: string[]
  source: 'builtin' | 'contrib'
}

export interface InstallResult {
  status: 'installed' | 'upgraded' | 'already_latest'
  version: string
}

export interface UninstallResult {
  status: 'uninstalled'
  name: string
}

export interface MessageEnvelope {
  id: string
  type: 'chat' | 'heartbeat' | 'device_command' | 'device_result' | 'device_register' | 'device_registered' | 'error'
  device_id: string | null
  payload: Record<string, any>
  timestamp: string
  ack_required: boolean
}
