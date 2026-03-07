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

/* ===== Duck 管理 ===== */
export async function getDuckList(duckType?: string, status?: string): Promise<{ ducks: any[] }> {
  const params = new URLSearchParams();
  if (duckType) params.set('duck_type', duckType);
  if (status) params.set('status', status);
  const qs = params.toString();
  return request(`/duck/list${qs ? '?' + qs : ''}`);
}

export async function getDuckStats(): Promise<{
  total: number; online: number; busy: number; offline: number;
  total_completed: number; total_failed: number; by_type: Record<string, number>;
}> {
  return request('/duck/stats');
}

export async function getDuckTemplates(): Promise<{ count: number; templates: any[] }> {
  return request('/duck/templates');
}

export async function createLocalDuck(name: string, duckType: string, skills: string[] = []): Promise<{ status: string; duck: any }> {
  return request('/duck/create-local', {
    method: 'POST',
    body: JSON.stringify({ name, duck_type: duckType, skills }),
  });
}

export async function destroyLocalDuck(duckId: string): Promise<void> {
  await request(`/duck/local/${duckId}`, { method: 'DELETE' });
}

export async function startLocalDuck(duckId: string): Promise<{ status: string; duck: any }> {
  return request(`/duck/local/${duckId}/start`, { method: 'POST' });
}

export async function updateDuckLLMConfig(duckId: string, apiKey: string, baseUrl: string, model: string): Promise<{ status: string; duck: any }> {
  return request(`/duck/local/${duckId}/llm-config`, {
    method: 'PUT',
    body: JSON.stringify({ api_key: apiKey, base_url: baseUrl, model }),
  });
}

export async function getLocalDucks(): Promise<{ count: number; ducks: any[] }> {
  return request('/duck/local/list');
}

export async function removeDuck(duckId: string): Promise<void> {
  await request(`/duck/remove/${duckId}`, { method: 'DELETE' });
}

/* ===== Egg 管理 ===== */
export async function createEgg(duckType: string, name?: string, mainAgentUrl?: string): Promise<{ status: string; egg: any }> {
  return request('/duck/create-egg', {
    method: 'POST',
    body: JSON.stringify({ duck_type: duckType, name, main_agent_url: mainAgentUrl }),
  });
}

export async function getEggs(): Promise<{ count: number; eggs: any[] }> {
  return request('/duck/eggs');
}

export function getEggDownloadUrl(eggId: string): string {
  return `${API_BASE}/duck/egg/${eggId}/download`;
}

export async function deleteEgg(eggId: string): Promise<void> {
  await request(`/duck/egg/${eggId}`, { method: 'DELETE' });
}
