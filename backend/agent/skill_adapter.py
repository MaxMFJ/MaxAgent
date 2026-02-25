"""
Skill Adapter — 将开源 Agent Skills 格式 (SKILL.md) 转换为本地 SkillCapsule。

支持的开源格式：
  1. Agent Skills 规范 (agentskills.io) — SKILL.md = YAML frontmatter + Markdown 正文
  2. skills.json 索引 — skillcreatorai/Ai-Agent-Skills 用的技能清单
  3. MCP tool definition — { name, description, inputSchema } JSON

转换后统一成 SkillCapsule（id/description/inputs/outputs/procedure），
可直接注册到 CapsuleRegistry 被 Agent 调用。
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .capsule_models import SkillCapsule, CAPSULE_SKILL_SCHEMA_VERSION

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────
#  1. SKILL.md 解析
# ────────────────────────────────────────────

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def parse_skill_md(text: str, source: str = "skill_md") -> Optional[Dict[str, Any]]:
    """
    解析 SKILL.md 文本 → Capsule 字典。
    YAML frontmatter 提取 name / description / allowed-tools / metadata，
    Markdown 正文作为 subtask description 放入 procedure。
    """
    fm = _extract_frontmatter(text)
    if not fm:
        return None

    name = fm.get("name", "").strip()
    description = fm.get("description", "").strip()
    if not name:
        return None

    body = _FRONTMATTER_RE.sub("", text).strip()
    sections = _split_markdown_sections(body)

    procedure = _build_procedure_from_sections(sections, fm)

    allowed_tools = fm.get("allowed-tools", "")
    tags = [t.strip() for t in allowed_tools.split() if t.strip()] if isinstance(allowed_tools, str) else []
    tags.append("agent-skill")

    capsule_dict: Dict[str, Any] = {
        "id": f"skill_{name}",
        "description": description or name,
        "inputs": {"task": {"type": "string", "description": "Task description or user request"}},
        "outputs": {"result": {"type": "object", "description": "Execution result"}},
        "procedure": procedure,
        "task_type": _infer_task_type(name, description, tags),
        "tags": tags,
        "capability": [name.replace("-", "_")],
        "schema_version": CAPSULE_SKILL_SCHEMA_VERSION,
        "source": source,
        "metadata": {
            "original_format": "agent_skills_md",
            "license": fm.get("license", ""),
            "compatibility": fm.get("compatibility", ""),
            "extra": fm.get("metadata", {}),
        },
    }
    return capsule_dict


def _extract_frontmatter(text: str) -> Optional[Dict[str, Any]]:
    """提取 YAML frontmatter。"""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    try:
        import yaml
        return yaml.safe_load(m.group(1)) or {}
    except ImportError:
        return _simple_yaml_parse(m.group(1))
    except Exception:
        return None


def _simple_yaml_parse(raw: str) -> Dict[str, Any]:
    """无 PyYAML 时的简易 key: value 解析。"""
    result: Dict[str, Any] = {}
    for line in raw.split("\n"):
        line = line.strip()
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip()
    return result


def _split_markdown_sections(body: str) -> List[Tuple[str, str]]:
    """将 Markdown 正文按 ## 标题拆分为 [(title, content), ...]。"""
    sections: List[Tuple[str, str]] = []
    current_title = "overview"
    current_lines: List[str] = []
    for line in body.split("\n"):
        if line.startswith("## "):
            if current_lines:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_title, "\n".join(current_lines).strip()))
    return sections


def _build_procedure_from_sections(
    sections: List[Tuple[str, str]],
    frontmatter: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    将 Markdown 各 section 转为 procedure steps。
    每个 section 成为一个 subtask step，描述里带指令。
    """
    steps: List[Dict[str, Any]] = []
    for i, (title, content) in enumerate(sections):
        if not content.strip():
            continue
        truncated = content[:2000] if len(content) > 2000 else content
        steps.append({
            "id": f"step_{i}",
            "type": "subtask",
            "description": f"[{title}] {truncated}",
        })
    if not steps:
        desc = frontmatter.get("description", "Execute skill")
        steps.append({"id": "step_0", "type": "subtask", "description": desc})
    return steps


def _infer_task_type(name: str, description: str, tags: List[str]) -> str:
    """从技能名/描述推断 task_type。"""
    combined = f"{name} {description}".lower()
    mapping = {
        "frontend": "development", "backend": "development", "code": "development",
        "test": "testing", "qa": "testing", "playwright": "testing",
        "pdf": "document", "docx": "document", "xlsx": "document", "pptx": "document",
        "design": "creative", "art": "creative", "image": "creative",
        "search": "search", "research": "research",
        "mail": "communication", "slack": "communication", "comms": "communication",
        "file": "file_operation", "organiz": "file_operation",
        "git": "development", "jira": "productivity", "brand": "business",
    }
    for keyword, task_type in mapping.items():
        if keyword in combined:
            return task_type
    return "general"


# ────────────────────────────────────────────
#  2. skills.json 索引解析
# ────────────────────────────────────────────

def parse_skills_json(data: Any, source: str = "skills_json") -> List[Dict[str, Any]]:
    """
    解析 skills.json 索引（如 skillcreatorai/Ai-Agent-Skills 的格式）。
    格式: { "skills": [ { "name": "...", "description": "...", "category": "..." }, ... ] }
    或   [ { "name": "...", ... }, ... ]
    """
    items = []
    if isinstance(data, dict):
        items = data.get("skills", data.get("entries", []))
    elif isinstance(data, list):
        items = data

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name", "").strip()
        if not name:
            continue
        desc = item.get("description", name)
        category = item.get("category", "")
        tags = [t.strip() for t in (item.get("tags") or []) if t.strip()]
        tags.append("agent-skill")
        if category:
            tags.append(category.lower())

        results.append({
            "id": f"skill_{name}",
            "description": desc,
            "inputs": {"task": {"type": "string", "description": "Task description"}},
            "outputs": {"result": {"type": "object", "description": "Result"}},
            "procedure": [{"id": "step_0", "type": "subtask", "description": desc}],
            "task_type": category.lower() if category else "general",
            "tags": tags,
            "capability": [name.replace("-", "_")],
            "schema_version": CAPSULE_SKILL_SCHEMA_VERSION,
            "source": source,
            "metadata": {"original_format": "skills_json", "raw": item},
        })
    return results


# ────────────────────────────────────────────
#  3. MCP tool definition 解析
# ────────────────────────────────────────────

def parse_mcp_tool(data: Dict[str, Any], source: str = "mcp") -> Optional[Dict[str, Any]]:
    """
    解析 MCP tool definition → Capsule 字典。
    MCP 格式: { "name": "...", "description": "...", "inputSchema": { "type": "object", "properties": {...} } }
    """
    name = data.get("name", "").strip()
    description = data.get("description", "").strip()
    if not name:
        return None

    input_schema = data.get("inputSchema", data.get("input_schema", {}))
    properties = {}
    if isinstance(input_schema, dict):
        properties = input_schema.get("properties", {})

    inputs = {}
    for key, val in properties.items():
        if isinstance(val, dict):
            inputs[key] = {
                "type": val.get("type", "string"),
                "description": val.get("description", key),
            }

    return {
        "id": f"mcp_{name}",
        "description": description or name,
        "inputs": inputs or {"input": {"type": "string", "description": "Input"}},
        "outputs": {"result": {"type": "object", "description": "Tool output"}},
        "procedure": [{"id": "step_0", "type": "subtask", "description": f"Execute MCP tool: {name}. {description}"}],
        "task_type": _infer_task_type(name, description, []),
        "tags": ["mcp", name.replace("_", "-")],
        "capability": [name],
        "schema_version": CAPSULE_SKILL_SCHEMA_VERSION,
        "source": source,
        "metadata": {"original_format": "mcp_tool", "input_schema": input_schema},
    }


# ────────────────────────────────────────────
#  4. 批量转换入口
# ────────────────────────────────────────────

def adapt_skill_file(file_path: Path, source_label: str = "") -> List[Dict[str, Any]]:
    """
    自动识别文件格式并转换。
    支持: SKILL.md, skills.json, *.json (MCP tool 或 skills 列表)
    """
    results: List[Dict[str, Any]] = []
    name = file_path.name.lower()
    src = source_label or f"adapted:{file_path.name}"

    if name == "skill.md" or name.endswith(".md"):
        try:
            text = file_path.read_text(encoding="utf-8")
            cap = parse_skill_md(text, source=src)
            if cap:
                results.append(cap)
        except Exception as e:
            logger.debug(f"Failed to parse {file_path}: {e}")

    elif name.endswith(".json"):
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.debug(f"Failed to load JSON {file_path}: {e}")
            return results

        if isinstance(data, dict):
            if "skills" in data or "entries" in data:
                results.extend(parse_skills_json(data, source=src))
            elif "name" in data and ("inputSchema" in data or "input_schema" in data):
                cap = parse_mcp_tool(data, source=src)
                if cap:
                    results.append(cap)
        elif isinstance(data, list):
            results.extend(parse_skills_json(data, source=src))

    return results


def adapt_skill_directory(directory: Path, source_label: str = "") -> List[Dict[str, Any]]:
    """递归扫描目录中的 SKILL.md 和 skills.json 文件并转换。"""
    results: List[Dict[str, Any]] = []
    if not directory.exists():
        return results

    for path in sorted(directory.rglob("*")):
        if path.is_file():
            name = path.name.lower()
            if name == "skill.md" or name == "skills.json" or (name.endswith(".md") and "skill" in name):
                src = source_label or f"adapted:{path.relative_to(directory)}"
                results.extend(adapt_skill_file(path, source_label=src))
    return results
