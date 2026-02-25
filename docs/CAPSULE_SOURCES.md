# Capsule 技能库 — 双策略架构

## 架构概览

```
┌─────────────────────────────────────────────────┐
│               Capsule Bootstrap                  │
│         (启动时自动加载 + 注册)                   │
├─────────────┬───────────────────────────────────┤
│  始终加载    │        按策略选择其一               │
│             │                                    │
│ ./capsules/ │  Strategy 1      Strategy 2        │
│ (本地 JSON) │  (EvoMap 预留)   (开源 Skills)      │
│             │  ↓               ↓                 │
│             │  EvoMap 网络     anthropics/skills  │
│             │  (需授权码)      skillcreatorai/... │
│             │                  (无需任何授权)      │
├─────────────┴───────────────────────────────────┤
│            CapsuleRegistry (本地注册表)           │
│         → Agent 通过 capsule 工具调用             │
└─────────────────────────────────────────────────┘
```

## 策略切换

| 策略 | 触发条件 | 来源 | 状态 |
|------|---------|------|------|
| **Strategy 1 — EvoMap** | 环境变量 `EVOMAP_AUTH_CODE` 存在 | EvoMap 官方网络 | 预留（待授权码） |
| **Strategy 2 — Open Skills** | 默认（无 `EVOMAP_AUTH_CODE`） | GitHub 公开仓库 | **当前生效** |

切换方式：
```bash
# 激活 Strategy 1（拿到 EvoMap 授权码后）
export EVOMAP_AUTH_CODE="your-auth-code-here"

# 回到 Strategy 2（删除或留空即可）
unset EVOMAP_AUTH_CODE
```

## Strategy 2 — 开源技能来源

### 内置源（默认启用）

| 源 | 仓库 | 技能数 | 内容 |
|----|------|--------|------|
| **Anthropic Skills** | [anthropics/skills](https://github.com/anthropics/skills) | ~50+ | PDF、文档、设计、测试、MCP 构建等 |
| **AI Agent Skills** | [skillcreatorai/Ai-Agent-Skills](https://github.com/skillcreatorai/Ai-Agent-Skills) | 47+ | 前端、后端、代码审查、Excel、PPT、搜索等 |

### 如何工作

1. 启动时，`capsule_bootstrap` 检测 `EVOMAP_AUTH_CODE` → 选择策略
2. Strategy 2 通过 GitHub API 递归扫描上述仓库的 `skills/` 目录
3. 找到 `SKILL.md` 文件 → `skill_adapter.py` 解析 YAML frontmatter + Markdown 正文
4. 转换为 `SkillCapsule` 格式 → 写入 `capsules_cache/open_skills/`
5. 校验后注册到 `CapsuleRegistry`
6. Agent 可通过 `capsule(action=find, task="pdf")` 查找并使用

### 格式转换

SKILL.md (Agent Skills 规范):
```markdown
---
name: pdf
description: Extract, create, merge, split PDFs
---
# PDF Skill
## Extraction
Extract text, tables, forms from PDF files...
```

转换为 SkillCapsule:
```json
{
  "id": "skill_pdf",
  "description": "Extract, create, merge, split PDFs",
  "inputs": { "task": { "type": "string" } },
  "outputs": { "result": { "type": "object" } },
  "procedure": [
    { "id": "step_0", "type": "subtask", "description": "[Extraction] Extract text..." }
  ],
  "tags": ["agent-skill", "pdf"],
  "source": "github:anthropics/skills"
}
```

### 添加自定义开源源

编辑 `backend/config/capsule_sources.json`：

```json
{
  "open_skill_sources": [
    {
      "id": "my_custom_skills",
      "name": "My Custom Skills",
      "owner": "my-github-user",
      "repo": "my-skills-repo",
      "branch": "main",
      "path": "skills",
      "enabled": true
    }
  ]
}
```

只要仓库里有 `SKILL.md` 文件就会被识别和转换。

## 本地 Capsule（始终加载）

`backend/capsules/` 目录中的 JSON/YAML 文件始终会被加载，不受策略切换影响。
这些是你手写的、可直接执行的 Capsule（支持 tool 调用、条件、重试、并行等）。

项目已自带示例：
- `example_screenshot.json` — 截图
- `example_terminal.json` — 终端命令
- `example_multi_step.json` — 多步骤 + 条件 + 重试
- `example_parallel.json` — 并行步骤
- `example_retry_fallback.json` — 重试 + 回退
- `example_gep_capsule.json` — GEP 格式自动转换

## 环境变量参考

| 变量 | 说明 | 默认 |
|------|------|------|
| `EVOMAP_AUTH_CODE` | EvoMap 授权码，设置后激活 Strategy 1 | （空 → Strategy 2） |
| `GITHUB_TOKEN` | GitHub Personal Access Token，提高 API 速率限制 | （空 → 匿名，60次/小时） |
| `CAPSULE_SOURCES` | 逗号分隔的自定义 Capsule JSON 源 URL | （空） |
