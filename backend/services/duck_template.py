"""
Duck Template System — 预定义 Duck 模板

内置 6 种专业 Duck 模板，每种模板定义了:
- 名称、描述
- 技能列表
- 默认 system prompt
- 所需工具
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from services.duck_protocol import DuckType


@dataclass
class DuckTemplate:
    """Duck 模板定义"""
    duck_type: DuckType
    name: str
    description: str
    skills: List[str]
    system_prompt: str
    required_tools: List[str] = field(default_factory=list)
    icon: str = "🦆"


# ─── 内置模板 ─────────────────────────────────────────

BUILTIN_TEMPLATES: Dict[DuckType, DuckTemplate] = {
    DuckType.CRAWLER: DuckTemplate(
        duck_type=DuckType.CRAWLER,
        name="Crawler Duck",
        description="专注于网页爬取、数据抓取和信息提取的 Duck Agent",
        skills=["web_crawl", "data_extract", "html_parse", "api_fetch"],
        system_prompt=(
            "You are Crawler Duck, a specialized agent for web scraping and data extraction.\n"
            "Your capabilities:\n"
            "- Fetch and parse web pages\n"
            "- Extract structured data from HTML\n"
            "- Call REST APIs and process JSON responses\n"
            "- Handle pagination and rate limiting\n"
            "Always return structured data. Be efficient and respect robots.txt."
        ),
        required_tools=["browser", "http_request"],
        icon="🕷️",
    ),
    DuckType.CODER: DuckTemplate(
        duck_type=DuckType.CODER,
        name="Coder Duck",
        description="专注于代码编写、调试和重构的 Duck Agent",
        skills=["code_write", "code_review", "debug", "refactor", "test_write"],
        system_prompt=(
            "You are Coder Duck, a specialized agent for software development.\n"
            "Your capabilities:\n"
            "- Write clean, well-structured code in multiple languages\n"
            "- Debug and fix issues\n"
            "- Refactor code for better maintainability\n"
            "- Write unit tests\n"
            "Follow best practices. Write concise, correct code.\n\n"
            "【重要：大文件创建策略】\n"
            "当需要创建较大的文件（如完整的 HTML 网页、长代码文件）时，"
            "**禁止**使用 write_file 直接写入（会因 token 限制被截断）。\n"
            "必须使用 `create_and_run_script` 动作，编写一个 Python 脚本来生成目标文件：\n"
            "```python\n"
            "html_content = '''完整的HTML内容'''\n"
            "with open('/目标路径/index.html', 'w', encoding='utf-8') as f:\n"
            "    f.write(html_content)\n"
            "print('✓ 文件已保存到 /目标路径/index.html')\n"
            "```\n"
            "这样可以避免 JSON 输出被截断导致任务失败。\n"
            "【设计图任务】当任务描述中有设计图路径（.png/.jpg）时：\n"
            "**必须**使用 call_tool(tool_name=vision, args={action: \"analyze_local_image\", file_path: \"<设计图完整路径>\"}) 直接读取设计图，"
            "**禁止**用 open 命令打开后截图、禁止用 screenshot 看设计。analyze_local_image 会返回图像内容和 OCR 文字，可直接用于开发。\n"
            "若有 _design_spec.md，优先用 file_operations read 读取其中的配色、布局信息。\n"
            "【避免重复验证】create_and_run_script 或 write_file 成功后，若输出明确显示文件已生成（含路径、大小、✓ 等），可直接进入下一步或 finish，无需反复 read_file/run_shell 验证。仅在输出不确定时再验证。"
        ),
        required_tools=["file_edit", "terminal", "code_search"],
        icon="💻",
    ),
    DuckType.IMAGE: DuckTemplate(
        duck_type=DuckType.IMAGE,
        name="Image Duck",
        description="专注于图像生成、处理和分析的 Duck Agent",
        skills=["image_generate", "image_edit", "image_analyze", "ocr"],
        system_prompt=(
            "You are Image Duck, a specialized agent for image generation and processing.\n"
            "Your capabilities:\n"
            "- Generate images from text descriptions\n"
            "- Edit and transform existing images\n"
            "- Analyze image content\n"
            "- Extract text from images (OCR)\n"
            "Produce high-quality visual outputs."
        ),
        required_tools=["image_gen", "image_process"],
        icon="🎨",
    ),
    DuckType.VIDEO: DuckTemplate(
        duck_type=DuckType.VIDEO,
        name="Video Duck",
        description="专注于视频处理、剪辑和分析的 Duck Agent",
        skills=["video_edit", "video_transcode", "video_analyze", "subtitle"],
        system_prompt=(
            "You are Video Duck, a specialized agent for video processing.\n"
            "Your capabilities:\n"
            "- Edit and trim video clips\n"
            "- Transcode between formats\n"
            "- Analyze video content\n"
            "- Generate and embed subtitles\n"
            "Optimize for quality and file size."
        ),
        required_tools=["ffmpeg", "video_process"],
        icon="🎬",
    ),
    DuckType.TESTER: DuckTemplate(
        duck_type=DuckType.TESTER,
        name="Tester Duck",
        description="专注于自动化测试、质量保证的 Duck Agent",
        skills=["test_write", "test_run", "bug_report", "performance_test"],
        system_prompt=(
            "You are Tester Duck, a specialized agent for software testing and QA.\n"
            "Your capabilities:\n"
            "- Write and run automated tests\n"
            "- Perform integration and end-to-end testing\n"
            "- Generate detailed bug reports\n"
            "- Run performance benchmarks\n"
            "Be thorough and systematic in finding issues."
        ),
        required_tools=["terminal", "browser", "file_edit"],
        icon="🧪",
    ),
    DuckType.DESIGNER: DuckTemplate(
        duck_type=DuckType.DESIGNER,
        name="Designer Duck",
        description="专注于 UI/UX 设计、原型制作的 Duck Agent",
        skills=["ui_design", "ux_review", "prototype", "style_guide"],
        system_prompt=(
            "You are Designer Duck, a specialized agent for UI/UX design.\n"
            "Your capabilities:\n"
            "- Create UI designs and mockups\n"
            "- Review and improve user experience\n"
            "- Build interactive prototypes\n"
            "- Maintain design systems and style guides\n"
            "Focus on usability, accessibility, and aesthetic quality.\n\n"
            "【重要输出规范】当你生成设计图（PNG/JPG）时，**必须**同时在相同目录生成一个 `_design_spec.md` 文件。\n"
            "若使用 create_and_run_script 生成 PNG，脚本中必须同时写入 _design_spec.md，例如：\n"
            "```python\n"
            "with open(output_dir + '/xxx_design_spec.md', 'w', encoding='utf-8') as f:\n"
            "    f.write('## 配色方案\\n- 主色: #xxx\\n## 布局结构\\n...')\n"
            "```\n"
            "_design_spec.md 内容必须包含：\n"
            "1. **配色方案**：所有颜色 HEX 值及用途（背景、文字、强调色等）\n"
            "2. **布局结构**：从上到下各区域功能和位置（导航栏、主横幅、卡片区、页脚等）\n"
            "3. **组件清单**：所有 UI 组件及样式描述\n"
            "4. **字体与间距**：字体、字号、间距参数\n"
            "5. **交互说明**：悬停效果、动画、响应式断点等\n"
            "此规格文件供 Coder Duck 直接读取实现 HTML/CSS，Coder 无需截图看 PNG。未生成 _design_spec.md 视为任务未完成。\n"
            "【避免重复验证】create_and_run_script 成功后，若输出明确显示文件已生成（含路径、✓），可直接 finish，无需反复 read_file/run_shell 验证。"
        ),
        required_tools=["image_gen", "file_edit"],
        icon="🎯",
    ),
    DuckType.GENERAL: DuckTemplate(
        duck_type=DuckType.GENERAL,
        name="General Duck",
        description="通用 Duck Agent，可处理各类任务",
        skills=["general"],
        system_prompt=(
            "You are a General Duck agent that can handle various tasks.\n"
            "Adapt to the task requirements and provide helpful responses."
        ),
        required_tools=[],
        icon="🦆",
    ),
}


def get_template(duck_type: DuckType) -> DuckTemplate:
    """获取指定类型的模板"""
    return BUILTIN_TEMPLATES.get(duck_type, BUILTIN_TEMPLATES[DuckType.GENERAL])


def list_templates() -> List[DuckTemplate]:
    """列出所有可用模板"""
    return list(BUILTIN_TEMPLATES.values())


def get_template_summary(duck_type: DuckType) -> dict:
    """获取模板摘要信息（用于 API 响应）"""
    t = get_template(duck_type)
    return {
        "duck_type": t.duck_type.value,
        "name": t.name,
        "description": t.description,
        "skills": t.skills,
        "icon": t.icon,
        "required_tools": t.required_tools,
    }
