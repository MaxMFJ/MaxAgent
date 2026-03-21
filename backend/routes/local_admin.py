import os
import signal
import subprocess
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/local-admin", tags=["local-admin"])


_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_WEBSITE_DIR = os.path.join(_PROJECT_ROOT, "website")
_WEB_DIR = os.path.join(_PROJECT_ROOT, "web")
_TUNNEL_DIR = "/Users/lzz/Desktop/tunnel"
_TUNNEL_CONFIG = os.path.join(_TUNNEL_DIR, "config.yml")
_TUNNEL_NAME = "chowduck-tunnel"

_WEBSITE_PORT = 4180
_WEB_PORT = 5173


_procs: Dict[str, subprocess.Popen] = {}


def _is_localhost(request: Request) -> bool:
    host = getattr(request.client, "host", None)
    return host in {"127.0.0.1", "::1", "localhost"}


def _require_auth(request: Request):
    if not _is_localhost(request):
        raise HTTPException(status_code=403, detail="local-admin is only available on localhost")

    token = (os.getenv("LOCAL_ADMIN_TOKEN") or "").strip()
    if not token:
        return

    provided = (request.headers.get("X-Local-Admin-Token") or "").strip()
    if not provided:
        provided = (request.query_params.get("token") or "").strip()

    if provided != token:
        raise HTTPException(status_code=401, detail="invalid token")


def _pid_alive(p: subprocess.Popen) -> bool:
    return p.poll() is None


def _start_proc(name: str, cmd: str, cwd: Optional[str] = None, env: Optional[dict] = None):
    existing = _procs.get(name)
    if existing and _pid_alive(existing):
        raise HTTPException(status_code=409, detail=f"{name} already running")

    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    p = subprocess.Popen(
        ["bash", "-lc", cmd],
        cwd=cwd,
        env=merged_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _procs[name] = p


def _stop_proc(name: str):
    p = _procs.get(name)
    if not p or not _pid_alive(p):
        _procs.pop(name, None)
        return

    try:
        p.send_signal(signal.SIGTERM)
        p.wait(timeout=5)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass
    finally:
        _procs.pop(name, None)


def _status():
    out = {}
    for k, p in list(_procs.items()):
        alive = _pid_alive(p)
        out[k] = {"running": alive, "pid": p.pid if alive else None}
        if not alive:
            _procs.pop(k, None)
    for k in ["website", "web", "tunnel"]:
        out.setdefault(k, {"running": False, "pid": None})
    return out


@router.get("/ui", response_class=HTMLResponse)
async def local_admin_ui(request: Request):
    try:
        _require_auth(request)

        token = (os.getenv("LOCAL_ADMIN_TOKEN") or "").strip()
        token_hint = "" if not token else "<div style=\"margin:8px 0;color:#666\">需要 Token。请设置 <code>LOCAL_ADMIN_TOKEN</code> 并在下方填写。</div>"

        html = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>ChowDuck 本地管理</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial; margin: 24px; max-width: 860px; }
    h1 { margin: 0 0 12px; }
    .row { display:flex; gap:12px; flex-wrap:wrap; margin: 10px 0; }
    button { padding: 10px 12px; border-radius: 10px; border: 1px solid #ddd; background: #fff; cursor: pointer; }
    button.primary { background:#111; color:#fff; border-color:#111; }
    button.danger { background:#b00020; color:#fff; border-color:#b00020; }
    .card { border:1px solid #eee; border-radius: 14px; padding: 14px; margin: 12px 0; }
    .status { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; white-space: pre; background:#fafafa; border:1px solid #eee; padding:12px; border-radius: 10px; }
    input { padding: 10px 12px; border-radius: 10px; border: 1px solid #ddd; width: 320px; }
    small { color:#666; }
  </style>
</head>
<body>
  <h1>ChowDuck 本地管理</h1>
  <div><small>仅本地可用。用于启动 website/web/tunnel 本地进程。</small></div>
  __TOKEN_HINT__

  <div class=\"card\">
    <div class=\"row\">
      <input id=\"token\" placeholder=\"Token（可选）\" />
      <button class=\"primary\" onclick=\"refresh()\">刷新状态</button>
      <button onclick=\"startAll()\">全部启动</button>
      <button class=\"danger\" onclick=\"stopAll()\">全部停止</button>
    </div>
  </div>

  <div class=\"card\">
    <h3>Website（端口 __WEBSITE_PORT__）</h3>
    <div class=\"row\">
      <button onclick=\"start('website')\">启动</button>
      <button class=\"danger\" onclick=\"stop('website')\">停止</button>
    </div>
  </div>

  <div class=\"card\">
    <h3>Web（端口 __WEB_PORT__）</h3>
    <div class=\"row\">
      <button onclick=\"start('web')\">启动</button>
      <button class=\"danger\" onclick=\"stop('web')\">停止</button>
    </div>
  </div>

  <div class=\"card\">
    <h3>Cloudflare Tunnel</h3>
    <div class=\"row\">
      <button onclick=\"start('tunnel')\">启动</button>
      <button class=\"danger\" onclick=\"stop('tunnel')\">停止</button>
    </div>
    <small>配置：<code>__TUNNEL_CONFIG__</code></small>
  </div>

  <div class=\"card\">
    <h3>状态</h3>
    <div id=\"status\" class=\"status\">加载中...</div>
  </div>

<script>
  function tokenHeader() {
    const t = document.getElementById('token').value.trim();
    return t ? {'X-Local-Admin-Token': t} : {};
  }

  async function api(path, opts={}) {
    const headers = Object.assign({'Content-Type': 'application/json'}, tokenHeader(), opts.headers || {});
    const res = await fetch(path, Object.assign({headers}, opts));
    const text = await res.text();
    let data;
    try { data = JSON.parse(text); } catch(e) { data = {raw: text}; }
    if (!res.ok) {
      throw new Error((data && (data.detail || data.message)) || (res.status + ' ' + res.statusText));
    }
    return data;
  }

  async function refresh() {
    try {
      const s = await api('/local-admin/status');
      document.getElementById('status').textContent = JSON.stringify(s, null, 2);
    } catch (e) {
      document.getElementById('status').textContent = '错误：' + e.message;
    }
  }

  async function start(name) {
    await api('/local-admin/start', {method:'POST', body: JSON.stringify({name})});
    await refresh();
  }

  async function stop(name) {
    await api('/local-admin/stop', {method:'POST', body: JSON.stringify({name})});
    await refresh();
  }

  async function startAll() {
    await api('/local-admin/start-all', {method:'POST'});
    await refresh();
  }

  async function stopAll() {
    await api('/local-admin/stop-all', {method:'POST'});
    await refresh();
  }

  refresh();
  setInterval(refresh, 2000);
</script>
</body>

</html>"""

        html = (
            html.replace("__TOKEN_HINT__", token_hint)
            .replace("__WEBSITE_PORT__", str(_WEBSITE_PORT))
            .replace("__WEB_PORT__", str(_WEB_PORT))
            .replace("__TUNNEL_CONFIG__", _TUNNEL_CONFIG)
        )

        return HTMLResponse(html)
    except HTTPException:
        raise
    except Exception as e:
        return HTMLResponse(
            "<!doctype html><html><body><pre>本地管理页面错误：" + str(e) + "</pre></body></html>",
            status_code=500,
        )


@router.get("/status")
async def local_admin_status(request: Request):
    _require_auth(request)
    return {"success": True, "status": _status()}


def _start_by_name(name: str):
    if name == "website":
        _start_proc(
            "website",
            f"npm run dev -- --port {_WEBSITE_PORT} --host 127.0.0.1",
            cwd=_WEBSITE_DIR,
        )
        return
    if name == "web":
        _start_proc(
            "web",
            f"npm run dev -- --port {_WEB_PORT} --host 127.0.0.1",
            cwd=_WEB_DIR,
        )
        return
    if name == "tunnel":
        if not os.path.isfile(_TUNNEL_CONFIG):
            raise HTTPException(status_code=400, detail=f"tunnel config not found: {_TUNNEL_CONFIG}")
        _start_proc(
            "tunnel",
            f"cloudflared tunnel --config '{_TUNNEL_CONFIG}' run '{_TUNNEL_NAME}'",
            cwd=_TUNNEL_DIR,
        )
        return
    raise HTTPException(status_code=400, detail="unknown name")


@router.post("/start")
async def local_admin_start(request: Request):
    _require_auth(request)
    body = await request.json()
    name = (body.get("name") or "").strip()

    if name == "website":
        _start_proc(
            "website",
            f"npm run dev -- --port {_WEBSITE_PORT} --host 127.0.0.1",
            cwd=_WEBSITE_DIR,
        )
    elif name == "web":
        _start_proc(
            "web",
            f"npm run dev -- --port {_WEB_PORT} --host 127.0.0.1",
            cwd=_WEB_DIR,
        )
    elif name == "tunnel":
        if not os.path.isfile(_TUNNEL_CONFIG):
            raise HTTPException(status_code=400, detail=f"tunnel config not found: {_TUNNEL_CONFIG}")
        _start_proc(
            "tunnel",
            f"cloudflared tunnel --config '{_TUNNEL_CONFIG}' run '{_TUNNEL_NAME}'",
            cwd=_TUNNEL_DIR,
        )
    else:
        raise HTTPException(status_code=400, detail="unknown name")

    return {"success": True, "status": _status()}


@router.post("/stop")
async def local_admin_stop(request: Request):
    _require_auth(request)
    body = await request.json()
    name = (body.get("name") or "").strip()

    if name not in {"website", "web", "tunnel"}:
        raise HTTPException(status_code=400, detail="unknown name")

    _stop_proc(name)
    return {"success": True, "status": _status()}


@router.post("/start-all")
async def local_admin_start_all(request: Request):
    _require_auth(request)

    errors = []
    for name in ["website", "web", "tunnel"]:
        try:
            _start_by_name(name)
        except Exception as e:
            errors.append({"name": name, "error": str(e)})

    return {"success": len(errors) == 0, "errors": errors, "status": _status()}


@router.post("/stop-all")
async def local_admin_stop_all(request: Request):
    _require_auth(request)

    for name in ["tunnel", "web", "website"]:
        _stop_proc(name)

    return {"success": True, "status": _status()}
