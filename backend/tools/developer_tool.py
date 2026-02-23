"""
Developer Tool - 开发能力
支持创建和运行 Web 应用、iOS/macOS 应用项目、API 服务等
"""

import os
import asyncio
import json
import shutil
from typing import Optional, Dict, Any, List
from .base import BaseTool, ToolResult, ToolCategory


class DeveloperTool(BaseTool):
    """开发工具，支持创建各类应用项目"""
    
    name = "developer"
    description = "开发工具：创建 Web 应用、iOS 应用、API 服务、执行代码"
    category = ToolCategory.FILE
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    # 项目创建
                    "create_web_app", "create_ios_app", "create_api_server",
                    "create_python_project", "create_react_app", "create_vue_app",
                    # 代码生成
                    "generate_html", "generate_component", "generate_api_endpoint",
                    # 项目管理
                    "install_deps", "run_dev_server", "build", "test",
                    # 代码执行
                    "run_code", "run_jupyter_cell",
                    # Git 操作
                    "git_init", "git_commit", "git_push",
                    # Xcode 操作
                    "xcode_build", "xcode_run", "xcode_create_view"
                ],
                "description": "开发操作类型"
            },
            "project_name": {
                "type": "string",
                "description": "项目名称"
            },
            "project_path": {
                "type": "string",
                "description": "项目路径"
            },
            "template": {
                "type": "string",
                "description": "项目模板"
            },
            "code": {
                "type": "string",
                "description": "代码内容"
            },
            "language": {
                "type": "string",
                "enum": ["python", "javascript", "typescript", "swift", "html", "css"],
                "description": "编程语言"
            },
            "framework": {
                "type": "string",
                "enum": ["react", "vue", "fastapi", "flask", "express", "swiftui"],
                "description": "框架选择"
            },
            "component_name": {
                "type": "string",
                "description": "组件名称"
            },
            "description": {
                "type": "string",
                "description": "功能描述（用于 AI 生成代码）"
            },
            "commit_message": {
                "type": "string",
                "description": "Git 提交信息"
            },
            "port": {
                "type": "number",
                "description": "服务端口"
            }
        },
        "required": ["action"]
    }
    
    def __init__(self, runtime_adapter=None):
        super().__init__(runtime_adapter)
        self._running_servers: Dict[str, asyncio.subprocess.Process] = {}
    
    async def execute(
        self,
        action: str,
        project_name: Optional[str] = None,
        project_path: Optional[str] = None,
        template: Optional[str] = None,
        code: Optional[str] = None,
        language: str = "python",
        framework: Optional[str] = None,
        component_name: Optional[str] = None,
        description: Optional[str] = None,
        commit_message: Optional[str] = None,
        port: int = 3000
    ) -> ToolResult:
        """执行开发操作"""
        
        # 项目创建
        if action == "create_web_app":
            return await self._create_web_app(project_name, project_path, framework)
        elif action == "create_ios_app":
            return await self._create_ios_app(project_name, project_path)
        elif action == "create_api_server":
            return await self._create_api_server(project_name, project_path, framework)
        elif action == "create_python_project":
            return await self._create_python_project(project_name, project_path)
        elif action == "create_react_app":
            return await self._create_react_app(project_name, project_path)
        elif action == "create_vue_app":
            return await self._create_vue_app(project_name, project_path)
        
        # 代码生成
        elif action == "generate_html":
            return await self._generate_html(description, project_path)
        elif action == "generate_component":
            return await self._generate_component(component_name, framework, description, project_path)
        elif action == "generate_api_endpoint":
            return await self._generate_api_endpoint(description, framework, project_path)
        
        # 项目管理
        elif action == "install_deps":
            return await self._install_deps(project_path)
        elif action == "run_dev_server":
            return await self._run_dev_server(project_path, port)
        elif action == "build":
            return await self._build_project(project_path)
        elif action == "test":
            return await self._run_tests(project_path)
        
        # 代码执行
        elif action == "run_code":
            return await self._run_code(code, language)
        
        # Git 操作
        elif action == "git_init":
            return await self._git_init(project_path)
        elif action == "git_commit":
            return await self._git_commit(project_path, commit_message)
        elif action == "git_push":
            return await self._git_push(project_path)
        
        # Xcode 操作
        elif action == "xcode_build":
            return await self._xcode_build(project_path)
        elif action == "xcode_run":
            return await self._xcode_run(project_path)
        elif action == "xcode_create_view":
            return await self._xcode_create_view(component_name, description, project_path)
        
        else:
            return ToolResult(success=False, error=f"未知操作: {action}")
    
    async def _run_cmd(
        self,
        cmd: List[str],
        cwd: Optional[str] = None,
        timeout: int = 300
    ) -> tuple[bool, str, str]:
        """执行命令"""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            
            return (
                process.returncode == 0,
                stdout.decode().strip(),
                stderr.decode().strip()
            )
        except asyncio.TimeoutError:
            return False, "", "命令执行超时"
        except Exception as e:
            return False, "", str(e)
    
    # ============ 项目创建 ============
    
    async def _create_web_app(
        self,
        name: str,
        path: Optional[str],
        framework: Optional[str]
    ) -> ToolResult:
        """创建 Web 应用"""
        if not name:
            return ToolResult(success=False, error="需要项目名称")
        
        project_dir = os.path.join(path or os.getcwd(), name)
        os.makedirs(project_dir, exist_ok=True)
        
        # 创建基础 HTML 文件
        html_content = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{name}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .container {{
            background: white;
            padding: 3rem;
            border-radius: 1rem;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
            max-width: 500px;
        }}
        h1 {{
            color: #333;
            margin-bottom: 1rem;
            font-size: 2rem;
        }}
        p {{
            color: #666;
            line-height: 1.6;
        }}
        .btn {{
            display: inline-block;
            margin-top: 1.5rem;
            padding: 0.8rem 2rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            border-radius: 2rem;
            font-weight: 600;
            transition: transform 0.2s;
        }}
        .btn:hover {{ transform: translateY(-2px); }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 {name}</h1>
        <p>欢迎使用 MacAgent 创建的 Web 应用！</p>
        <a href="#" class="btn">开始使用</a>
    </div>
    <script>
        console.log('{name} 已启动');
    </script>
</body>
</html>
'''
        
        with open(os.path.join(project_dir, "index.html"), "w") as f:
            f.write(html_content)
        
        # 创建简单的 CSS 和 JS 文件
        css_content = '''/* 自定义样式 */
.custom-class {
    /* 添加你的样式 */
}
'''
        js_content = '''// 自定义脚本
document.addEventListener('DOMContentLoaded', () => {
    console.log('页面已加载');
});
'''
        
        with open(os.path.join(project_dir, "styles.css"), "w") as f:
            f.write(css_content)
        
        with open(os.path.join(project_dir, "script.js"), "w") as f:
            f.write(js_content)
        
        return ToolResult(success=True, data={
            "message": f"Web 应用 {name} 创建成功",
            "path": project_dir,
            "files": ["index.html", "styles.css", "script.js"],
            "next_step": f"用浏览器打开 {project_dir}/index.html 或使用 python -m http.server"
        })
    
    async def _create_ios_app(self, name: str, path: Optional[str]) -> ToolResult:
        """创建 iOS/macOS 应用项目"""
        if not name:
            return ToolResult(success=False, error="需要项目名称")
        
        project_dir = os.path.join(path or os.getcwd(), name)
        os.makedirs(project_dir, exist_ok=True)
        
        # 创建 Swift 文件
        app_swift = f'''import SwiftUI

@main
struct {name}App: App {{
    var body: some Scene {{
        WindowGroup {{
            ContentView()
        }}
    }}
}}
'''
        
        content_view = f'''import SwiftUI

struct ContentView: View {{
    @State private var message = "Hello, {name}!"
    
    var body: some View {{
        VStack(spacing: 20) {{
            Image(systemName: "star.fill")
                .font(.system(size: 60))
                .foregroundStyle(.yellow)
            
            Text(message)
                .font(.largeTitle)
                .fontWeight(.bold)
            
            Button("点击我") {{
                message = "🎉 欢迎使用 {name}!"
            }}
            .buttonStyle(.borderedProminent)
        }}
        .padding()
    }}
}}

#Preview {{
    ContentView()
}}
'''
        
        # 创建项目结构
        sources_dir = os.path.join(project_dir, "Sources")
        os.makedirs(sources_dir, exist_ok=True)
        
        with open(os.path.join(sources_dir, f"{name}App.swift"), "w") as f:
            f.write(app_swift)
        
        with open(os.path.join(sources_dir, "ContentView.swift"), "w") as f:
            f.write(content_view)
        
        # 创建 Package.swift
        package_swift = f'''// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "{name}",
    platforms: [
        .macOS(.v14),
        .iOS(.v17)
    ],
    products: [
        .executable(name: "{name}", targets: ["{name}"])
    ],
    targets: [
        .executableTarget(
            name: "{name}",
            path: "Sources"
        )
    ]
)
'''
        
        with open(os.path.join(project_dir, "Package.swift"), "w") as f:
            f.write(package_swift)
        
        return ToolResult(success=True, data={
            "message": f"iOS/macOS 应用 {name} 创建成功",
            "path": project_dir,
            "files": [
                "Package.swift",
                f"Sources/{name}App.swift",
                "Sources/ContentView.swift"
            ],
            "next_step": f"使用 Xcode 打开项目或运行 swift build"
        })
    
    async def _create_api_server(
        self,
        name: str,
        path: Optional[str],
        framework: Optional[str]
    ) -> ToolResult:
        """创建 API 服务"""
        if not name:
            return ToolResult(success=False, error="需要项目名称")
        
        framework = framework or "fastapi"
        project_dir = os.path.join(path or os.getcwd(), name)
        os.makedirs(project_dir, exist_ok=True)
        
        if framework == "fastapi":
            main_py = '''from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI(
    title="API Server",
    description="由 MacAgent 创建的 API 服务",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 数据模型
class Item(BaseModel):
    id: Optional[int] = None
    name: str
    description: Optional[str] = None
    price: float

# 内存数据库
items_db: List[Item] = []

@app.get("/")
async def root():
    return {"message": "API 服务运行中", "docs": "/docs"}

@app.get("/items")
async def list_items():
    return {"items": items_db}

@app.post("/items")
async def create_item(item: Item):
    item.id = len(items_db) + 1
    items_db.append(item)
    return {"message": "创建成功", "item": item}

@app.get("/items/{item_id}")
async def get_item(item_id: int):
    for item in items_db:
        if item.id == item_id:
            return item
    return {"error": "Item not found"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
'''
            
            requirements = '''fastapi>=0.100.0
uvicorn>=0.22.0
pydantic>=2.0.0
'''
        
        elif framework == "flask":
            main_py = '''from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

items_db = []

@app.route('/')
def root():
    return jsonify({"message": "API 服务运行中"})

@app.route('/items', methods=['GET'])
def list_items():
    return jsonify({"items": items_db})

@app.route('/items', methods=['POST'])
def create_item():
    item = request.json
    item['id'] = len(items_db) + 1
    items_db.append(item)
    return jsonify({"message": "创建成功", "item": item})

@app.route('/items/<int:item_id>')
def get_item(item_id):
    for item in items_db:
        if item['id'] == item_id:
            return jsonify(item)
    return jsonify({"error": "Item not found"}), 404

if __name__ == "__main__":
    app.run(debug=True, port=8000)
'''
            
            requirements = '''flask>=2.0.0
flask-cors>=3.0.0
'''
        
        else:
            return ToolResult(success=False, error=f"不支持的框架: {framework}")
        
        with open(os.path.join(project_dir, "main.py"), "w") as f:
            f.write(main_py)
        
        with open(os.path.join(project_dir, "requirements.txt"), "w") as f:
            f.write(requirements)
        
        return ToolResult(success=True, data={
            "message": f"API 服务 {name} 创建成功 (使用 {framework})",
            "path": project_dir,
            "files": ["main.py", "requirements.txt"],
            "next_step": "pip install -r requirements.txt && python main.py"
        })
    
    async def _create_python_project(
        self,
        name: str,
        path: Optional[str]
    ) -> ToolResult:
        """创建 Python 项目"""
        if not name:
            return ToolResult(success=False, error="需要项目名称")
        
        project_dir = os.path.join(path or os.getcwd(), name)
        os.makedirs(project_dir, exist_ok=True)
        os.makedirs(os.path.join(project_dir, name), exist_ok=True)
        os.makedirs(os.path.join(project_dir, "tests"), exist_ok=True)
        
        # __init__.py
        with open(os.path.join(project_dir, name, "__init__.py"), "w") as f:
            f.write(f'"""{ name } package"""\n\n__version__ = "0.1.0"\n')
        
        # main.py
        main_py = f'''"""{ name } main module"""


def main():
    """Main entry point"""
    print("Hello from {name}!")


if __name__ == "__main__":
    main()
'''
        with open(os.path.join(project_dir, name, "main.py"), "w") as f:
            f.write(main_py)
        
        # pyproject.toml
        pyproject = f'''[project]
name = "{name}"
version = "0.1.0"
description = "A Python project created by MacAgent"
requires-python = ">=3.10"
dependencies = []

[project.scripts]
{name} = "{name}.main:main"

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"
'''
        with open(os.path.join(project_dir, "pyproject.toml"), "w") as f:
            f.write(pyproject)
        
        # README.md
        readme = f'''# {name}

由 MacAgent 创建的 Python 项目。

## 安装

```bash
pip install -e .
```

## 使用

```bash
{name}
```

或者

```python
from {name} import main
main.main()
```
'''
        with open(os.path.join(project_dir, "README.md"), "w") as f:
            f.write(readme)
        
        return ToolResult(success=True, data={
            "message": f"Python 项目 {name} 创建成功",
            "path": project_dir,
            "structure": [
                f"{name}/",
                f"  {name}/__init__.py",
                f"  {name}/main.py",
                "  tests/",
                "  pyproject.toml",
                "  README.md"
            ]
        })
    
    async def _create_react_app(
        self,
        name: str,
        path: Optional[str]
    ) -> ToolResult:
        """创建 React 应用"""
        if not name:
            return ToolResult(success=False, error="需要项目名称")
        
        project_dir = path or os.getcwd()
        
        # 使用 create-vite 创建 React 项目
        success, stdout, stderr = await self._run_cmd(
            ["npm", "create", "vite@latest", name, "--", "--template", "react-ts"],
            cwd=project_dir,
            timeout=120
        )
        
        if success:
            return ToolResult(success=True, data={
                "message": f"React 应用 {name} 创建成功",
                "path": os.path.join(project_dir, name),
                "next_step": f"cd {name} && npm install && npm run dev"
            })
        
        # 如果 npm 创建失败，手动创建基础结构
        return await self._create_react_manual(name, project_dir)
    
    async def _create_react_manual(self, name: str, path: str) -> ToolResult:
        """手动创建 React 项目结构"""
        project_dir = os.path.join(path, name)
        os.makedirs(os.path.join(project_dir, "src"), exist_ok=True)
        
        # index.html
        index_html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{name}</title>
</head>
<body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
</body>
</html>
'''
        
        # main.tsx
        main_tsx = '''import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
'''
        
        # App.tsx
        app_tsx = f'''import {{ useState }} from 'react'
import './App.css'

function App() {{
  const [count, setCount] = useState(0)

  return (
    <div className="app">
      <h1>🚀 {name}</h1>
      <div className="card">
        <button onClick={{() => setCount(count + 1)}}>
          点击次数: {{count}}
        </button>
      </div>
      <p>由 MacAgent 创建</p>
    </div>
  )
}}

export default App
'''
        
        # CSS
        app_css = '''.app {
  text-align: center;
  padding: 2rem;
}

.card {
  padding: 2rem;
}

button {
  font-size: 1rem;
  padding: 0.6rem 1.2rem;
  border-radius: 8px;
  border: 1px solid #646cff;
  background: #646cff;
  color: white;
  cursor: pointer;
}

button:hover {
  background: #535bf2;
}
'''
        
        # package.json
        package_json = f'''{{
  "name": "{name}",
  "private": true,
  "version": "0.0.1",
  "type": "module",
  "scripts": {{
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  }},
  "dependencies": {{
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  }},
  "devDependencies": {{
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "@vitejs/plugin-react": "^4.0.0",
    "typescript": "^5.0.0",
    "vite": "^5.0.0"
  }}
}}
'''
        
        # Write files
        with open(os.path.join(project_dir, "index.html"), "w") as f:
            f.write(index_html)
        with open(os.path.join(project_dir, "src", "main.tsx"), "w") as f:
            f.write(main_tsx)
        with open(os.path.join(project_dir, "src", "App.tsx"), "w") as f:
            f.write(app_tsx)
        with open(os.path.join(project_dir, "src", "App.css"), "w") as f:
            f.write(app_css)
        with open(os.path.join(project_dir, "src", "index.css"), "w") as f:
            f.write("/* Global styles */")
        with open(os.path.join(project_dir, "package.json"), "w") as f:
            f.write(package_json)
        
        return ToolResult(success=True, data={
            "message": f"React 应用 {name} 创建成功（手动模式）",
            "path": project_dir,
            "next_step": f"cd {name} && npm install && npm run dev"
        })
    
    async def _create_vue_app(
        self,
        name: str,
        path: Optional[str]
    ) -> ToolResult:
        """创建 Vue 应用"""
        if not name:
            return ToolResult(success=False, error="需要项目名称")
        
        project_dir = path or os.getcwd()
        
        success, stdout, stderr = await self._run_cmd(
            ["npm", "create", "vite@latest", name, "--", "--template", "vue-ts"],
            cwd=project_dir,
            timeout=120
        )
        
        if success:
            return ToolResult(success=True, data={
                "message": f"Vue 应用 {name} 创建成功",
                "path": os.path.join(project_dir, name),
                "next_step": f"cd {name} && npm install && npm run dev"
            })
        
        return ToolResult(success=False, error=f"Vue 创建失败: {stderr}")
    
    # ============ 代码执行 ============
    
    async def _run_code(self, code: str, language: str) -> ToolResult:
        """执行代码"""
        if not code:
            return ToolResult(success=False, error="需要代码内容")
        
        import tempfile
        
        ext_map = {
            "python": ".py",
            "javascript": ".js",
            "typescript": ".ts",
            "swift": ".swift"
        }
        
        cmd_map = {
            "python": ["python3"],
            "javascript": ["node"],
            "typescript": ["npx", "ts-node"],
            "swift": ["swift"]
        }
        
        if language not in ext_map:
            return ToolResult(success=False, error=f"不支持的语言: {language}")
        
        ext = ext_map[language]
        cmd = cmd_map[language]
        
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=ext,
            delete=False
        ) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            success, stdout, stderr = await self._run_cmd(
                cmd + [temp_file],
                timeout=60
            )
            
            return ToolResult(success=True, data={
                "stdout": stdout,
                "stderr": stderr,
                "success": success
            })
        finally:
            os.unlink(temp_file)
    
    # ============ 项目管理 ============
    
    async def _install_deps(self, project_path: str) -> ToolResult:
        """安装依赖"""
        if not project_path or not os.path.exists(project_path):
            return ToolResult(success=False, error="项目路径无效")
        
        # 检测项目类型
        if os.path.exists(os.path.join(project_path, "package.json")):
            success, stdout, stderr = await self._run_cmd(
                ["npm", "install"],
                cwd=project_path,
                timeout=300
            )
        elif os.path.exists(os.path.join(project_path, "requirements.txt")):
            success, stdout, stderr = await self._run_cmd(
                ["pip", "install", "-r", "requirements.txt"],
                cwd=project_path,
                timeout=300
            )
        elif os.path.exists(os.path.join(project_path, "pyproject.toml")):
            success, stdout, stderr = await self._run_cmd(
                ["pip", "install", "-e", "."],
                cwd=project_path,
                timeout=300
            )
        else:
            return ToolResult(success=False, error="无法检测项目类型")
        
        if success:
            return ToolResult(success=True, data={"message": "依赖安装成功"})
        return ToolResult(success=False, error=stderr)
    
    async def _run_dev_server(self, project_path: str, port: int) -> ToolResult:
        """启动开发服务器"""
        if not project_path or not os.path.exists(project_path):
            return ToolResult(success=False, error="项目路径无效")
        
        # 检测项目类型并选择启动命令
        if os.path.exists(os.path.join(project_path, "package.json")):
            cmd = ["npm", "run", "dev"]
        elif os.path.exists(os.path.join(project_path, "main.py")):
            cmd = ["python", "main.py"]
        else:
            # 默认启动 Python HTTP 服务器
            cmd = ["python", "-m", "http.server", str(port)]
        
        # 后台启动
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=project_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        self._running_servers[project_path] = process
        
        return ToolResult(success=True, data={
            "message": f"开发服务器已启动",
            "pid": process.pid,
            "port": port,
            "url": f"http://localhost:{port}"
        })
    
    async def _build_project(self, project_path: str) -> ToolResult:
        """构建项目"""
        if not project_path or not os.path.exists(project_path):
            return ToolResult(success=False, error="项目路径无效")
        
        if os.path.exists(os.path.join(project_path, "package.json")):
            success, stdout, stderr = await self._run_cmd(
                ["npm", "run", "build"],
                cwd=project_path,
                timeout=300
            )
        else:
            return ToolResult(success=False, error="不支持的项目类型")
        
        if success:
            return ToolResult(success=True, data={"message": "构建成功", "output": stdout})
        return ToolResult(success=False, error=stderr)
    
    async def _run_tests(self, project_path: str) -> ToolResult:
        """运行测试"""
        if not project_path or not os.path.exists(project_path):
            return ToolResult(success=False, error="项目路径无效")
        
        if os.path.exists(os.path.join(project_path, "package.json")):
            cmd = ["npm", "test"]
        elif os.path.exists(os.path.join(project_path, "pyproject.toml")):
            cmd = ["pytest"]
        else:
            cmd = ["python", "-m", "pytest"]
        
        success, stdout, stderr = await self._run_cmd(cmd, cwd=project_path, timeout=300)
        
        return ToolResult(success=True, data={
            "test_output": stdout,
            "errors": stderr,
            "passed": success
        })
    
    # ============ Git 操作 ============
    
    async def _git_init(self, project_path: str) -> ToolResult:
        """初始化 Git 仓库"""
        if not project_path:
            return ToolResult(success=False, error="需要项目路径")
        
        success, stdout, stderr = await self._run_cmd(
            ["git", "init"],
            cwd=project_path
        )
        
        if success:
            # 创建 .gitignore
            gitignore = '''node_modules/
__pycache__/
*.pyc
.env
.venv/
dist/
build/
.DS_Store
'''
            with open(os.path.join(project_path, ".gitignore"), "w") as f:
                f.write(gitignore)
            
            return ToolResult(success=True, data={"message": "Git 仓库初始化成功"})
        return ToolResult(success=False, error=stderr)
    
    async def _git_commit(self, project_path: str, message: str) -> ToolResult:
        """Git 提交"""
        if not project_path or not message:
            return ToolResult(success=False, error="需要项目路径和提交信息")
        
        # 添加所有文件
        await self._run_cmd(["git", "add", "."], cwd=project_path)
        
        # 提交
        success, stdout, stderr = await self._run_cmd(
            ["git", "commit", "-m", message],
            cwd=project_path
        )
        
        if success:
            return ToolResult(success=True, data={"message": "提交成功"})
        return ToolResult(success=False, error=stderr)
    
    async def _git_push(self, project_path: str) -> ToolResult:
        """Git 推送"""
        if not project_path:
            return ToolResult(success=False, error="需要项目路径")
        
        success, stdout, stderr = await self._run_cmd(
            ["git", "push"],
            cwd=project_path
        )
        
        if success:
            return ToolResult(success=True, data={"message": "推送成功"})
        return ToolResult(success=False, error=stderr)
    
    # ============ Xcode 操作 ============
    
    async def _xcode_build(self, project_path: str) -> ToolResult:
        """Xcode 构建"""
        if not project_path:
            return ToolResult(success=False, error="需要项目路径")
        
        # 查找 xcodeproj 或 xcworkspace
        for f in os.listdir(project_path):
            if f.endswith(".xcworkspace"):
                workspace = f
                success, stdout, stderr = await self._run_cmd(
                    ["xcodebuild", "-workspace", workspace, "-scheme", f.replace(".xcworkspace", "")],
                    cwd=project_path,
                    timeout=600
                )
                break
            elif f.endswith(".xcodeproj"):
                project = f
                success, stdout, stderr = await self._run_cmd(
                    ["xcodebuild", "-project", project],
                    cwd=project_path,
                    timeout=600
                )
                break
        else:
            # Swift Package
            success, stdout, stderr = await self._run_cmd(
                ["swift", "build"],
                cwd=project_path,
                timeout=300
            )
        
        if success:
            return ToolResult(success=True, data={"message": "构建成功", "output": stdout[-2000:]})
        return ToolResult(success=False, error=stderr[-1000:])
    
    async def _xcode_run(self, project_path: str) -> ToolResult:
        """运行 Xcode 项目"""
        if not project_path:
            return ToolResult(success=False, error="需要项目路径")
        
        # 使用 AppleScript 打开 Xcode 并运行（通过 runtime adapter）
        if not self.runtime_adapter:
            return ToolResult(success=False, error="当前平台不支持 AppleScript")
        script = f'''
        tell application "Xcode"
            activate
            open "{project_path}"
            delay 2
        end tell
        tell application "System Events"
            tell process "Xcode"
                keystroke "r" using command down
            end tell
        end tell
        '''
        r = await self.runtime_adapter.run_script(script, lang="applescript")
        if not r.success:
            return ToolResult(success=False, error=r.error)
        return ToolResult(success=True, data={"message": "Xcode 项目运行中"})
    
    async def _xcode_create_view(
        self,
        name: str,
        description: Optional[str],
        project_path: str
    ) -> ToolResult:
        """创建 SwiftUI View"""
        if not name or not project_path:
            return ToolResult(success=False, error="需要视图名称和项目路径")
        
        view_code = f'''import SwiftUI

/// {description or name + " View"}
struct {name}: View {{
    var body: some View {{
        VStack {{
            Text("{name}")
                .font(.title)
        }}
        .padding()
    }}
}}

#Preview {{
    {name}()
}}
'''
        
        # 查找 Sources 目录
        sources_dir = os.path.join(project_path, "Sources")
        if not os.path.exists(sources_dir):
            sources_dir = project_path
        
        file_path = os.path.join(sources_dir, f"{name}.swift")
        with open(file_path, "w") as f:
            f.write(view_code)
        
        return ToolResult(success=True, data={
            "message": f"SwiftUI 视图 {name} 创建成功",
            "path": file_path
        })
    
    # ============ 代码生成 ============
    
    async def _generate_html(
        self,
        description: str,
        project_path: Optional[str]
    ) -> ToolResult:
        """根据描述生成 HTML"""
        if not description:
            return ToolResult(success=False, error="需要功能描述")
        
        # 简单的模板生成
        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{description}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
        }}
    </style>
</head>
<body>
    <h1>{description}</h1>
    <p>由 MacAgent 生成</p>
</body>
</html>
'''
        
        if project_path:
            file_path = os.path.join(project_path, "generated.html")
            with open(file_path, "w") as f:
                f.write(html)
            return ToolResult(success=True, data={"path": file_path, "html": html})
        
        return ToolResult(success=True, data={"html": html})
    
    async def _generate_component(
        self,
        name: str,
        framework: Optional[str],
        description: Optional[str],
        project_path: Optional[str]
    ) -> ToolResult:
        """生成前端组件"""
        if not name:
            return ToolResult(success=False, error="需要组件名称")
        
        framework = framework or "react"
        
        if framework == "react":
            code = f'''import React from 'react';

interface {name}Props {{
  title?: string;
}}

export const {name}: React.FC<{name}Props> = ({{ title = "{name}" }}) => {{
  return (
    <div className="{name.lower()}">
      <h2>{{title}}</h2>
      {{/* {description or "组件内容"} */}}
    </div>
  );
}};

export default {name};
'''
            ext = ".tsx"
        
        elif framework == "vue":
            code = f'''<template>
  <div class="{name.lower()}">
    <h2>{{ title }}</h2>
    <!-- {description or "组件内容"} -->
  </div>
</template>

<script setup lang="ts">
defineProps<{{
  title?: string;
}}>()
</script>

<style scoped>
.{name.lower()} {{
  padding: 1rem;
}}
</style>
'''
            ext = ".vue"
        
        elif framework == "swiftui":
            code = f'''import SwiftUI

struct {name}: View {{
    var title: String = "{name}"
    
    var body: some View {{
        VStack {{
            Text(title)
                .font(.headline)
            // {description or "视图内容"}
        }}
        .padding()
    }}
}}

#Preview {{
    {name}()
}}
'''
            ext = ".swift"
        
        else:
            return ToolResult(success=False, error=f"不支持的框架: {framework}")
        
        if project_path:
            file_path = os.path.join(project_path, f"{name}{ext}")
            with open(file_path, "w") as f:
                f.write(code)
            return ToolResult(success=True, data={
                "path": file_path,
                "component": name,
                "framework": framework
            })
        
        return ToolResult(success=True, data={"code": code, "component": name})
    
    async def _generate_api_endpoint(
        self,
        description: str,
        framework: Optional[str],
        project_path: Optional[str]
    ) -> ToolResult:
        """生成 API 端点"""
        if not description:
            return ToolResult(success=False, error="需要端点描述")
        
        framework = framework or "fastapi"
        
        if framework == "fastapi":
            code = f'''from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter()

# {description}

class ItemRequest(BaseModel):
    name: str
    value: Optional[str] = None

class ItemResponse(BaseModel):
    id: int
    name: str
    value: Optional[str]

@router.get("/items", response_model=List[ItemResponse])
async def list_items():
    """获取列表"""
    return []

@router.post("/items", response_model=ItemResponse)
async def create_item(request: ItemRequest):
    """创建项目"""
    return ItemResponse(id=1, **request.dict())

@router.get("/items/{{item_id}}", response_model=ItemResponse)
async def get_item(item_id: int):
    """获取单个项目"""
    raise HTTPException(status_code=404, detail="Not found")
'''
        
        elif framework == "express":
            code = f'''// {description}

const express = require('express');
const router = express.Router();

// GET /items
router.get('/items', (req, res) => {{
  res.json([]);
}});

// POST /items
router.post('/items', (req, res) => {{
  const item = {{ id: 1, ...req.body }};
  res.status(201).json(item);
}});

// GET /items/:id
router.get('/items/:id', (req, res) => {{
  res.status(404).json({{ error: 'Not found' }});
}});

module.exports = router;
'''
        
        else:
            return ToolResult(success=False, error=f"不支持的框架: {framework}")
        
        if project_path:
            filename = "routes.py" if framework == "fastapi" else "routes.js"
            file_path = os.path.join(project_path, filename)
            with open(file_path, "w") as f:
                f.write(code)
            return ToolResult(success=True, data={"path": file_path})
        
        return ToolResult(success=True, data={"code": code})
