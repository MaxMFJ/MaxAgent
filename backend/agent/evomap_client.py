"""
EvoMap Network Client
Handles all communication with the EvoMap network (https://evomap.ai).
Provides node registration, capsule publishing, capsule search/inheritance,
with automatic retry, local caching, and full audit logging.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from .evomap_models import (
    Capsule, Gene, EvolutionEvent, NodeRegistration,
    NodeStatus, compute_asset_id, get_env_fingerprint,
)

logger = logging.getLogger(__name__)

EVOMAP_BASE_URL = os.environ.get("EVOMAP_BASE_URL", "https://evomap.ai/api/v1")
EVOMAP_API_KEY = os.environ.get("EVOMAP_API_KEY", "")

DATA_DIR = Path(os.path.dirname(__file__)).parent / "data" / "evomap"
GENES_FILE = DATA_DIR / "genes.json"
CAPSULES_FILE = DATA_DIR / "capsules.json"
EVENTS_FILE = DATA_DIR / "events.jsonl"
NODE_FILE = DATA_DIR / "node.json"
INHERITED_DIR = DATA_DIR / "inherited"
LOG_FILE = DATA_DIR / "evomap.log"

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=15)
MAX_RETRIES = 3
RETRY_BACKOFF = [1, 3, 8]


def _ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    INHERITED_DIR.mkdir(parents=True, exist_ok=True)


def _append_log(entry: Dict[str, Any]):
    """Append structured log entry for audit trail."""
    _ensure_dirs()
    entry.setdefault("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _save_json(path: Path, data: Any):
    _ensure_dirs()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_json(path: Path, default: Any = None) -> Any:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


class EvoMapClient:
    """
    Async client for EvoMap GEP network.
    All operations are idempotent and logged for traceability.
    """

    def __init__(self, base_url: str = "", api_key: str = ""):
        self.base_url = (base_url or EVOMAP_BASE_URL).rstrip("/")
        self.api_key = api_key or EVOMAP_API_KEY
        self._session: Optional[aiohttp.ClientSession] = None
        self._node: Optional[NodeRegistration] = None
        _ensure_dirs()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=DEFAULT_TIMEOUT,
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict] = None,
        retries: int = MAX_RETRIES,
    ) -> Tuple[bool, Any]:
        """
        Generic HTTP request with retry + backoff.
        Returns (success, response_data_or_error_message).
        """
        url = f"{self.base_url}{path}"
        last_error = ""
        for attempt in range(retries):
            try:
                session = await self._get_session()
                kwargs: Dict[str, Any] = {}
                if payload is not None:
                    kwargs["json"] = payload
                async with session.request(method, url, **kwargs) as resp:
                    body = await resp.text()
                    if resp.status in (200, 201):
                        try:
                            data = json.loads(body)
                        except json.JSONDecodeError:
                            data = body
                        _append_log({
                            "action": f"{method} {path}",
                            "status": resp.status,
                            "attempt": attempt + 1,
                            "success": True,
                        })
                        return True, data
                    elif resp.status == 401:
                        _append_log({
                            "action": f"{method} {path}",
                            "status": 401,
                            "error": "authentication_failed",
                        })
                        return False, "Authentication failed: invalid API key"
                    elif resp.status == 403:
                        _append_log({
                            "action": f"{method} {path}",
                            "status": 403,
                            "error": "permission_denied",
                        })
                        return False, "Permission denied"
                    else:
                        last_error = f"HTTP {resp.status}: {body[:200]}"
            except asyncio.TimeoutError:
                last_error = "Request timed out"
            except aiohttp.ClientError as e:
                last_error = f"Network error: {e}"
            except Exception as e:
                last_error = f"Unexpected error: {e}"

            if attempt < retries - 1:
                wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                logger.warning(f"EvoMap request {method} {path} attempt {attempt + 1} failed: {last_error}, retrying in {wait}s")
                await asyncio.sleep(wait)

        _append_log({
            "action": f"{method} {path}",
            "error": last_error,
            "attempts": retries,
            "success": False,
        })
        return False, last_error

    # ─── Node Registration ───

    def get_local_node(self) -> Optional[NodeRegistration]:
        """Load locally cached node registration."""
        data = _load_json(NODE_FILE)
        if data:
            self._node = NodeRegistration.from_dict(data)
            return self._node
        return None

    async def register_node(self, capabilities: List[str], endpoint: str = "") -> Dict[str, Any]:
        """
        Register this agent as a node on the EvoMap network.
        Falls back to local-only registration if network is unreachable.
        """
        node = self.get_local_node()
        if node is None:
            node = NodeRegistration(capabilities=capabilities, endpoint=endpoint)

        node.capabilities = capabilities
        node.status = NodeStatus.ONLINE
        if endpoint:
            node.endpoint = endpoint

        payload = node.to_dict()
        ok, resp = await self._request("POST", "/nodes/register", payload)

        result = {
            "node_id": node.node_id,
            "registration": "network" if ok else "local_only",
            "status": "success" if ok else "fallback",
            "network_response": resp if ok else None,
            "error": resp if not ok else None,
        }

        if ok and isinstance(resp, dict):
            node.node_id = resp.get("node_id", node.node_id)
            result["node_id"] = node.node_id

        _save_json(NODE_FILE, node.to_dict())
        self._node = node

        event = EvolutionEvent(
            intent="register",
            signals=capabilities,
            summary=f"Node registered: {result['registration']}",
            outcome="success" if ok else "fallback",
            details=result,
        )
        _append_event(event)

        logger.info(f"EvoMap node registered: {result['registration']} (id={node.node_id})")
        return result

    # ─── Capsule Publishing ───

    async def publish_capsule(self, capsule: Capsule) -> Dict[str, Any]:
        """Publish a capsule to the EvoMap network. Cache locally regardless."""
        capsule_dict = capsule.to_dict()
        if not capsule.asset_id:
            capsule.asset_id = compute_asset_id(capsule_dict)
            capsule_dict["asset_id"] = capsule.asset_id

        _save_local_capsule(capsule)

        ok, resp = await self._request("POST", "/capsules/publish", capsule_dict)

        result = {
            "capsule_id": capsule.id,
            "asset_id": capsule.asset_id,
            "published": "network" if ok else "local_only",
            "status": "success" if ok else "fallback",
            "error": resp if not ok else None,
        }

        event = EvolutionEvent(
            intent="publish",
            capsule_id=capsule.id,
            gene_id=capsule.gene,
            signals=capsule.trigger,
            summary=f"Capsule published: {result['published']}",
            outcome="success" if ok else "fallback",
            details=result,
        )
        _append_event(event)

        logger.info(f"Capsule published: {result['published']} (id={capsule.id})")
        return result

    # ─── Capsule Search & Inheritance ───

    async def search_capsules(
        self,
        signals: List[str],
        limit: int = 10,
        min_confidence: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Search the EvoMap network for capsules matching given signals.
        Falls back to locally inherited capsules if network is unreachable.
        """
        payload = {
            "signals": signals,
            "limit": limit,
            "min_confidence": min_confidence,
            "platform": get_env_fingerprint()["platform"],
        }

        ok, resp = await self._request("POST", "/capsules/search", payload)

        if ok and isinstance(resp, dict):
            capsules_data = resp.get("capsules", [])
            result = {
                "source": "network",
                "count": len(capsules_data),
                "capsules": capsules_data,
                "status": "success",
            }
        else:
            local_capsules = self._search_local_capsules(signals, limit, min_confidence)
            result = {
                "source": "local_cache",
                "count": len(local_capsules),
                "capsules": [c.to_dict() for c in local_capsules],
                "status": "fallback",
                "error": resp if not ok else None,
            }

        _append_log({
            "action": "search_capsules",
            "signals": signals,
            "source": result["source"],
            "count": result["count"],
        })

        return result

    async def inherit_capsule(self, capsule_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inherit (download and validate) a capsule from the network.
        Stores in local inherited cache after validation.
        """
        try:
            capsule = Capsule.from_dict(capsule_data)
        except Exception as e:
            result = {
                "capsule_id": capsule_data.get("id", "unknown"),
                "status": "rejected",
                "error": f"Invalid capsule format: {e}",
            }
            _append_log({"action": "inherit_capsule", **result})
            return result

        # Verify asset_id integrity
        expected_id = compute_asset_id(capsule.to_dict())
        if capsule.asset_id and capsule.asset_id != expected_id:
            logger.warning(f"Asset ID mismatch for capsule {capsule.id}: expected {expected_id[:20]}..., got {capsule.asset_id[:20]}...")

        # Lower confidence for external capsules (safety margin)
        capsule.confidence = min(capsule.confidence * 0.8, 0.95)

        # Save to inherited directory
        inherited_path = INHERITED_DIR / f"{capsule.id}.json"
        _save_json(inherited_path, capsule.to_dict())

        event = EvolutionEvent(
            intent="inherit",
            capsule_id=capsule.id,
            gene_id=capsule.gene,
            signals=capsule.trigger,
            summary=f"Inherited capsule from network: {capsule.summary[:100]}",
            outcome="success",
            details={"confidence": capsule.confidence, "source": "network"},
        )
        _append_event(event)

        result = {
            "capsule_id": capsule.id,
            "gene": capsule.gene,
            "confidence": capsule.confidence,
            "status": "inherited",
            "triggers": capsule.trigger,
        }
        logger.info(f"Capsule inherited: {capsule.id} (confidence={capsule.confidence:.2f})")
        return result

    # ─── Gene Management ───

    async def search_genes(self, signals: List[str]) -> Dict[str, Any]:
        """Search for matching genes on the network."""
        payload = {"signals": signals}
        ok, resp = await self._request("POST", "/genes/search", payload)

        if ok and isinstance(resp, dict):
            return {"source": "network", "genes": resp.get("genes", []), "status": "success"}

        local_genes = self._load_local_genes()
        matched = [g for g in local_genes if _signals_overlap(signals, g.get("signals_match", []))]
        return {"source": "local_cache", "genes": matched, "status": "fallback"}

    # ─── Local Operations ───

    def _search_local_capsules(
        self, signals: List[str], limit: int = 10, min_confidence: float = 0.5
    ) -> List[Capsule]:
        """Search locally cached + inherited capsules."""
        all_capsules = self._load_all_local_capsules()
        scored = []
        for c in all_capsules:
            if c.confidence < min_confidence:
                continue
            overlap = _signals_overlap(signals, c.trigger)
            if overlap > 0:
                scored.append((overlap, c))
        scored.sort(key=lambda x: (-x[0], -x[1].confidence))
        return [c for _, c in scored[:limit]]

    def _load_all_local_capsules(self) -> List[Capsule]:
        """Load capsules from local store + inherited directory."""
        capsules = []
        local_data = _load_json(CAPSULES_FILE, {"capsules": []})
        for cd in local_data.get("capsules", []):
            try:
                capsules.append(Capsule.from_dict(cd))
            except Exception:
                pass

        if INHERITED_DIR.exists():
            for fp in sorted(INHERITED_DIR.glob("*.json")):
                try:
                    data = _load_json(fp)
                    if data:
                        capsules.append(Capsule.from_dict(data))
                except Exception:
                    pass
        return capsules

    def _load_local_genes(self) -> List[Dict[str, Any]]:
        data = _load_json(GENES_FILE, {"genes": []})
        return data.get("genes", [])

    def get_local_capsules(self) -> List[Capsule]:
        return self._load_all_local_capsules()

    def get_local_genes(self) -> List[Gene]:
        raw = self._load_local_genes()
        genes = []
        for g in raw:
            try:
                genes.append(Gene.from_dict(g))
            except Exception:
                pass
        return genes

    def get_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Read recent evolution events."""
        if not EVENTS_FILE.exists():
            return []
        events = []
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return events[-limit:]

    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Read the full audit log."""
        if not LOG_FILE.exists():
            return []
        entries = []
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries[-limit:]


def _save_local_capsule(capsule: Capsule):
    """Append capsule to local store."""
    _ensure_dirs()
    data = _load_json(CAPSULES_FILE, {"version": 1, "capsules": []})
    existing_ids = {c.get("id") for c in data["capsules"]}
    if capsule.id not in existing_ids:
        data["capsules"].append(capsule.to_dict())
        _save_json(CAPSULES_FILE, data)


def _append_event(event: EvolutionEvent):
    """Append evolution event to JSONL log."""
    _ensure_dirs()
    with open(EVENTS_FILE, "a", encoding="utf-8") as f:
        f.write(event.to_jsonl() + "\n")


def _signals_overlap(signals_a: List[str], signals_b: List[str]) -> float:
    """Compute signal overlap ratio (0..1)."""
    if not signals_a or not signals_b:
        return 0.0
    set_b = {s.lower() for s in signals_b}
    hits = sum(1 for s in signals_a if s.lower() in set_b)
    # Also do fuzzy substring matching
    for sa in signals_a:
        sa_low = sa.lower()
        for sb in set_b:
            if sa_low in sb or sb in sa_low:
                hits += 0.5
    return min(hits / max(len(signals_a), 1), 1.0)


# ─── Singleton ───

_client: Optional[EvoMapClient] = None


def get_evomap_client() -> EvoMapClient:
    global _client
    if _client is None:
        _client = EvoMapClient()
    return _client


def reset_evomap_client():
    global _client
    if _client:
        try:
            asyncio.get_event_loop().run_until_complete(_client.close())
        except Exception:
            pass
    _client = None
