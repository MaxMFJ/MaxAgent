"""
EvoMap Service Layer
Orchestrates the full lifecycle: registration -> inheritance -> publishing.
Provides capability resolution: when the agent needs a strategy, query EvoMap
first before falling back to local tools/strategies.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .evomap_client import get_evomap_client, EvoMapClient, _append_event
from .evomap_models import (
    Capsule, Gene, EvolutionEvent, NodeRegistration,
    GeneCategory, CapsuleOutcome, CapsuleOutcomeStatus,
    compute_asset_id, get_env_fingerprint,
)

logger = logging.getLogger(__name__)


class EvoMapService:
    """
    High-level service for EvoMap integration.

    Lifecycle:
      1. initialize() — register node, sync genes/capsules
      2. resolve_capability() — query EvoMap for strategies before local fallback
      3. publish_capability() — share proven strategies to the network
      4. get_status() — full status report
    """

    def __init__(self):
        self.client = get_evomap_client()
        self._initialized = False
        self._registration_result: Optional[Dict] = None
        self._inherited_count = 0
        self._published_count = 0

    async def initialize(self, capabilities: List[str], endpoint: str = "") -> Dict[str, Any]:
        """
        Full initialization sequence:
          1. Register node on EvoMap network
          2. Search and inherit available capsules for our capabilities
          3. Build local gene library from Chow Duck's existing strategies
        """
        results = {
            "registration": None,
            "inheritance": None,
            "local_genes": None,
            "status": "initializing",
        }

        # Step 1: Register node
        try:
            reg_result = await self.client.register_node(capabilities, endpoint)
            results["registration"] = reg_result
            self._registration_result = reg_result
            logger.info(f"EvoMap registration: {reg_result['status']}")
        except Exception as e:
            results["registration"] = {"status": "error", "error": str(e)}
            logger.error(f"EvoMap registration failed: {e}")

        # Step 2: Inherit capsules from network
        try:
            inherit_result = await self._inherit_from_network(capabilities)
            results["inheritance"] = inherit_result
            logger.info(f"EvoMap inheritance: {inherit_result.get('status')}, count={inherit_result.get('inherited_count', 0)}")
        except Exception as e:
            results["inheritance"] = {"status": "error", "error": str(e)}
            logger.error(f"EvoMap inheritance failed: {e}")

        # Step 3: Ensure local genes exist for Chow Duck capabilities
        try:
            genes_result = self._ensure_local_genes(capabilities)
            results["local_genes"] = genes_result
        except Exception as e:
            results["local_genes"] = {"status": "error", "error": str(e)}

        self._initialized = True
        results["status"] = "ready"
        return results

    async def _inherit_from_network(self, signals: List[str]) -> Dict[str, Any]:
        """Search network for capsules and inherit verified ones."""
        search_result = await self.client.search_capsules(signals, limit=20, min_confidence=0.5)
        inherited = []
        rejected = []

        for capsule_data in search_result.get("capsules", []):
            if not self._verify_capsule_applicability(capsule_data):
                rejected.append({
                    "id": capsule_data.get("id"),
                    "reason": "applicability check failed",
                })
                continue

            try:
                result = await self.client.inherit_capsule(capsule_data)
                if result["status"] == "inherited":
                    inherited.append(result)
                    self._inherited_count += 1
                else:
                    rejected.append({"id": capsule_data.get("id"), "reason": result.get("error", "unknown")})
            except Exception as e:
                rejected.append({"id": capsule_data.get("id"), "reason": str(e)})

        return {
            "source": search_result.get("source", "unknown"),
            "searched_count": search_result.get("count", 0),
            "inherited_count": len(inherited),
            "rejected_count": len(rejected),
            "inherited": inherited,
            "rejected": rejected,
            "status": "success" if inherited else ("no_matches" if not rejected else "partial"),
        }

    def _verify_capsule_applicability(self, capsule_data: Dict[str, Any]) -> bool:
        """
        Verify that a capsule is applicable to this agent's environment.
        Checks platform compatibility, confidence threshold, schema version.
        """
        env = capsule_data.get("env_fingerprint", {})
        local_env = get_env_fingerprint()

        capsule_platform = env.get("platform", "").lower()
        if capsule_platform and capsule_platform not in ("", local_env["platform"], "any"):
            logger.debug(f"Capsule platform mismatch: {capsule_platform} vs {local_env['platform']}")
            return False

        confidence = capsule_data.get("confidence", 0)
        if confidence < 0.3:
            logger.debug(f"Capsule confidence too low: {confidence}")
            return False

        outcome = capsule_data.get("outcome", {})
        if isinstance(outcome, dict) and outcome.get("status") == "failure":
            logger.debug("Capsule outcome is failure, skipping")
            return False

        return True

    def _ensure_local_genes(self, capabilities: List[str]) -> Dict[str, Any]:
        """Create default genes for Chow Duck's capabilities if they don't exist."""
        from .evomap_client import _load_json, _save_json, GENES_FILE

        data = _load_json(GENES_FILE, {"version": 1, "genes": []})
        existing_ids = {g.get("id") for g in data["genes"]}

        macagent_genes = _build_macagent_genes(capabilities)
        added = []
        for gene_dict in macagent_genes:
            if gene_dict["id"] not in existing_ids:
                data["genes"].append(gene_dict)
                added.append(gene_dict["id"])

        if added:
            _save_json(GENES_FILE, data)

        return {"total": len(data["genes"]), "added": added, "status": "ok"}

    # ─── Capability Resolution ───

    async def resolve_capability(
        self,
        task_description: str,
        signals: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Query EvoMap for a strategy/capsule to handle the given task.
        Returns matching capsules with strategies, or empty if none found.

        This is the main integration point: AgentCore calls this before
        falling back to its own tool/strategy selection.
        """
        if signals is None:
            signals = _extract_signals(task_description)

        if not signals:
            return {"found": False, "source": "none", "capsules": [], "genes": []}

        # Search capsules (network first, local fallback)
        capsule_result = await self.client.search_capsules(signals, limit=5, min_confidence=0.6)
        capsules = capsule_result.get("capsules", [])

        # Search genes
        gene_result = await self.client.search_genes(signals)
        genes = gene_result.get("genes", [])

        found = len(capsules) > 0 or len(genes) > 0
        return {
            "found": found,
            "source": capsule_result.get("source", "unknown"),
            "capsules": capsules,
            "genes": genes,
            "signals": signals,
        }

    # ─── Capability Publishing ───

    async def publish_capability(
        self,
        tool_name: str,
        strategy: List[str],
        signals: List[str],
        category: str = "capability",
        summary: str = "",
        success: bool = True,
        confidence: float = 0.85,
    ) -> Dict[str, Any]:
        """
        Publish a proven Chow Duck capability as a GEP Capsule to the network.
        """
        gene_id = f"gene_macagent_{tool_name}"
        capsule_id = f"capsule_macagent_{tool_name}_{int(time.time() * 1000)}"

        # Ensure gene exists locally
        gene = Gene(
            id=gene_id,
            category=GeneCategory(category) if category in [c.value for c in GeneCategory] else GeneCategory.CAPABILITY,
            signals_match=signals,
            preconditions=[f"Chow Duck {tool_name} tool available"],
            strategy=strategy,
        )
        self._save_gene(gene)

        capsule = Capsule(
            id=capsule_id,
            trigger=signals,
            gene=gene_id,
            summary=summary or f"Chow Duck capability: {tool_name}",
            confidence=confidence,
            outcome=CapsuleOutcome(
                status=CapsuleOutcomeStatus.SUCCESS if success else CapsuleOutcomeStatus.FAILURE,
                score=confidence,
            ),
        )

        result = await self.client.publish_capsule(capsule)
        self._published_count += 1
        return result

    def _save_gene(self, gene: Gene):
        """Save gene to local store (idempotent)."""
        from .evomap_client import _load_json, _save_json, GENES_FILE

        data = _load_json(GENES_FILE, {"version": 1, "genes": []})
        existing_ids = {g.get("id") for g in data["genes"]}
        if gene.id not in existing_ids:
            data["genes"].append(gene.to_dict())
            _save_json(GENES_FILE, data)

    # ─── Status ───

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive EvoMap integration status."""
        node = self.client.get_local_node()
        capsules = self.client.get_local_capsules()
        genes = self.client.get_local_genes()

        return {
            "initialized": self._initialized,
            "node": node.to_dict() if node else None,
            "registration": self._registration_result,
            "local_capsules": len(capsules),
            "local_genes": len(genes),
            "inherited_count": self._inherited_count,
            "published_count": self._published_count,
            "recent_events": self.client.get_events(10),
        }

    def get_audit_trail(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self.client.get_audit_log(limit)


def _extract_signals(task: str) -> List[str]:
    """
    Extract GEP-compatible signals from a task description.
    Uses keyword matching to map task intent to signal vocabulary.
    """
    signal_map = {
        "error": ["error", "错误", "失败", "fail", "bug", "crash", "exception"],
        "repair": ["修复", "fix", "repair", "恢复", "restore"],
        "optimize": ["优化", "optimize", "加速", "speed", "performance", "性能"],
        "capability_gap": ["不能", "无法", "找不到", "missing", "unsupported", "不支持"],
        "user_feature_request": ["添加", "新增", "add", "create", "implement", "实现", "开发"],
        "file_operation": ["文件", "file", "读取", "写入", "read", "write", "move", "copy"],
        "app_control": ["打开", "关闭", "启动", "open", "close", "launch", "app"],
        "browser": ["浏览器", "browser", "网页", "webpage", "url"],
        "terminal": ["终端", "terminal", "命令", "command", "shell"],
        "system": ["系统", "system", "内存", "CPU", "memory", "disk"],
        "mail": ["邮件", "email", "mail", "发送"],
        "screenshot": ["截图", "screenshot", "屏幕"],
        "search": ["搜索", "search", "查找", "find"],
    }

    task_lower = task.lower()
    matched = []
    for signal, keywords in signal_map.items():
        if any(kw in task_lower for kw in keywords):
            matched.append(signal)
    return matched


def _build_macagent_genes(capabilities: List[str]) -> List[Dict[str, Any]]:
    """Build default gene definitions for Chow Duck's native capabilities."""
    genes = []

    cap_gene_map = {
        "app_control": {
            "id": "gene_macagent_app_control",
            "category": "capability",
            "signals_match": ["app_control", "open", "close", "launch", "打开", "关闭"],
            "preconditions": ["macOS runtime available", "app_control capability active"],
            "strategy": [
                "Parse user intent for application name and action",
                "Use AppTool to open/close/activate applications",
                "Verify action result via window info",
            ],
        },
        "file_operation": {
            "id": "gene_macagent_file_ops",
            "category": "capability",
            "signals_match": ["file_operation", "file", "read", "write", "文件"],
            "preconditions": ["file system access available"],
            "strategy": [
                "Parse file path and operation type from user request",
                "Use FileTool for read/write/move/copy operations",
                "Validate operation success and report result",
            ],
        },
        "terminal": {
            "id": "gene_macagent_terminal",
            "category": "capability",
            "signals_match": ["terminal", "command", "shell", "终端", "命令"],
            "preconditions": ["terminal access available"],
            "strategy": [
                "Parse command from user request",
                "Execute via TerminalTool with safety checks",
                "Stream output and handle errors",
            ],
        },
        "browser": {
            "id": "gene_macagent_browser",
            "category": "capability",
            "signals_match": ["browser", "webpage", "url", "浏览器", "网页"],
            "preconditions": ["browser automation available"],
            "strategy": [
                "Parse target URL or search query",
                "Use BrowserTool for navigation and interaction",
                "Extract and return relevant content",
            ],
        },
        "screenshot": {
            "id": "gene_macagent_screenshot",
            "category": "capability",
            "signals_match": ["screenshot", "screen", "截图", "屏幕"],
            "preconditions": ["screenshot capability available"],
            "strategy": [
                "Capture screen or window screenshot",
                "Return image data for analysis",
            ],
        },
        "system": {
            "id": "gene_macagent_system",
            "category": "capability",
            "signals_match": ["system", "memory", "CPU", "disk", "系统"],
            "preconditions": ["system monitoring available"],
            "strategy": [
                "Query system metrics (CPU, memory, disk)",
                "Format and present system status",
            ],
        },
        "mail": {
            "id": "gene_macagent_mail",
            "category": "capability",
            "signals_match": ["mail", "email", "邮件", "发送"],
            "preconditions": ["SMTP configured"],
            "strategy": [
                "Parse recipient, subject, body from user request",
                "Send via MailTool with configured SMTP",
                "Confirm delivery status",
            ],
        },
        "search": {
            "id": "gene_macagent_search",
            "category": "capability",
            "signals_match": ["search", "web_search", "搜索", "查找"],
            "preconditions": ["web search API available"],
            "strategy": [
                "Extract search query from user intent",
                "Execute web search via WebSearchTool",
                "Summarize and present results",
            ],
        },
    }

    for cap in capabilities:
        if cap in cap_gene_map:
            gene_data = cap_gene_map[cap]
            gene_data.setdefault("type", "Gene")
            gene_data.setdefault("constraints", {"max_files": 10})
            gene_data.setdefault("validation", [])
            genes.append(gene_data)

    # Always include repair and innovate genes
    genes.append({
        "type": "Gene",
        "id": "gene_macagent_self_repair",
        "category": "repair",
        "signals_match": ["error", "exception", "failed", "crash", "错误", "失败"],
        "preconditions": ["self-healing system available"],
        "strategy": [
            "Diagnose error using SelfHealingAgent",
            "Generate repair plan",
            "Execute repair with validation",
            "Record outcome as EvolutionEvent",
        ],
        "constraints": {"max_files": 20},
        "validation": [],
    })

    genes.append({
        "type": "Gene",
        "id": "gene_macagent_self_upgrade",
        "category": "innovate",
        "signals_match": ["capability_gap", "tool_not_found", "missing", "user_feature_request"],
        "preconditions": ["self-upgrade framework available"],
        "strategy": [
            "Analyze capability gap from tool_not_found event",
            "Plan tool implementation via Self-Upgrade planner",
            "Generate, validate, and activate new tool",
            "Publish as Capsule to EvoMap network",
        ],
        "constraints": {"max_files": 25},
        "validation": [],
    })

    return genes


# ─── Singleton ───

_service: Optional[EvoMapService] = None


def get_evomap_service() -> EvoMapService:
    global _service
    if _service is None:
        _service = EvoMapService()
    return _service
