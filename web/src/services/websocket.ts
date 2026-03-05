import type { WSMessage, WSMessageType } from '../types';

type Listener = (msg: WSMessage) => void;

class WebSocketService {
  private ws: WebSocket | null = null;
  private listeners = new Map<WSMessageType | '*', Set<Listener>>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay = 1000;
  private maxReconnectDelay = 30000;
  private manualClose = false;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  sessionId: string | null = null;
  hasRunningTask = false;
  hasRunningChat = false;
  runningTaskId: string | null = null;

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  get readyState(): number {
    return this.ws?.readyState ?? WebSocket.CLOSED;
  }

  connect(url?: string) {
    if (this.ws && this.ws.readyState < WebSocket.CLOSING) return;
    this.manualClose = false;

    // 同源 /ws，由 Vite 代理到后端（支持 localhost 与 chowduck.cn tunnel）
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = url ?? `${protocol}//${window.location.host}/ws`;
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log('[WS] connected');
      this.reconnectDelay = 1000;
      // 不在这里 emit session_init，等待服务端发回 connected 消息
    };

    this.ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data);

        // 处理后端发送的 connected 消息
        if (msg.type === 'connected') {
          this.sessionId = msg.session_id as string;
          this.hasRunningTask = !!msg.has_running_task;
          this.hasRunningChat = !!msg.has_running_chat;
          this.runningTaskId = (msg.running_task_id as string) ?? null;
          // 通知连接已建立
          const { type: _origType, ...rest } = msg;
          this.emit({ type: 'session_init', _status: 'connected', ...rest });
          return;
        }

        // 处理心跳
        if (msg.type === 'server_ping') {
          this.send({ type: 'pong' });
          return;
        }

        this.emit(msg);
      } catch (e) {
        console.error('[WS] parse error:', e);
      }
    };

    this.ws.onclose = () => {
      console.log('[WS] disconnected');
      this.stopPing();
      this.emit({ type: 'session_init', _status: 'disconnected' });
      if (!this.manualClose) this.scheduleReconnect();
    };

    this.ws.onerror = (err) => {
      console.error('[WS] error:', err);
    };
  }

  disconnect() {
    this.manualClose = true;
    this.stopPing();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  reconnect() {
    this.disconnect();
    this.manualClose = false;
    setTimeout(() => this.connect(), 100);
  }

  send(data: Record<string, unknown>) {
    if (!this.connected) {
      console.warn('[WS] not connected, cannot send');
      return;
    }
    this.ws!.send(JSON.stringify(data));
  }

  sendChat(content: string, sessionId?: string) {
    this.send({
      type: 'chat',
      content,
      session_id: sessionId ?? this.sessionId,
    });
  }

  sendStopGeneration() {
    this.send({ type: 'stop', session_id: this.sessionId });
  }

  sendAutonomousTask(task: string, options?: {
    enableModelSelection?: boolean;
    preferLocal?: boolean;
  }) {
    this.send({
      type: 'autonomous_task',
      task,
      session_id: this.sessionId,
      enable_model_selection: options?.enableModelSelection,
      prefer_local: options?.preferLocal,
    });
  }

  sendResumeTask(sessionId: string) {
    this.send({ type: 'resume_task', session_id: sessionId });
  }

  sendResumeChat(sessionId: string) {
    this.send({ type: 'resume_chat', session_id: sessionId });
  }

  sendClearSession(sessionId: string) {
    this.send({ type: 'clear_session', session_id: sessionId });
  }

  on(type: WSMessageType | '*', listener: Listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(listener);
    return () => this.off(type, listener);
  }

  off(type: WSMessageType | '*', listener: Listener) {
    this.listeners.get(type)?.delete(listener);
  }

  private emit(msg: WSMessage) {
    this.listeners.get(msg.type)?.forEach((fn) => fn(msg));
    this.listeners.get('*')?.forEach((fn) => fn(msg));
  }

  private stopPing() {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) return;
    console.log(`[WS] reconnecting in ${this.reconnectDelay}ms...`);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
      this.connect();
    }, this.reconnectDelay);
  }
}

export const wsService = new WebSocketService();
export default wsService;
