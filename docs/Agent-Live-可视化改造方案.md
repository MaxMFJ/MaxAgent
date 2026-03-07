# Agent Live 可视化改造方案

> 参考 Agent World (OpenClaw)、OpenClawViewer，将「日志式」展示升级为「图形化执行可视化」

---

## 一、现状 vs 目标

| 维度 | 当前（Cyberdeck Terminal） | 目标（Agent World 风格） |
|------|---------------------------|--------------------------|
| **呈现方式** | 终端文本、[LOG]、[STREAM] | 图形化节点、连线、粒子流 |
| **信息传达** | 读文字理解 | 一眼看懂「谁在动、数据往哪流」 |
| **隐喻** | 命令行输出 | 控制室、神经网、执行链 |
| **设计风格** | 赛博朋克 ✓ | 保持 ✓ |

---

## 二、Agent World / OpenClawViewer 核心特征

- **Agent World**：像素风控制室，Agent 以角色形式存在，打字/阅读/执行有动画；子 Agent 链以连接角色展示
- **OpenClawViewer**：Agent Network（可旋转图）、Activity Pulse、Live Feed
- **共同点**：**节点 + 连线 + 实时状态**，而非纯文本

---

## 三、推荐方案：Neural Canvas + Terminal 双区

在保留 Cyberdeck 风格的前提下，**上方增加 Neural Canvas（神经网画布）**，下方保留终端作为「详情」。

```
┌─────────────────────────────────────────────────────────┐
│  [NEURAL CANVAS]  中心 AI 节点 + 工具环 + 粒子流          │
│       🧠 ←──→ 🔧  run_shell                              │
│        \    /                                            │
│         \  /  ← 光点从中心流向被调用的工具                │
│          📁  read_file                                   │
├─────────────────────────────────────────────────────────┤
│  [TERMINAL]  STANDBY / PROCESSING / EXECUTE + [LOG]      │
│  保留现有终端内容，作为「详情」或折叠区                    │
└─────────────────────────────────────────────────────────┘
```

### 3.1 Neural Canvas 元素

| 元素 | 视觉 | 数据驱动 |
|------|------|----------|
| **中心节点** | AI 大脑图标，思考时紫色脉动 | `isStreamingLLM` |
| **工具环** | 6–8 个工具图标沿圆周排布 | `recentToolCalls` / `actionLogs` 提取类型 |
| **高亮节点** | 当前/最近调用的工具发光、放大 | `displayTool` |
| **连线** | 中心 → 高亮工具的虚线/实线 | 执行时显示 |
| **粒子流** | 光点从中心沿连线流向工具 | `displayTool != nil` 且执行中 |
| **执行链** | 可选：最近 3–5 步为横向节点流 | `actionLogs` 最近几条 |

### 3.2 工具类型 → SF Symbol 映射

| action_type | Symbol |
|-------------|--------|
| run_shell, create_and_run_script | `terminal` |
| read_file, write_file, list_directory | `doc.text` |
| call_tool (screenshot) | `camera.viewfinder` |
| call_tool (web_search) | `globe` |
| call_tool (mail) | `envelope` |
| call_tool (capsule) | `brain.head.profile` |
| 其他 call_tool | `wrench.and.screwdriver` |
| open_app | `app.badge` |
| think | `brain` |
| finish | `checkmark.circle` |

---

## 四、实现要点

### 4.1 布局

- `VStack`：上 Neural Canvas（约 40% 高度），下 Terminal Content（可滚动）
- 或提供 Tab/切换：`[可视化]` | `[终端]`，满足不同偏好

### 4.2 动效

- **中心脉动**：`TimelineView` 或 `withAnimation` 驱动 `scaleEffect` / `opacity`
- **粒子流**：`Canvas` 绘制小圆点，沿 Path 做 `trim` 动画
- **工具高亮**：`scaleEffect(1.2)` + `shadow`，2 秒后恢复

### 4.3 数据流

- `MonitoringViewModel` 已有：`actionLogs`、`recentToolCalls`、`isStreamingLLM`、`displayTool`
- 从 `actionLogs` 提取最近 N 个 `actionType`，去重后映射到工具环上的节点

---

## 五、MVP 功能清单

1. **NeuralCanvas 组件**：中心 AI 节点 + 工具环（6 个固定类型）
2. **状态驱动**：思考时中心脉动；执行时高亮对应工具节点
3. **连线动画**：中心到高亮工具的线段 + 光点流动
4. **保留终端**：下方 Terminal 区域可折叠或默认展示

---

## 六、与 Agent World 的差异

| Agent World | MacAgent Agent Live |
|-------------|---------------------|
| 像素风角色 | 抽象节点 + 图标 |
| 多 Agent 房间 | 单 Agent + 工具环 |
| 子 Agent 链 | 执行链（Think→Tool→Think→…） |
| 3D/2D 场景 | 2D Canvas，SwiftUI |

MacAgent 侧重「单 Agent 执行过程」的神经网隐喻，与 Agent World 的「多 Agent 社交」不同，但**可视化思路一致**：用图形和动效传达状态，而非仅靠文字。
