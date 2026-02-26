#!/bin/bash

# iOS Agent App 编译验证脚本

echo "================================"
echo "iOS Agent App 编译验证"
echo "================================"
echo ""

cd /Users/lzz/Desktop/未命名文件夹/MacAgent/iOSAgentApp

echo "1. 检查文件是否存在..."
echo ""

files=(
    "iOSAgentApp/Models/Conversation.h"
    "iOSAgentApp/Models/Conversation.m"
    "iOSAgentApp/Models/ConversationManager.h"
    "iOSAgentApp/Models/ConversationManager.m"
    "iOSAgentApp/ViewControllers/ConversationListViewController.h"
    "iOSAgentApp/ViewControllers/ConversationListViewController.m"
)

all_exist=true
for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file"
    else
        echo "❌ $file (缺失)"
        all_exist=false
    fi
done

echo ""

if [ "$all_exist" = false ]; then
    echo "❌ 部分文件缺失，无法继续"
    exit 1
fi

echo "2. 检查修改的文件..."
echo ""

modified_files=(
    "iOSAgentApp/Models/Message.h"
    "iOSAgentApp/Models/Message.m"
    "iOSAgentApp/Services/WebSocketService.h"
    "iOSAgentApp/Services/WebSocketService.m"
    "iOSAgentApp/ViewControllers/ChatViewController.m"
)

for file in "${modified_files[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file"
    else
        echo "❌ $file (缺失)"
    fi
done

echo ""
echo "3. 检查 Xcode 项目配置..."
echo ""

if grep -q "Conversation.m" iOSAgentApp.xcodeproj/project.pbxproj; then
    echo "✅ Conversation.m 已添加到项目"
else
    echo "❌ Conversation.m 未添加到项目"
fi

if grep -q "ConversationManager.m" iOSAgentApp.xcodeproj/project.pbxproj; then
    echo "✅ ConversationManager.m 已添加到项目"
else
    echo "❌ ConversationManager.m 未添加到项目"
fi

if grep -q "ConversationListViewController.m" iOSAgentApp.xcodeproj/project.pbxproj; then
    echo "✅ ConversationListViewController.m 已添加到项目"
else
    echo "❌ ConversationListViewController.m 未添加到项目"
fi

echo ""
echo "4. 尝试编译项目（需要 Xcode 命令行工具）..."
echo ""

if command -v xcodebuild &> /dev/null; then
    echo "正在清理构建缓存..."
    xcodebuild clean -workspace iOSAgentApp.xcworkspace -scheme iOSAgentApp 2>&1 | tail -5
    
    echo ""
    echo "正在编译项目（仅验证语法，不生成完整 app）..."
    xcodebuild build -workspace iOSAgentApp.xcworkspace -scheme iOSAgentApp -sdk iphonesimulator -configuration Debug CODE_SIGNING_ALLOWED=NO 2>&1 | grep -E "(error:|warning:|BUILD)" | tail -20
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ 编译成功！"
    else
        echo ""
        echo "⚠️  编译可能有问题，请在 Xcode 中打开项目查看详细错误"
    fi
else
    echo "⚠️  未找到 xcodebuild 命令"
    echo "请在 Xcode 中手动打开项目进行编译验证"
fi

echo ""
echo "================================"
echo "验证完成"
echo "================================"
echo ""
echo "下一步："
echo "1. 在 Xcode 中打开 iOSAgentApp.xcworkspace"
echo "2. 确认所有文件都在项目导航器中"
echo "3. 选择模拟器或真机设备"
echo "4. 按 Cmd+B 编译"
echo "5. 按 Cmd+R 运行并测试"
echo ""
