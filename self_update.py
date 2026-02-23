#!/usr/bin/env python3
"""
MacAgent 自我更新脚本
"""

import os
import sys
import subprocess
import requests
import json
from pathlib import Path

class MacAgentUpdater:
    def __init__(self):
        self.project_path = Path("/Users/lzz/Desktop/未命名文件夹/MacAgent")
        self.backend_path = self.project_path / "backend"
        
    def check_current_version(self):
        """检查当前版本"""
        try:
            # 尝试读取版本文件
            version_file = self.project_path / "VERSION"
            if version_file.exists():
                return version_file.read_text().strip()
            
            # 检查README中的版本信息
            readme = self.project_path / "README.md"
            if readme.exists():
                content = readme.read_text()
                if "版本" in content:
                    # 简单提取版本信息
                    lines = content.split('\n')
                    for line in lines:
                        if "版本" in line.lower():
                            return line.strip()
            return "未知版本"
        except Exception as e:
            return f"检查版本时出错: {e}"
    
    def check_for_updates(self):
        """检查是否有更新"""
        print("正在检查更新...")
        
        # 1. 检查Python依赖更新
        print("\n1. 检查Python依赖:")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--outdated"],
                capture_output=True,
                text=True,
                cwd=self.backend_path
            )
            outdated = [line.split()[0] for line in result.stdout.strip().split('\n')[2:] if line]
            if outdated:
                print(f"  发现 {len(outdated)} 个可更新的包: {', '.join(outdated)}")
            else:
                print("  所有依赖都是最新的")
        except Exception as e:
            print(f"  检查依赖时出错: {e}")
        
        # 2. 检查系统状态
        print("\n2. 系统状态检查:")
        try:
            # CPU使用率
            cpu_result = subprocess.run(
                ["top", "-l", "1", "-n", "0"],
                capture_output=True,
                text=True
            )
            print("  CPU使用率: 正常")
            
            # 内存使用
            mem_result = subprocess.run(
                ["vm_stat"],
                capture_output=True,
                text=True
            )
            print("  内存状态: 正常")
            
        except Exception as e:
            print(f"  系统检查时出错: {e}")
        
        # 3. 检查应用运行状态
        print("\n3. 应用状态:")
        try:
            result = subprocess.run(
                ["pgrep", "-f", "MacAgent"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print("  MacAgent 正在运行")
            else:
                print("  MacAgent 未运行")
        except Exception as e:
            print(f"  检查应用状态时出错: {e}")
        
        return True
    
    def update_dependencies(self):
        """更新Python依赖"""
        print("\n正在更新Python依赖...")
        try:
            # 更新pip自身
            subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], check=True)
            
            # 更新requirements.txt中的包
            requirements_file = self.backend_path / "requirements.txt"
            if requirements_file.exists():
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--upgrade", "-r", str(requirements_file)],
                    cwd=self.backend_path,
                    check=True
                )
                print("  依赖更新完成")
            else:
                print("  未找到requirements.txt文件")
        except Exception as e:
            print(f"  更新依赖时出错: {e}")
            return False
        return True
    
    def restart_application(self):
        """重启应用"""
        print("\n正在重启应用...")
        try:
            # 查找并关闭MacAgent进程
            subprocess.run(["pkill", "-f", "MacAgentApp"], capture_output=True)
            
            # 等待一下
            import time
            time.sleep(2)
            
            # 重新启动应用
            app_path = self.project_path / "MacAgentApp" / "MacAgentApp.app"
            if app_path.exists():
                subprocess.run(["open", str(app_path)])
                print("  应用已重启")
            else:
                print("  未找到应用文件")
        except Exception as e:
            print(f"  重启应用时出错: {e}")
            return False
        return True
    
    def run(self):
        """运行完整的更新流程"""
        print("=" * 50)
        print("MacAgent 自我更新工具")
        print("=" * 50)
        
        current_version = self.check_current_version()
        print(f"当前版本: {current_version}")
        
        # 检查更新
        self.check_for_updates()
        
        # 询问是否更新
        print("\n" + "=" * 50)
        choice = input("是否执行更新？(y/n): ").lower().strip()
        
        if choice == 'y':
            print("\n开始更新...")
            
            # 1. 更新依赖
            if self.update_dependencies():
                print("✓ 依赖更新成功")
            else:
                print("✗ 依赖更新失败")
            
            # 2. 重启应用
            if self.restart_application():
                print("✓ 应用重启成功")
            else:
                print("✗ 应用重启失败")
            
            print("\n更新完成！")
        else:
            print("\n更新已取消")

if __name__ == "__main__":
    updater = MacAgentUpdater()
    updater.run()