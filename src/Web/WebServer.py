import base64
import datetime
import json
import logging
import socket
import sys
import threading
import time
from typing import Optional

import bottle
from bottle import Bottle, request, response, HTTPResponse
import waitress

import psutil

# Suppress waitress request logging
logging.getLogger('waitress').setLevel(logging.WARNING)

from Web.WebBridge import WebBridge

# Limit concurrent SSE connections to avoid thread exhaustion
_SSE_SEMAPHORE = threading.Semaphore(4)

FAVICON_BYTES: bytes | None = None
_INDEX_HTML_BYTES: bytes | None = None


def _get_index_html_bytes() -> bytes:
    global _INDEX_HTML_BYTES
    if _INDEX_HTML_BYTES is None:
        _INDEX_HTML_BYTES = _build_index_html().encode("utf-8")
    return _INDEX_HTML_BYTES


def _get_favicon_bytes() -> bytes:
    global FAVICON_BYTES
    if FAVICON_BYTES is None:
        import pathlib
        if hasattr(sys, '_MEIPASS'):
            ico_path = pathlib.Path(sys._MEIPASS) / "icons" / "gaugeIcon.ico"
        else:
            ico_path = pathlib.Path(__file__).resolve().parent.parent / "icons" / "gaugeIcon.ico"
        try:
            FAVICON_BYTES = ico_path.read_bytes()
        except OSError:
            FAVICON_BYTES = b""
    return FAVICON_BYTES


_RESP_OK = b'{"ok":true}'
_RESP_400_INVALID_JSON = b'{"ok":false,"error":"Invalid JSON"}'
_RESP_400_INVALID_MODE = b'{"ok":false,"error":"Invalid mode"}'
_RESP_400_MISSING_SPEED = b'{"ok":false,"error":"Missing gpu_speed or cpu_speed"}'
_RESP_400_INVALID_SPEED = b'{"ok":false,"error":"Invalid speed values"}'
_RESP_404 = b'{"ok":false,"error":"Not found"}'
_RESP_401 = b'{"ok":false,"error":"Unauthorized"}'


# Fast scan: only the cheapest attrs. 'exe' and 'username' are expensive on Windows
# (require per-process system calls) — defer them to pass 2 for top candidates only.
_PROC_ATTRS_SCAN = ['pid', 'name', 'memory_info', 'memory_percent']

def _collect_processes(sort_by: str = "cpu", num: int = 20) -> list[dict]:
    """Collect top N processes sorted by cpu or memory.

    Strategy:
    1. Fast scan all processes with cheapest attrs (no exe/status/num_threads)
    2. Pre-sort by memory, take top candidates; fetch exe+create_time only for them
    3. Compute cpu_percent + num_threads only for final candidates
    """
    # Pass 1: fast scan — minimal attrs to reduce per-process system calls
    all_procs = []
    for p in psutil.process_iter(attrs=_PROC_ATTRS_SCAN):
        try:
            mem_info = p.info.get('memory_info')
            if mem_info is None:
                continue
            mem_mb = round(mem_info.rss / (1024 * 1024), 1)
            mem_pct = round(p.info.get('memory_percent', 0) or 0, 2)
            all_procs.append({
                "proc": p,
                "pid": p.info.get('pid', 0),
                "name": p.info.get('name', '') or '',
                "memory_mb": mem_mb,
                "memory_percent": mem_pct,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    # Pre-sort by memory, take 2x candidates
    all_procs.sort(key=lambda x: x['memory_percent'], reverse=True)
    candidates = all_procs[:num * 2]

    # Pass 2: fetch expensive attrs (exe, create_time) only for candidates
    for item in candidates:
        p = item['proc']
        try:
            ct = p.create_time()
            item['create_time'] = datetime.datetime.fromtimestamp(ct).strftime("%Y-%m-%d %H:%M:%S") if ct else ""
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError, ValueError):
            item['create_time'] = ""
        try:
            item['exe'] = p.exe() or ''
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            item['exe'] = ''

    # Pass 3: cpu_percent + num_threads only for final candidates
    for item in candidates:
        p = item.pop('proc')
        try:
            cpu = p.cpu_percent(interval=0)
            item['cpu_percent'] = round(cpu, 1)
            item['threads'] = p.num_threads()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            item['cpu_percent'] = 0.0
            item['threads'] = 0

    key = "cpu_percent" if sort_by == "cpu" else "memory_percent"
    candidates.sort(key=lambda x: x[key], reverse=True)
    return candidates[:num]


def _parse_process_params(params) -> tuple:
    """Parse sort_by and num query parameters for the /api/processes endpoints."""
    sort_by = params.get('type', 'cpu')
    if sort_by not in ('cpu', 'memory'):
        sort_by = 'cpu'
    try:
        num = int(params.get('num', '20'))
    except (ValueError, TypeError):
        num = 20
    num = max(1, min(100, num))
    return sort_by, num


# ---------------------------------------------------------------------------
# Bottle app factory
# ---------------------------------------------------------------------------

_RESP_429_TOO_MANY = b'{"ok":false,"error":"Too many failed attempts, try again later"}'


def _create_app(bridge: WebBridge,
                auth_enabled: bool = False,
                auth_user: str = "",
                auth_pass: str = "") -> Bottle:
    """Create and configure a Bottle application."""

    app = Bottle()

    # -- Auth rate limiting state --
    _auth_failures: dict[str, list[float]] = {}  # ip -> list of failure timestamps
    _AUTH_MAX_FAILURES = 5
    _AUTH_LOCKOUT_SEC = 60

    # -- CORS hook (runs after every request) --
    @app.hook('after_request')
    def _cors():
        if response.content_type != 'text/event-stream':
            response.set_header('Access-Control-Allow-Origin', '*')
            response.set_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            response.set_header('Access-Control-Allow-Headers', 'Content-Type')

    # -- Auth hook (runs before every request) --
    @app.hook('before_request')
    def _auth():
        if not auth_enabled:
            return
        client_ip = request.get_header('X-Forwarded-For', request.remote_addr)

        # Rate limiting check
        now = time.time()
        if client_ip in _auth_failures:
            # Prune old entries
            _auth_failures[client_ip] = [t for t in _auth_failures[client_ip] if now - t < _AUTH_LOCKOUT_SEC]
            if len(_auth_failures[client_ip]) >= _AUTH_MAX_FAILURES:
                raise HTTPResponse(
                    body=_RESP_429_TOO_MANY,
                    status=429,
                    headers={
                        'Content-Type': 'application/json',
                        'Retry-After': str(_AUTH_LOCKOUT_SEC),
                    },
                )

        auth_header = request.get_header('Authorization', '')
        if not auth_header.startswith('Basic '):
            _auth_failures.setdefault(client_ip, []).append(now)
            raise HTTPResponse(
                body=_RESP_401,
                status=401,
                headers={
                    'Content-Type': 'application/json',
                    'WWW-Authenticate': 'Basic realm="TCC-G15"',
                },
            )
        try:
            decoded = base64.b64decode(auth_header[6:]).decode('utf-8')
            user, passwd = decoded.split(':', 1)
        except Exception:
            _auth_failures.setdefault(client_ip, []).append(now)
            raise HTTPResponse(
                body=_RESP_401,
                status=401,
                headers={'Content-Type': 'application/json'},
            )
        if user != auth_user or passwd != auth_pass:
            _auth_failures.setdefault(client_ip, []).append(now)
            raise HTTPResponse(
                body=_RESP_401,
                status=401,
                headers={
                    'Content-Type': 'application/json',
                    'WWW-Authenticate': 'Basic realm="TCC-G15"',
                },
            )
        # Auth success — clear failures for this IP
        _auth_failures.pop(client_ip, None)

    # -- CORS preflight --
    @app.route('/api/<:re:.*>', method='OPTIONS')
    def _cors_options(path=''):
        return ''

    # -- Index --
    @app.route('/')
    @app.route('/index.html')
    def _index():
        response.content_type = 'text/html; charset=utf-8'
        response.set_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        response.set_header('Pragma', 'no-cache')
        response.set_header('Expires', '0')
        return _get_index_html_bytes()

    # -- API: status --
    @app.route('/api/status')
    def _api_status():
        response.content_type = 'application/json'
        return bridge.get_status()

    # -- API: status SSE stream --
    @app.route('/api/status/stream')
    def _api_status_stream():
        if not _SSE_SEMAPHORE.acquire(timeout=2):
            response.content_type = 'application/json'
            raise HTTPResponse(
                body=b'{"ok":false,"error":"Too many SSE connections"}',
                status=429,
                headers={'Content-Type': 'application/json', 'Retry-After': '5'},
            )
        response.content_type = 'text/event-stream; charset=utf-8'
        response.set_header('Cache-Control', 'no-cache, no-transform')
        response.set_header('X-Accel-Buffering', 'no')
        response.set_header('Access-Control-Allow-Origin', '*')
        _SSE_MAX_LIFETIME = 300  # Force reconnect every 5 minutes
        _SSE_HEARTBEAT_INTERVAL = 30
        def generate():
            start_time = time.time()
            last_heartbeat = start_time
            try:
                while True:
                    if time.time() - start_time > _SSE_MAX_LIFETIME:
                        yield b": lifetime-reached\n\n"
                        break
                    now = time.time()
                    if now - last_heartbeat >= _SSE_HEARTBEAT_INTERVAL:
                        yield b": heartbeat\n\n"
                        last_heartbeat = now
                    try:
                        status = bridge.get_status()
                        data = json.dumps(status)
                        yield f"data: {data}\n\n".encode('utf-8')
                    except Exception as e:
                        yield f"data: {json.dumps({'error': str(e)})}\n\n".encode('utf-8')
                    time.sleep(2)  # Status stream: push every 2s (reduced from 1s to lower CPU)
            finally:
                _SSE_SEMAPHORE.release()
        return generate()

    # -- API: processes (GET) --
    @app.route('/api/processes')
    def _api_processes():
        response.content_type = 'application/json'
        sort_by, num = _parse_process_params(request.params)
        procs = _collect_processes(sort_by, num)
        return {'ok': True, 'type': sort_by, 'num': num, 'processes': procs}

    # -- API: processes SSE stream --
    @app.route('/api/processes/stream')
    def _api_processes_stream():
        if not _SSE_SEMAPHORE.acquire(timeout=2):
            response.content_type = 'application/json'
            raise HTTPResponse(
                body=b'{"ok":false,"error":"Too many SSE connections"}',
                status=429,
                headers={'Content-Type': 'application/json', 'Retry-After': '5'},
            )
        response.content_type = 'text/event-stream; charset=utf-8'
        response.set_header('Cache-Control', 'no-cache, no-transform')
        response.set_header('X-Accel-Buffering', 'no')
        response.set_header('Access-Control-Allow-Origin', '*')
        # Capture request params before the loop; request is a Bottle thread-local
        # proxy that may become invalid after the handler returns.
        initial_sort_by, initial_num = _parse_process_params(request.params)
        _SSE_MAX_LIFETIME = 300
        _SSE_HEARTBEAT_INTERVAL = 30
        def generate():
            start_time = time.time()
            last_heartbeat = start_time
            try:
                sort_by, num = initial_sort_by, initial_num
                while True:
                    if time.time() - start_time > _SSE_MAX_LIFETIME:
                        yield b": lifetime-reached\n\n"
                        break
                    now = time.time()
                    if now - last_heartbeat >= _SSE_HEARTBEAT_INTERVAL:
                        yield b": heartbeat\n\n"
                        last_heartbeat = now
                    try:
                        procs = _collect_processes(sort_by, num)
                        data = json.dumps({'ok': True, 'type': sort_by, 'num': num, 'processes': procs})
                        yield f"data: {data}\n\n".encode('utf-8')
                    except Exception as e:
                        yield f"data: {json.dumps({'ok': False, 'error': str(e)})}\n\n".encode('utf-8')
                    time.sleep(5)  # Process stream: push every 5s (reduced from 3s to lower CPU)
            finally:
                _SSE_SEMAPHORE.release()
        return generate()

    # -- Favicon --
    @app.route('/favicon.ico')
    def _favicon():
        favicon = _get_favicon_bytes()
        if favicon:
            response.content_type = 'image/x-icon'
            return favicon
        raise HTTPResponse(body=_RESP_404, status=404, headers={'Content-Type': 'application/json'})

    # -- API: mode --
    @app.route('/api/mode', method='POST')
    def _api_mode():
        response.content_type = 'application/json'
        try:
            body = request.json
        except Exception:
            raise HTTPResponse(body=_RESP_400_INVALID_JSON, status=400, headers={'Content-Type': 'application/json'})
        if body is None:
            raise HTTPResponse(body=_RESP_400_INVALID_JSON, status=400, headers={'Content-Type': 'application/json'})
        mode = body.get('mode')
        if mode not in ('Balanced', 'G_Mode', 'Custom'):
            raise HTTPResponse(body=_RESP_400_INVALID_MODE, status=400, headers={'Content-Type': 'application/json'})
        bridge.set_mode(mode)
        return {'ok': True}

    # -- API: fan --
    @app.route('/api/fan', method='POST')
    def _api_fan():
        response.content_type = 'application/json'
        try:
            body = request.json
        except Exception:
            raise HTTPResponse(body=_RESP_400_INVALID_JSON, status=400, headers={'Content-Type': 'application/json'})
        if body is None:
            raise HTTPResponse(body=_RESP_400_INVALID_JSON, status=400, headers={'Content-Type': 'application/json'})
        gpu = body.get('gpu_speed')
        cpu = body.get('cpu_speed')
        if gpu is None or cpu is None:
            raise HTTPResponse(body=_RESP_400_MISSING_SPEED, status=400, headers={'Content-Type': 'application/json'})
        try:
            gpu = int(gpu)
            cpu = int(cpu)
        except (ValueError, TypeError):
            raise HTTPResponse(body=_RESP_400_INVALID_SPEED, status=400, headers={'Content-Type': 'application/json'})
        bridge.set_fan_speeds(max(0, min(120, gpu)), max(0, min(120, cpu)))
        return {'ok': True}

    return app


# ---------------------------------------------------------------------------
# Threaded WSGI server using waitress (supports streaming/SSE)
# ---------------------------------------------------------------------------

_cached_lan_ip: Optional[str] = None


class ThreadedHTTPServer(threading.Thread):
    def __init__(self, bridge: WebBridge, port: int = 8080,
                 bind_addr: str = "0.0.0.0",
                 auth_enabled: bool = False,
                 auth_user: str = "",
                 auth_pass: str = "") -> None:
        super().__init__(daemon=True)
        self.bridge = bridge
        self.port = port
        self.bind_addr = bind_addr
        self.auth_enabled = auth_enabled
        self.auth_user = auth_user
        self.auth_pass = auth_pass
        self._server = None
        self._started_event = threading.Event()
        self._stop_event = threading.Event()

    def wait_until_ready(self, timeout: float = 5.0) -> bool:
        return self._started_event.wait(timeout)

    def stop(self) -> None:
        self._stop_event.set()
        if self._server:
            self._server.close()

    def run(self) -> None:
        app = _create_app(
            bridge=self.bridge,
            auth_enabled=self.auth_enabled,
            auth_user=self.auth_user,
            auth_pass=self.auth_pass,
        )
        # Warmup psutil cpu_percent baseline for all processes (non-blocking).
        # This ensures subsequent cpu_percent(interval=0) calls return meaningful values.
        try:
            for p in psutil.process_iter(attrs=['pid']):
                try:
                    p.cpu_percent(interval=0)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass
        try:
            self._server = waitress.create_server(
                app,
                host=self.bind_addr,
                port=self.port,
                threads=4,  # Match SSE semaphore limit to reduce thread overhead
            )
        except OSError as e:
            print(f"WebServer: failed to start on {self.bind_addr}:{self.port}: {e}")
            return
        self._started_event.set()
        print(f"WebServer: listening on http://{self.bind_addr}:{self.port}")
        self._server.run()
        print("WebServer: stopped")

    @staticmethod
    def get_lan_ip() -> str:
        global _cached_lan_ip
        if _cached_lan_ip is not None:
            return _cached_lan_ip
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                _cached_lan_ip = s.getsockname()[0]
            return _cached_lan_ip
        except Exception:
            return "127.0.0.1"


def _build_index_html() -> str:
    import pathlib, sys
    if hasattr(sys, '_MEIPASS'):
        template_path = pathlib.Path(sys._MEIPASS) / "Web" / "templates" / "index.html"
    else:
        template_path = pathlib.Path(__file__).resolve().parent / "templates" / "index.html"
    return template_path.read_text(encoding="utf-8")
