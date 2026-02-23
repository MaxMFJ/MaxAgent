# MacAgent iOS 客户端

Objective-C 编写的 iOS 聊天客户端，用于远程连接 Mac 上的 MacAgent 后端服务。

## 功能特性

- WebSocket 实时通信
- 流式消息显示
- 工具调用状态展示
- 扫码连接配置
- Token 认证支持
- 自动重连机制

## 系统要求

- iOS 15.0+
- Xcode 15.0+

## 项目结构

```
iOSAgentApp/
├── AppDelegate.h/m          # 应用代理
├── SceneDelegate.h/m        # 场景代理
├── main.m                   # 入口
├── Services/
│   └── WebSocketService.h/m # WebSocket 通信服务
├── Models/
│   ├── Message.h/m          # 消息模型
│   └── ServerConfig.h/m     # 服务器配置
├── ViewControllers/
│   ├── ChatViewController.h/m    # 聊天主界面
│   └── SettingsViewController.h/m # 设置界面
├── Views/
│   ├── MessageCell.h/m      # 消息单元格
│   └── InputView.h/m        # 输入栏
└── Resources/
    ├── Assets.xcassets      # 资源文件
    └── LaunchScreen.storyboard
```

## 使用方法

### 1. 在 Mac 上启动后端和 Tunnel

1. 启动 MacAgent 后端服务
2. 打开 MacAgent 设置 -> 远程
3. 点击「启动 Tunnel」
4. 等待生成公网地址和二维码

### 2. 在 iOS 上连接

1. 打开 iOSAgentApp
2. 点击设置图标
3. 扫描 Mac 上显示的二维码，或手动输入地址
4. 点击「Connect」
5. 开始聊天！

## 通信协议

### WebSocket 连接

```
wss://xxx.trycloudflare.com/ws?client_type=ios&token=xxx
```

### 消息格式

发送聊天消息：
```json
{
  "type": "chat",
  "content": "你好",
  "session_id": "xxx"
}
```

接收内容流：
```json
{
  "type": "content",
  "content": "你好！"
}
```

工具调用：
```json
{
  "type": "tool_call",
  "name": "screenshot",
  "call_id": "xxx",
  "arguments": "{}"
}
```

## 开发说明

项目使用 Objective-C 编写，采用 UIKit 框架。

### WebSocket 实现

使用 `NSURLSessionWebSocketTask` (iOS 13+) 原生 WebSocket 支持：

- 自动心跳保活 (10秒间隔)
- 断线自动重连 (指数退避)
- JSON 消息序列化

### 界面实现

- `ChatViewController`: UITableView + 自定义 cell
- `InputView`: 自适应高度的输入框
- `MessageCell`: 气泡样式消息

## License

MIT
