/* ============ 消息与会话 ============ */

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  timestamp: number;
  /** 流式传输中 */
  isStreaming?: boolean;
  /** 思考过程（折叠显示） */
  thinking?: string;
  /** 工具调用 */
  toolCalls?: ToolCall[];
  /** 执行日志 */
  executionLogs?: ExecutionLogEntry[];
  /** 附件文件路径 */
  filePaths?: string[];
  /** 图片列表 */
  images?: MessageImage[];
  /** 模型名称 */
  modelName?: string;
  /** Token 用量 */
  tokenUsage?: TokenUsage;
}

export interface MessageImage {
  base64: string;
  mimeType: string;
  path?: string;
}

export interface TokenUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: Message[];
  /** 当前 session_id */
  sessionId?: string;
}

/* ============ 工具 ============ */

export interface ToolParameter {
  name: string;
  type: string;
  description: string;
  required: boolean;
  default?: unknown;
}

export interface ToolDefinition {
  name: string;
  description: string;
  parameters: ToolParameter[] | Record<string, unknown>;
  category?: string;
  source?: 'system' | 'generated';
}

export interface ToolCall {
  id: string;
  toolName: string;
  arguments: Record<string, unknown>;
  result?: string;
  status: 'pending' | 'running' | 'success' | 'error';
  startTime?: number;
  endTime?: number;
}

/* ============ 系统通知 ============ */

export interface SystemNotification {
  id: string;
  type: 'info' | 'warning' | 'error' | 'success';
  message: string;
  timestamp: number;
  read: boolean;
  category?: 'system_error' | 'evolution' | 'task' | 'info';
}

/* ============ 任务进度 ============ */

export interface TaskProgress {
  taskId: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number;   // 0-100
  description: string;
  startTime: number;
  endTime?: number;
  totalActions?: number;
  successfulActions?: number;
  failedActions?: number;
  summary?: string;
  modelType?: string;
  currentIteration?: number;
}

/* ============ 执行日志 ============ */

export interface ActionLogEntry {
  timestamp: number;
  action: string;
  target?: string;
  result?: string;
  actionId?: string;
  status?: 'pending' | 'executing' | 'success' | 'failed';
  iteration?: number;
  reasoning?: string;
}

export interface ExecutionLogEntry {
  timestamp: number;
  level: 'info' | 'warn' | 'error' | 'debug';
  message: string;
  source?: string;
  toolName?: string;
}

/* ============ 后端配置 ============ */

export interface BackendConfig {
  serverUrl: string;
  provider: string;
  model: string;
  apiKey?: string;
  baseUrl?: string;
  temperature: number;
  maxTokens: number;
  langchainCompat?: boolean;
  langchainInstalled?: boolean;
  remoteFallbackProvider?: string;
  cloudProviders?: CloudProviderConfig[];
}

export interface CloudProviderConfig {
  provider: string;
  baseUrl?: string;
  model: string;
  hasApiKey: boolean;
}

/* ============ 待审批工具 ============ */

export interface PendingTool {
  tool_name: string;
  filename: string;
}

/* ============ 文件下载 ============ */

export interface FileInfo {
  name: string;
  path: string;
  size: number;
  sizeFormatted: string;
  extension: string;
  icon: string;
  exists: boolean;
  isFile: boolean;
  modifiedAt?: string;
}

/* ============ WebSocket 消息 ============ */

export type WSMessageType =
  /* 连接 */
  | 'connected'
  | 'session_init'
  /* 流式聊天 */
  | 'content'
  | 'done'
  | 'stopped'
  | 'error'
  | 'retry'
  /* 工具 */
  | 'tool_call'
  | 'tool_result'
  | 'tools_updated'
  /* 执行日志 */
  | 'execution_log'
  /* LLM 请求跟踪 */
  | 'llm_request_start'
  | 'llm_request_end'
  /* 自主任务 */
  | 'task_start'
  | 'task_complete'
  | 'model_selected'
  | 'action_plan'
  | 'action_executing'
  | 'action_result'
  | 'reflect_start'
  | 'reflect_result'
  /* 图片 */
  | 'image'
  | 'screenshot'
  /* 系统通知 */
  | 'system_notification'
  /* Duck 任务 */
  | 'duck_task_complete'
  | 'duck_task_retry'
  | 'duck_task_progress'
  | 'auto_delegated_to_duck'
  /* 心跳 */
  | 'server_ping'
  /* 监控 */
  | 'monitor_event'
  /* 恢复 */
  | 'resume_chat_result'
  /* 升级 */
  | 'upgrade_complete'
  | 'upgrade_error'
  /* 群聊 */
  | 'group_chat_created'
  | 'group_message'
  | 'group_status_update'
  /* 兼容旧类型 */
  | 'chat_response'
  | 'chat_chunk'
  | 'chat_complete'
  | 'thinking_chunk'
  | 'tool_call_start'
  | 'tool_call_result'
  | 'system_message'
  | 'task_progress'
  | 'action_log';

export interface WSMessage {
  type: WSMessageType;
  [key: string]: unknown;
}

/* ============ 群聊（多 Agent 协作） ============ */

export type GroupChatStatus = 'active' | 'completed' | 'failed' | 'cancelled';
export type ParticipantRole = 'main' | 'duck' | 'system' | 'monitor';
export type GroupMessageType =
  | 'text'
  | 'task_assign'
  | 'task_progress'
  | 'task_complete'
  | 'task_failed'
  | 'status_update'
  | 'plan'
  | 'conclusion'
  | 'monitor_report';

export interface GroupParticipant {
  participant_id: string;
  name: string;
  role: ParticipantRole;
  duck_type?: string;
  emoji: string;
  joined_at: number;
}

export interface GroupMessage {
  msg_id: string;
  sender_id: string;
  sender_name: string;
  sender_role: ParticipantRole;
  msg_type: GroupMessageType;
  content: string;
  mentions: string[];
  metadata: Record<string, unknown>;
  timestamp: number;
}

export interface GroupTaskSummary {
  total?: number;
  completed?: number;
  failed?: number;
  running?: number;
  pending?: number;
}

export interface GroupChat {
  group_id: string;
  title: string;
  session_id: string;
  dag_id?: string;
  status: GroupChatStatus;
  participants: GroupParticipant[];
  messages: GroupMessage[];
  task_summary: GroupTaskSummary;
  created_at: number;
  completed_at?: number;
}

export interface GroupChatBrief {
  group_id: string;
  title: string;
  session_id: string;
  dag_id?: string;
  status: GroupChatStatus;
  participant_count: number;
  message_count: number;
  task_summary: GroupTaskSummary;
  created_at: number;
  completed_at?: number;
  last_message?: GroupMessage;
}
