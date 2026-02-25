"""
Project Workspace Binding
LLM must NEVER choose file paths.
"""

import os
import logging

logger = logging.getLogger(__name__)

# Repo root = backend directory (where agent, tools live)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS_GENERATED_DIR = os.path.join(PROJECT_ROOT, "tools", "generated")


def _ensure_inside_project(rel_path: str) -> bool:
    """Ensure path is inside PROJECT_ROOT"""
    abs_path = os.path.normpath(os.path.join(PROJECT_ROOT, rel_path))
    return abs_path.startswith(PROJECT_ROOT + os.sep) or abs_path == PROJECT_ROOT


def write_project_file(rel_path: str, content: str):
    """
    Write content to a file inside PROJECT_ROOT.
    - Always inside PROJECT_ROOT
    - Auto create dirs
    - Return absolute path on success
    - Log path
    - Return None on failure
    """
    rel_path = rel_path.lstrip("/").lstrip("\\")
    abs_path = os.path.normpath(os.path.join(PROJECT_ROOT, rel_path))
    if not abs_path.startswith(PROJECT_ROOT + os.sep) and abs_path != PROJECT_ROOT:
        logger.error(f"[Upgrade] Rejected path outside project: {rel_path}")
        return None
    try:
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"[Upgrade] Wrote: {abs_path}")
        return abs_path
    except Exception as e:
        logger.error(f"[Upgrade] Write failed {rel_path}: {e}")
        return None
