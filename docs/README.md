# MacAgent 文档

MacAgent 是 macOS 系统级智能助手，可代表用户执行终端、文件、截图、邮件等操作。本目录为主线设计与运维文档，归档与专项见 `archive/`。

**推荐阅读顺序**：1）[backend-structure.md](backend-structure.md) 了解后端结构 → 2）[主线目标与路线图.md](主线目标与路线图.md) 看目标与阶段 → 3）[痛点分析与解决方案.md](痛点分析与解决方案.md) 看问题与方案；测试与验收按需查阅。

---

## 主线目标点

| 维度 | 当前 | 2026 标杆目标 | Claude Code 对齐目标 |
|------|------|----------------|----------------------|
| **状态** | v3 + v3.1（memory/规划/escalation/反思/安全/trace/首步加固/MACAGENT.md） | 可观测（trace+执行轨迹）+ 可评估（benchmark）+ 安全与运维（沙箱、审计、/health/deep）；幂等、HITL、回滚 | 主循环三阶段（含显式 Verify）、会话 resume/fork、checkpoint、Extended Thinking；可选 Subagent |
| **里程碑** | Phase A（文档+稳定性）✅ Phase B（体验对齐）✅ | v3.2：trace 完善、benchmark 自动化、沙箱、/health/deep | Phase C（重要性 memory、反思模板、CoT/Subagent）待做 |

---

## 主线文档（5 个）

| 文档 | 用途 |
|------|------|
| [主线目标与路线图.md](主线目标与路线图.md) | 2026 标杆 + Claude Code 进化 + Phase A/B/C + 版本路线 |
| [backend-structure.md](backend-structure.md) | 后端目录与模块说明 |
| [痛点分析与解决方案.md](痛点分析与解决方案.md) | 当前痛点与 P0/P1/P2 方案 |
| [测试与验收.md](测试与验收.md) | v3.1 测试、自愈测试、benchmark 与验收入口 |
| [V3.1_PLAN.md](V3.1_PLAN.md) | v3.1 功能清单与和 v3 关系（细节见主线路线图） |

**归档**：历史与专项文档（v3 升级、iOS、TTS、企业级、打包等）见 [archive/](archive/)，不参与主线阅读。

---

## 相关

- Agent 项目上下文（供注入）：`backend/data/prompts/MACAGENT.md`
