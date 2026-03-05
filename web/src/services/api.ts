import type { FileInfo } from '../types';

const API_BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`API ${res.status}: ${body || res.statusText}`);
  }
  return res.json();
}

/* ===== 健康检查 ===== */
export async function getHealth(): Promise<{ status: string }> {
  return request('/health');
}

/* ===== 配置 ===== */
export async function getConfig(): Promise<Record<string, unknown>> {
  return request('/config');
}

export async function updateConfig(config: Record<string, unknown>): Promise<void> {
  await request('/config', { method: 'POST', body: JSON.stringify(config) });
}

/* ===== 工具列表 ===== */
export async function getTools(): Promise<{ tools: unknown[] }> {
  return request('/tools');
}

/* ===== 系统消息 ===== */
export async function getSystemMessages(): Promise<{ messages: unknown[] }> {
  return request('/system-messages');
}

/* ===== 文件下载 ===== */
export async function getFileInfo(path: string): Promise<FileInfo> {
  return request(`/files/info?path=${encodeURIComponent(path)}`);
}

export function getFileDownloadUrl(path: string): string {
  return `${API_BASE}/files/download?path=${encodeURIComponent(path)}`;
}

export async function getFilePreview(path: string): Promise<{ content: string; truncated: boolean }> {
  return request(`/files/preview?path=${encodeURIComponent(path)}`);
}

/* ===== 会话 ===== */
export async function getConversations(): Promise<{ conversations: unknown[] }> {
  return request('/conversations');
}

export async function deleteConversation(id: string): Promise<void> {
  await request(`/conversations/${id}`, { method: 'DELETE' });
}

/* ===== 任务 ===== */
export async function getTasks(): Promise<{ tasks: unknown[] }> {
  return request('/tasks');
}

export async function cancelTask(taskId: string): Promise<void> {
  await request(`/tasks/${taskId}/cancel`, { method: 'POST' });
}
