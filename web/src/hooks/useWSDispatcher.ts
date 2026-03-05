import { useEffect } from 'react';
import { useWSStore } from '../stores/wsStore';
import { useChatStore } from '../stores/chatStore';
import { useMonitorStore } from '../stores/monitorStore';
import { useNotificationStore } from '../stores/notificationStore';
import { useToolStore } from '../stores/toolStore';
import { getTools } from '../services/api';
import type { WSMessage } from '../types';

/**
 * 处理 WebSocket 消息并更新所有 Stores
 * 兼容后端实际协议 + 旧协议
 */
export function useWSDispatcher() {
  const onMessage = useWSStore((s) => s.onMessage);

  useEffect(() => {
    const unsubs: (() => void)[] = [];

    // 辅助函数：获取当前活跃会话和 assistant 消息 ID
    const getActiveAssistant = () => {
      const store = useChatStore.getState();
      const conv = store.getActiveConversation();
      if (!conv) return null;
      const msgs = conv.messages;
      const last = msgs[msgs.length - 1];
      if (last?.role === 'assistant' && last.isStreaming) {
        return { convId: conv.id, msgId: last.id };
      }
      return null;
    };

    /* ============= 后端原生协议 ============= */

    /* 流式文本 content */
    unsubs.push(onMessage('content', (msg: WSMessage) => {
      const content = msg.content as string;
      if (!content) return;
      const target = getActiveAssistant();
      if (target) {
        useChatStore.getState().appendToMessage(target.convId, target.msgId, content);
        useMonitorStore.getState().appendNeuralStream(content);
        useMonitorStore.getState().setIsStreaming(true);
      }
    }));

    /* 完成 done */
    unsubs.push(onMessage('done', (msg: WSMessage) => {
      const target = getActiveAssistant();
      if (target) {
        const patch: Record<string, unknown> = { isStreaming: false };
        if (msg.model) patch.modelName = msg.model;
        if (msg.usage) {
          const u = msg.usage as any;
          patch.tokenUsage = {
            promptTokens: u.prompt_tokens ?? 0,
            completionTokens: u.completion_tokens ?? 0,
            totalTokens: u.total_tokens ?? 0,
          };
          // 更新用量统计
          useMonitorStore.getState().updateUsageStats({
            totalRequests: useMonitorStore.getState().usageStats.totalRequests + 1,
            successCount: useMonitorStore.getState().usageStats.successCount + 1,
            totalTokens: useMonitorStore.getState().usageStats.totalTokens + (u.total_tokens ?? 0),
            inputTokens: useMonitorStore.getState().usageStats.inputTokens + (u.prompt_tokens ?? 0),
            outputTokens: useMonitorStore.getState().usageStats.outputTokens + (u.completion_tokens ?? 0),
          });
        }
        useChatStore.getState().updateMessage(target.convId, target.msgId, patch as any);
      }
      useChatStore.getState().setStreaming(false);
      useMonitorStore.getState().setIsStreaming(false);
    }));

    /* 停止 stopped */
    unsubs.push(onMessage('stopped', (_msg: WSMessage) => {
      const target = getActiveAssistant();
      if (target) {
        useChatStore.getState().updateMessage(target.convId, target.msgId, { isStreaming: false });
      }
      useChatStore.getState().setStreaming(false);
      useMonitorStore.getState().setIsStreaming(false);
    }));

    /* 错误 error */
    unsubs.push(onMessage('error', (msg: WSMessage) => {
      console.error('[WS Error]', msg);
      const target = getActiveAssistant();
      if (target) {
        const errText = (msg.message as string) ?? 'Unknown error';
        useChatStore.getState().appendToMessage(target.convId, target.msgId, `\n\n> ⚠️ 错误: ${errText}`);
        useChatStore.getState().updateMessage(target.convId, target.msgId, { isStreaming: false });
      }
      useChatStore.getState().setStreaming(false);
      useMonitorStore.getState().setIsStreaming(false);
      const errMsg = (msg.message as string) ?? JSON.stringify(msg);
      useNotificationStore.getState().addNotification('error', errMsg);
    }));

    /* 重试 retry */
    unsubs.push(onMessage('retry', (msg: WSMessage) => {
      const text = (msg.message as string) ?? '正在重试…';
      useNotificationStore.getState().addNotification('warning', text);
    }));

    /* 工具调用 tool_call */
    unsubs.push(onMessage('tool_call', (msg: WSMessage) => {
      const toolName = msg.tool_name as string;
      const toolArgs = (msg.tool_args as Record<string, unknown>) ?? {};
      const callId = `tc_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

      const target = getActiveAssistant();
      if (target) {
        const store = useChatStore.getState();
        const conv = store.conversations.find(c => c.id === target.convId);
        const m = conv?.messages.find(m => m.id === target.msgId);
        const existing = m?.toolCalls ?? [];
        store.updateMessage(target.convId, target.msgId, {
          toolCalls: [...existing, {
            id: callId,
            toolName,
            arguments: toolArgs,
            status: 'running',
            startTime: Date.now(),
          }],
        });
      }

      useToolStore.getState().addCallToHistory({
        id: callId,
        toolName,
        arguments: toolArgs,
        status: 'running',
        startTime: Date.now(),
      });

      useMonitorStore.getState().addStep({
        id: callId,
        action: `调用工具: ${toolName}`,
        status: 'executing',
        startTime: Date.now(),
      });
    }));

    /* 工具结果 tool_result */
    unsubs.push(onMessage('tool_result', (msg: WSMessage) => {
      const toolName = msg.tool_name as string;
      const success = msg.success as boolean;
      const result = (msg.result as string) ?? '';

      // 找到最近一个 running 状态的同名工具调用
      const toolStore = useToolStore.getState();
      const runningCall = [...toolStore.callHistory].reverse().find(
        c => c.toolName === toolName && c.status === 'running'
      );
      const callId = runningCall?.id;
      const status = success ? 'success' as const : 'error' as const;

      if (callId) {
        const target = getActiveAssistant();
        if (target) {
          const store = useChatStore.getState();
          const conv = store.conversations.find(c => c.id === target.convId);
          const m = conv?.messages.find(m => m.id === target.msgId);
          const toolCalls = (m?.toolCalls ?? []).map(tc =>
            tc.id === callId ? { ...tc, status, result, endTime: Date.now() } : tc
          );
          store.updateMessage(target.convId, target.msgId, { toolCalls });
        }
        toolStore.updateCallInHistory(callId, { status, result, endTime: Date.now() });
        useMonitorStore.getState().updateStep(callId, {
          status: success ? 'success' : 'failed',
          result,
          endTime: Date.now(),
        });
      }
    }));

    /* 工具列表更新 tools_updated */
    unsubs.push(onMessage('tools_updated', (_msg: WSMessage) => {
      getTools().then((res) => useToolStore.getState().setTools(res.tools as any)).catch(() => {});
    }));

    /* 执行日志 execution_log */
    unsubs.push(onMessage('execution_log', (msg: WSMessage) => {
      useMonitorStore.getState().addLog({
        timestamp: Date.now(),
        level: (msg.level as any) ?? 'info',
        message: (msg.message as string) ?? '',
        source: msg.tool_name as string,
        toolName: msg.tool_name as string,
      });
    }));

    /* LLM 请求开始 */
    unsubs.push(onMessage('llm_request_start', (msg: WSMessage) => {
      const provider = msg.provider as string;
      const model = msg.model as string;
      const iteration = msg.iteration as number;
      useMonitorStore.getState().addStep({
        id: `llm_${Date.now()}`,
        action: `LLM 请求 #${iteration}: ${provider}/${model}`,
        status: 'executing',
        startTime: Date.now(),
      });
    }));

    /* LLM 请求结束 */
    unsubs.push(onMessage('llm_request_end', (msg: WSMessage) => {
      const usage = msg.usage as any;
      if (usage) {
        useMonitorStore.getState().updateUsageStats({
          totalRequests: useMonitorStore.getState().usageStats.totalRequests + 1,
          successCount: msg.error ? useMonitorStore.getState().usageStats.successCount : useMonitorStore.getState().usageStats.successCount + 1,
          totalTokens: useMonitorStore.getState().usageStats.totalTokens + (usage.total_tokens ?? 0),
          inputTokens: useMonitorStore.getState().usageStats.inputTokens + (usage.prompt_tokens ?? 0),
          outputTokens: useMonitorStore.getState().usageStats.outputTokens + (usage.completion_tokens ?? 0),
        });
      }
    }));

    /* 图片 */
    unsubs.push(onMessage('image', (msg: WSMessage) => {
      const target = getActiveAssistant();
      if (target) {
        const store = useChatStore.getState();
        const conv = store.conversations.find(c => c.id === target.convId);
        const m = conv?.messages.find(m => m.id === target.msgId);
        const images = m?.images ?? [];
        store.updateMessage(target.convId, target.msgId, {
          images: [...images, {
            base64: msg.base64 as string,
            mimeType: (msg.mime_type as string) ?? 'image/png',
            path: msg.path as string,
          }],
        });
      }
    }));

    /* 截图 */
    unsubs.push(onMessage('screenshot', (msg: WSMessage) => {
      const target = getActiveAssistant();
      if (target) {
        const store = useChatStore.getState();
        const conv = store.conversations.find(c => c.id === target.convId);
        const m = conv?.messages.find(m => m.id === target.msgId);
        const images = m?.images ?? [];
        store.updateMessage(target.convId, target.msgId, {
          images: [...images, {
            base64: msg.image_base64 as string,
            mimeType: (msg.mime_type as string) ?? 'image/png',
            path: msg.screenshot_path as string,
          }],
        });
      }
    }));

    /* ============= 自主任务事件 ============= */

    /* 任务开始 */
    unsubs.push(onMessage('task_start', (msg: WSMessage) => {
      useToolStore.getState().setActiveTask({
        taskId: msg.task_id as string,
        status: 'running',
        progress: 0,
        description: (msg.task as string) ?? '',
        startTime: Date.now(),
        totalActions: 0,
        successfulActions: 0,
        failedActions: 0,
      });
      const target = getActiveAssistant();
      if (target) {
        useChatStore.getState().appendToMessage(
          target.convId, target.msgId,
          `🚀 **任务已启动**\n\n`
        );
      }
    }));

    /* 模型选择 */
    unsubs.push(onMessage('model_selected', (msg: WSMessage) => {
      const target = getActiveAssistant();
      if (target) {
        useChatStore.getState().appendToMessage(
          target.convId, target.msgId,
          `📡 模型选择: **${msg.model_type}** (${msg.reason})\n\n`
        );
      }
      useToolStore.getState().updateTaskProgress({ modelType: msg.model_type as string });
    }));

    /* 动作规划 */
    unsubs.push(onMessage('action_plan', (msg: WSMessage) => {
      const action = msg.action as any;
      const iteration = msg.iteration as number;
      const actionId = action?.action_id ?? `ap_${Date.now()}`;

      const target = getActiveAssistant();
      if (target) {
        useChatStore.getState().appendToMessage(
          target.convId, target.msgId,
          `\n**步骤 ${iteration}**: ${action?.action_type ?? '执行'}\n> ${action?.reasoning ?? ''}\n\n`
        );
      }

      useMonitorStore.getState().addStep({
        id: actionId,
        action: `Step ${iteration}: ${action?.action_type ?? ''}`,
        target: action?.reasoning,
        status: 'pending',
        startTime: Date.now(),
      });

      useMonitorStore.getState().addActionLog({
        timestamp: Date.now(),
        action: action?.action_type ?? '',
        actionId,
        reasoning: action?.reasoning,
        iteration,
        status: 'pending',
      });
    }));

    /* 动作执行中 */
    unsubs.push(onMessage('action_executing', (msg: WSMessage) => {
      const actionId = msg.action_id as string;
      useMonitorStore.getState().updateStep(actionId, { status: 'executing' });
    }));

    /* 动作结果 */
    unsubs.push(onMessage('action_result', (msg: WSMessage) => {
      const actionId = msg.action_id as string;
      const success = msg.success as boolean;
      const output = (msg.output as string) ?? '';
      const error = msg.error as string;

      useMonitorStore.getState().updateStep(actionId, {
        status: success ? 'success' : 'failed',
        result: success ? output : error,
        endTime: Date.now(),
      });

      const target = getActiveAssistant();
      if (target) {
        const status = success ? '✅' : '❌';
        const text = success ? output.slice(0, 200) : error;
        useChatStore.getState().appendToMessage(
          target.convId, target.msgId,
          `${status} ${text ? `\`${text}\`` : ''}\n\n`
        );
      }

      // 更新任务进度
      const task = useToolStore.getState().activeTask;
      if (task) {
        useToolStore.getState().updateTaskProgress({
          totalActions: (task.totalActions ?? 0) + 1,
          successfulActions: success ? (task.successfulActions ?? 0) + 1 : task.successfulActions,
          failedActions: !success ? (task.failedActions ?? 0) + 1 : task.failedActions,
          progress: Math.min(95, (task.progress ?? 0) + 5),
        });
      }
    }));

    /* 反思开始 */
    unsubs.push(onMessage('reflect_start', (_msg: WSMessage) => {
      const target = getActiveAssistant();
      if (target) {
        useChatStore.getState().appendToMessage(
          target.convId, target.msgId,
          `\n🔍 **反思分析中…**\n\n`
        );
      }
    }));

    /* 反思结果 */
    unsubs.push(onMessage('reflect_result', (msg: WSMessage) => {
      const reflection = msg.reflection as string;
      const target = getActiveAssistant();
      if (target && reflection) {
        useChatStore.getState().appendToMessage(
          target.convId, target.msgId,
          `> ${reflection}\n\n`
        );
      }
    }));

    /* 任务完成 */
    unsubs.push(onMessage('task_complete', (msg: WSMessage) => {
      const success = msg.success as boolean;
      const summary = (msg.summary as string) ?? '';
      const totalActions = msg.total_actions as number;

      const target = getActiveAssistant();
      if (target) {
        const icon = success ? '🎉' : '😞';
        useChatStore.getState().appendToMessage(
          target.convId, target.msgId,
          `\n---\n${icon} **任务${success ? '完成' : '失败'}** (共 ${totalActions ?? 0} 步)\n\n${summary}\n`
        );
        useChatStore.getState().updateMessage(target.convId, target.msgId, { isStreaming: false });
      }
      useChatStore.getState().setStreaming(false);
      useMonitorStore.getState().setIsStreaming(false);

      useToolStore.getState().updateTaskProgress({
        status: success ? 'completed' : 'failed',
        progress: 100,
        summary,
        endTime: Date.now(),
      });
    }));

    /* 系统通知 */
    unsubs.push(onMessage('system_notification', (msg: WSMessage) => {
      const notification = msg.notification as any;
      if (notification) {
        useNotificationStore.getState().addNotification(
          notification.level ?? 'info',
          notification.content ?? notification.title ?? ''
        );
      }
    }));

    /* ============= 兼容旧协议（fallback） ============= */

    unsubs.push(onMessage('chat_chunk', (msg: WSMessage) => {
      const chunk = (msg as any).data?.chunk ?? (msg as any).chunk;
      if (chunk) {
        const target = getActiveAssistant();
        if (target) {
          useChatStore.getState().appendToMessage(target.convId, target.msgId, chunk);
          useMonitorStore.getState().appendNeuralStream(chunk);
          useMonitorStore.getState().setIsStreaming(true);
        }
      }
    }));

    unsubs.push(onMessage('thinking_chunk', (msg: WSMessage) => {
      const chunk = (msg as any).data?.chunk ?? (msg as any).chunk;
      if (chunk) {
        const target = getActiveAssistant();
        if (target) {
          useChatStore.getState().appendThinking(target.convId, target.msgId, chunk);
        }
      }
    }));

    unsubs.push(onMessage('chat_complete', (_msg: WSMessage) => {
      const target = getActiveAssistant();
      if (target) {
        useChatStore.getState().updateMessage(target.convId, target.msgId, { isStreaming: false });
      }
      useChatStore.getState().setStreaming(false);
      useMonitorStore.getState().setIsStreaming(false);
    }));

    unsubs.push(onMessage('system_message', (msg: WSMessage) => {
      const text = (msg as any).data?.message ?? (msg as any).message;
      const level = (msg as any).data?.level ?? (msg as any).level ?? 'info';
      useNotificationStore.getState().addNotification(level, text ?? JSON.stringify(msg));
    }));

    unsubs.push(onMessage('task_progress', (msg: WSMessage) => {
      const data = (msg as any).data ?? msg;
      useToolStore.getState().setActiveTask({
        taskId: data.task_id,
        status: data.status ?? 'running',
        progress: data.progress ?? 0,
        description: data.description ?? '',
        startTime: Date.now(),
      });
    }));

    return () => unsubs.forEach(u => u());
  }, [onMessage]);
}
