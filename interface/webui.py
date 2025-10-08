"""FastAPI-based web interface branded as the SyntH Web UI.

This implementation exposes a functional chat front-end that integrates with
the existing Rekku core infrastructure. It reuses the same interaction
patterns that the development WebUI uses (``interface_dev/webui.py``), while
offering a refined layout, VRM avatar management, and notification helpers so
the Docker container can serve the application directly.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Deque, Dict, Optional, List

from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    UploadFile,
    File,
    Request,
    HTTPException,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.core_initializer import register_interface
from core.logging_utils import _LOG_FILE, log_debug, log_error, log_info, log_warning
import core.plugin_instance as plugin_instance


BRAND_NAME = "SyntH Web UI"
INTERFACE_NAME = "synth_webui"
LOG_PREFIX = "[synth_webui]"
_LEGACY_AUTOSTART_ENV = "WEBWAIFU_AUTOSTART"
_AUTOSTART_ENV = "SYNTH_WEBUI_AUTOSTART"
_LEGACY_VRM_DIR_ENV = "WEBWAIFU_VRM_DIR"
_VRM_DIR_ENV = "SYNTH_WEBUI_VRM_DIR"


class SynthWebUIInterface:
    """Production-ready web interface served from the Docker container."""

    def __init__(self) -> None:
        self.app = FastAPI(title=BRAND_NAME, version="1.0")
        self.start_time = datetime.utcnow()
        self.connections: Dict[str, WebSocket] = {}
        self.message_history: Dict[str, Deque[dict]] = {}
        self.max_history = 100
        self.host = os.getenv("WEBUI_HOST", "0.0.0.0")
        self.port = int(os.getenv("WEBUI_PORT", "8000"))
        autostart_env = (
            os.getenv(_AUTOSTART_ENV)
            if os.getenv(_AUTOSTART_ENV) is not None
            else os.getenv(_LEGACY_AUTOSTART_ENV, "1")
        )
        self.autostart = autostart_env not in {"0", "false", "False"}
        self._server_thread: Optional[threading.Thread] = None
        self._server: Optional[object] = None  # uvicorn.Server set when started
        self._server_lock = threading.Lock()
        vrm_dir_env = os.getenv(_VRM_DIR_ENV) or os.getenv(_LEGACY_VRM_DIR_ENV)
        default_vrm_dir = Path(__file__).resolve().parent.parent / "res" / "synth_webui" / "avatars"
        self.vrm_dir = Path(vrm_dir_env).expanduser() if vrm_dir_env else default_vrm_dir
        try:
            self.vrm_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # pragma: no cover - runtime issues
            log_warning(f"{LOG_PREFIX} Failed to ensure VRM directory {self.vrm_dir}: {exc}")
        self.active_vrm_marker = self.vrm_dir / ".active"
        self.active_vrm = self._load_active_vrm()

        # Allow the UI to be embedded if desired (same-origin by default)
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        static_dir = Path(__file__).resolve().parent.parent / "docs" / "res"
        if static_dir.exists():
            self.app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
        else:
            log_warning(f"{LOG_PREFIX} static directory not found: {static_dir}")

        if self.vrm_dir.exists():
            try:
                self.app.mount("/avatars", StaticFiles(directory=str(self.vrm_dir)), name="synth-webui-avatars")
            except Exception as exc:  # pragma: no cover - runtime
                log_warning(f"{LOG_PREFIX} Unable to mount VRM directory {self.vrm_dir}: {exc}")

        self.app.get("/")(self.index)
        self.app.get("/health")(self.health)
        self.app.get("/stats")(self.stats)
        self.app.get("/logs")(self.logs_page)
        self.app.websocket("/ws")(self.websocket_endpoint)
        self.app.websocket("/logs")(self.logs_ws_endpoint)
        self.app.get("/api/vrm")(self.list_vrm_models)
        self.app.get("/api/vrm/active")(self.get_active_vrm_endpoint)
        self.app.post("/api/vrm")(self.upload_vrm_model)
        self.app.post("/api/vrm/active")(self.set_active_vrm_endpoint)
        self.app.delete("/api/vrm/{model_name}")(self.delete_vrm_model)

        register_interface(INTERFACE_NAME, self)
        log_info(f"{LOG_PREFIX} Interface registered")
        if self.autostart:
            self._ensure_background_server()
        else:
            log_info(f"{LOG_PREFIX} Autostart disabled - {BRAND_NAME} will not start automatically")

    # ------------------------------------------------------------------
    # Interface metadata
    # ------------------------------------------------------------------
    @staticmethod
    def get_interface_id() -> str:
        return INTERFACE_NAME

    @staticmethod
    def get_supported_actions() -> dict:
        return {
            "message_synth_webui": {
                "required_fields": ["text", "target"],
                "optional_fields": [],
                "description": f"Send a text message to a {BRAND_NAME} session.",
            }
        }

    @staticmethod
    def get_prompt_instructions(action_name: str) -> dict:
        if action_name == "message_synth_webui":
            return {
                "description": f"Send a message to the {BRAND_NAME} browser client.",
                "payload": {
                    "text": {
                        "type": "string",
                        "example": "Ciao!",
                        "description": "Message content to deliver",
                    },
                    "target": {
                        "type": "string",
                        "example": "session-id",
                        "description": "Session identifier returned by the websocket",
                    },
                },
            }
        return {}

    @staticmethod
    def get_interface_instructions() -> str:
        return (
            f"Use interface: {INTERFACE_NAME} to converse through the {BRAND_NAME} browser UI. "
            "The target field must contain the session identifier emitted by the "
            "websocket handshake."
        )

    # ------------------------------------------------------------------
    # HTTP Handlers
    # ------------------------------------------------------------------
    async def index(self):
        try:
            html = self._render_index()
        except Exception as exc:
            log_error(f"{LOG_PREFIX} failed to render index: {exc}")
            raise HTTPException(status_code=500, detail="Unable to render SyntH Web UI") from exc
        return HTMLResponse(content=html)

    async def health(self):
        return JSONResponse({"status": "ok", "time": datetime.utcnow().isoformat()})

    async def stats(self):
        uptime = int((datetime.utcnow() - self.start_time).total_seconds())
        return JSONResponse({"uptime": uptime, "sessions": len(self.connections)})

    async def logs_page(self):
        html = self._render_logs()
        return HTMLResponse(content=html)

    # ------------------------------------------------------------------
    # WebSocket logic
    # ------------------------------------------------------------------
    async def websocket_endpoint(self, websocket: WebSocket):
        await websocket.accept()
        session_id = str(uuid.uuid4())
        self.connections[session_id] = websocket
        self.message_history.setdefault(session_id, deque(maxlen=self.max_history))
        await websocket.send_json({"type": "session", "session_id": session_id})
        await self._replay_history(session_id)
        log_info(f"{LOG_PREFIX} Client connected: {session_id}")

        try:
            while True:
                data = await websocket.receive_text()
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    payload = {"text": data}
                text = (payload.get("text") or "").strip()
                if not text:
                    continue
                await self._append_history(session_id, "user", text)
                await self._handle_user_message(session_id, text)
        except WebSocketDisconnect:
            log_info(f"{LOG_PREFIX} Client disconnected: {session_id}")
        except Exception as exc:  # pragma: no cover - runtime issues
            log_error(f"{LOG_PREFIX} websocket error: {exc}")
        finally:
            self.connections.pop(session_id, None)
            self.message_history.pop(session_id, None)

    async def logs_ws_endpoint(self, websocket: WebSocket):  # pragma: no cover - runtime streaming
        await websocket.accept()
        log_override = os.getenv("SYNTH_LOG_PATH")
        candidates = []
        if log_override:
            candidates.append(Path(log_override).expanduser())
        candidates.extend(
            [
                Path("/app/logs/rfp.log"),
                Path.cwd() / "logs" / "rfp.log",
                Path.cwd() / "logs" / "dev" / "rfp.log",
                Path(_LOG_FILE),
            ]
        )

        unique_candidates = []
        seen = set()
        for candidate in candidates:
            if candidate is None:
                continue
            candidate = Path(candidate)
            key = candidate.expanduser()
            if key in seen:
                continue
            seen.add(key)
            unique_candidates.append(candidate)

        path = next((candidate for candidate in unique_candidates if candidate.exists()), unique_candidates[0])

        try:
            wait_seconds = int(os.getenv("SYNTH_LOG_WAIT", "20"))
            waited = 0
            while not path.exists() and waited < wait_seconds:
                await asyncio.sleep(1)
                waited += 1

            if not path.exists():
                await websocket.send_text(f"Log file not found: {path}")
                return

            with path.open("r", encoding="utf-8", errors="replace") as log_file:
                # Send last 200 lines
                log_file.seek(0)
                recent_lines = deque(log_file, maxlen=200)
                for line in recent_lines:
                    await websocket.send_text(line.rstrip())
                log_file.seek(0, os.SEEK_END)
                while True:
                    line = log_file.readline()
                    if not line:
                        await asyncio.sleep(1)
                        continue
                    await websocket.send_text(line.rstrip())
        except Exception as exc:  # pragma: no cover - runtime issues
            log_error(f"{LOG_PREFIX} log stream error: {exc}")
        finally:
            await websocket.close()

    async def _handle_user_message(self, session_id: str, text: str) -> None:
        from types import SimpleNamespace

        message = SimpleNamespace(
            chat_id=session_id,
            message_id=int(datetime.utcnow().timestamp() * 1000) % 1_000_000,
            text=text,
            date=datetime.utcnow(),
            from_user=SimpleNamespace(
                id=session_id,
                username=f"synth_{session_id[:8]}",
                first_name="SyntH",
                last_name="",
                full_name="SyntH User",
            ),
            chat=SimpleNamespace(
                id=session_id,
                type="web",
                title=f"{BRAND_NAME} Session",
                full_name=f"{BRAND_NAME} Session",
            ),
            reply_to_message=None,
        )

        log_debug(f"{LOG_PREFIX} message from {session_id}: {text}")
        try:
            response = await plugin_instance.handle_incoming_message(
                self, message, {}, INTERFACE_NAME
            )
        except Exception as exc:  # pragma: no cover - runtime issues
            log_error(f"{LOG_PREFIX} error handling message: {exc}")
            response = None

        if response:
            await self.send_message(session_id, text=response)

    async def _replay_history(self, session_id: str) -> None:
        history = self.message_history.get(session_id)
        if not history:
            return
        websocket = self.connections.get(session_id)
        if not websocket:
            return
        for item in history:
            await websocket.send_json({"type": "message", **item})

    async def _append_history(self, session_id: str, sender: str, text: str) -> None:
        history = self.message_history.setdefault(
            session_id, deque(maxlen=self.max_history)
        )
        history.append({"sender": sender, "text": text})

    # ------------------------------------------------------------------
    # Methods used by actions / plugins
    # ------------------------------------------------------------------
    async def send_message(
        self,
        payload_or_chat_id=None,
        text: Optional[str] = None,
        **kwargs,
    ) -> None:
        if isinstance(payload_or_chat_id, dict):
            payload = payload_or_chat_id
            text = payload.get("text", text)
            chat_id = payload.get("target") or payload.get("chat_id")
        else:
            chat_id = payload_or_chat_id or kwargs.get("chat_id")
            if text is None:
                text = kwargs.get("text")

        if not text or not chat_id:
            log_warning(f"{LOG_PREFIX} send_message missing text or chat_id")
            return

        websocket = self.connections.get(str(chat_id))
        if not websocket:
            log_warning(f"{LOG_PREFIX} no active websocket for session {chat_id}")
            return

        await websocket.send_json({"type": "message", "sender": "rekku", "text": text})
        await self._append_history(str(chat_id), "rekku", text)

    async def execute_action(self, action: dict, context: dict, bot, original_message):
        if action.get("type") == "message_synth_webui":
            payload = action.get("payload", {})
            await self.send_message(payload, original_message=original_message)

    # ------------------------------------------------------------------
    # VRM management API
    # ------------------------------------------------------------------
    def _load_active_vrm(self) -> Optional[str]:
        if self.active_vrm_marker.exists():
            try:
                name = self.active_vrm_marker.read_text(encoding="utf-8").strip()
            except Exception:
                name = ""
            if name:
                candidate = self.vrm_dir / Path(name).name
                if candidate.exists():
                    return candidate.name
        # Fallback to first available model
        for candidate in sorted(self.vrm_dir.glob("*.vrm")):
            return candidate.name
        return None

    def _set_active_vrm(self, model_name: Optional[str]) -> None:
        if not model_name:
            try:
                if self.active_vrm_marker.exists():
                    self.active_vrm_marker.unlink()
            except Exception:
                pass
            self.active_vrm = None
            return
        candidate = self.vrm_dir / Path(model_name).name
        if not candidate.exists():
            raise FileNotFoundError(model_name)
        try:
            self.active_vrm_marker.write_text(candidate.name, encoding="utf-8")
        except Exception as exc:  # pragma: no cover - file system issues
            log_warning(f"{LOG_PREFIX} Failed to persist active VRM: {exc}")
        self.active_vrm = candidate.name

    @staticmethod
    def _sanitize_vrm_filename(name: str) -> str:
        stem = Path(name or "avatar").stem
        safe = "".join(ch for ch in stem if ch.isalnum() or ch in ("-", "_")).strip("_-")
        if not safe:
            safe = "avatar"
        return f"{safe}_{uuid.uuid4().hex[:8]}.vrm"

    def _models_payload(self) -> dict:
        models: List[dict] = []
        for path in sorted(self.vrm_dir.glob("*.vrm")):
            try:
                stat = path.stat()
            except OSError:
                continue
            models.append(
                {
                    "name": path.name,
                    "url": f"/avatars/{path.name}",
                    "size": stat.st_size,
                    "modified": int(stat.st_mtime),
                    "active": path.name == self.active_vrm,
                }
            )
        return {"models": models, "active": self.active_vrm}

    async def list_vrm_models(self):
        return JSONResponse(self._models_payload())

    async def get_active_vrm_endpoint(self):
        if self.active_vrm:
            return JSONResponse(
                {"name": self.active_vrm, "url": f"/avatars/{self.active_vrm}"}
            )
        return JSONResponse({"name": None, "url": None})

    async def set_active_vrm_endpoint(self, request: Request):
        data = await request.json()
        name = data.get("name")
        if not name:
            raise HTTPException(status_code=400, detail="Missing 'name'")
        candidate = self.vrm_dir / Path(name).name
        if not candidate.exists():
            raise HTTPException(status_code=404, detail="Model not found")
        self._set_active_vrm(candidate.name)
        return JSONResponse(
            {"status": "ok", "name": candidate.name, "url": f"/avatars/{candidate.name}"}
        )

    async def upload_vrm_model(self, file: UploadFile = File(...)):
        if not file or not file.filename:
            raise HTTPException(status_code=400, detail="No file uploaded")
        if not file.filename.lower().endswith(".vrm"):
            raise HTTPException(status_code=400, detail="Only .vrm files are accepted")
        filename = self._sanitize_vrm_filename(file.filename)
        destination = self.vrm_dir / filename
        try:
            with destination.open("wb") as buffer:
                while True:
                    chunk = await file.read(1 << 20)
                    if not chunk:
                        break
                    buffer.write(chunk)
        except Exception as exc:
            log_error(f"{LOG_PREFIX} Failed to store VRM upload: {exc}")
            if destination.exists():
                try:
                    destination.unlink()
                except Exception:
                    pass
            raise HTTPException(status_code=500, detail="Failed to store VRM file")
        finally:
            await file.close()

        self._set_active_vrm(filename)
        return JSONResponse(
            {"status": "ok", "name": filename, "url": f"/avatars/{filename}"}, status_code=201
        )

    async def delete_vrm_model(self, model_name: str):
        sanitized = Path(model_name).name
        target = self.vrm_dir / sanitized
        if not target.exists():
            raise HTTPException(status_code=404, detail="Model not found")
        try:
            target.unlink()
        except Exception as exc:
            log_error(f"{LOG_PREFIX} Failed to delete VRM {sanitized}: {exc}")
            raise HTTPException(status_code=500, detail="Unable to delete VRM file")

        if self.active_vrm == sanitized:
            fallback = None
            for candidate in sorted(self.vrm_dir.glob("*.vrm")):
                fallback = candidate.name
                break
            self._set_active_vrm(fallback)
        return JSONResponse(self._models_payload())

    def _ensure_background_server(self) -> None:
        """Launch the FastAPI app in a background thread if not already running."""
        with self._server_lock:
            if self._server_thread and self._server_thread.is_alive():
                return

            def _runner() -> None:
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self._run_server())
                except Exception as exc:  # pragma: no cover - runtime issues
                    log_error(f"{LOG_PREFIX} Failed to start uvicorn server: {exc}")
                finally:
                    loop.close()

            log_info(f"{LOG_PREFIX} Starting {BRAND_NAME} server on http://{self.host}:{self.port}")
            self._server_thread = threading.Thread(
                target=_runner,
                name="synth-webui-uvicorn",
                daemon=True,
            )
            self._server_thread.start()

    async def _run_server(self) -> None:
        """Create and run the uvicorn server."""
        import uvicorn

        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level=os.getenv("WEBUI_LOG_LEVEL", "info"),
            lifespan="off",
        )
        server = uvicorn.Server(config)
        with self._server_lock:
            self._server = server
        try:
            await server.serve()
        finally:
            with self._server_lock:
                self._server = None

    def cleanup(self) -> None:
        with self._server_lock:
            server = self._server
        if server is not None:
            try:
                server.should_exit = True
            except Exception:  # pragma: no cover - defensive
                pass
        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=2)

    # ------------------------------------------------------------------
    # HTML template
    # ------------------------------------------------------------------
    def _render_index(self) -> str:
        logo = "/static/RFP_logo.png"
        template_path = Path(__file__).resolve().parent / "templates" / "synth_webui_index.html"
        try:
            html = template_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            log_error(f"{LOG_PREFIX} template not found: {template_path}")
            return (
                f"<html><body><h1>{BRAND_NAME}</h1>"
                "<p>Template non disponibile.</p></body></html>"
            )
        except Exception as exc:  # pragma: no cover - runtime issues
            log_error(f"{LOG_PREFIX} unable to read template: {exc}")
            return (
                f"<html><body><h1>{BRAND_NAME}</h1>"
                "<p>Errore nel rendering.</p></body></html>"
            )

        return (
            html.replace("%%BRAND_NAME%%", BRAND_NAME)
            .replace("%%LOGO_URL%%", logo)
        )

    def _render_logs(self) -> str:
        template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{brand_name} Logs</title>
    <style>
        body {{ background: #101017; color: #e0ffe0; font-family: monospace; margin: 0; }
        header {{ padding: 1rem 1.5rem; background: #1b1b28; display: flex; flex-wrap: wrap; justify-content: space-between; gap: 1rem; align-items: center; }
        header .left {{ display: flex; gap: 1rem; align-items: center; }
        header .filters {{ display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; font-size: 0.9rem; }
        header label {{ display: inline-flex; align-items: center; gap: 0.35rem; cursor: pointer; background: rgba(255, 255, 255, 0.08); padding: 0.35rem 0.6rem; border-radius: 999px; }
        header input[type="checkbox"] {{ accent-color: #ff6bd6; }
        main {{ padding: 1.5rem; }
        pre {{
            background: #09090f;
            border-radius: 12px;
            padding: 1.2rem;
            height: 80vh;
            overflow-y: auto;
            white-space: pre-wrap;
        }
        a {{ color: #9fa8ff; text-decoration: none; }
        a:hover {{ text-decoration: underline; }
    </style>
</head>
<body>
    <header>
        <div class="left">
            <strong>Realtime logs</strong>
            <a href="/">Back to chat</a>
        </div>
        <div class="filters">
            <label><input class="level-filter" data-level="info" type="checkbox" checked />INFO</label>
            <label><input class="level-filter" data-level="warning" type="checkbox" checked />WARNING</label>
            <label><input class="level-filter" data-level="error" type="checkbox" checked />ERROR</label>
            <label><input class="level-filter" data-level="debug" type="checkbox" checked />DEBUG</label>
        </div>
    </header>
    <main>
        <pre id="log"></pre>
    </main>
    <script>
        const log = document.getElementById('log');
        const filters = document.querySelectorAll('.level-filter');
        const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const ws = new WebSocket(`${protocol}://${window.location.host}/logs`);
        const levels = {{ info: true, warning: true, error: true, debug: true }};
        const lines = [];

        const levelFromLine = (line) => {{
            const match = line.match(/\\[(INFO|WARNING|ERROR|DEBUG)\\]/i);
            return match ? match[1].toLowerCase() : 'info';
        }};

        const render = () => {{
            const filtered = lines.filter((line) => {{
                const lvl = levelFromLine(line);
                return levels[lvl] ?? true;
            }});
            log.textContent = filtered.join('\\n');
            log.scrollTop = log.scrollHeight;
        }};

        filters.forEach((checkbox) => {{
            checkbox.addEventListener('change', (event) => {{
                const level = event.target.dataset.level;
                levels[level] = event.target.checked;
                render();
            }});
        }});

        ws.addEventListener('message', (event) => {{
            lines.push(event.data);
            render();
        }});
    </script>
</body>
</html>
"""
        return template.replace('{brand_name}', BRAND_NAME)


# Expose class and instance for dynamic discovery
INTERFACE_CLASS = SynthWebUIInterface
synth_webui_interface = SynthWebUIInterface()


async def start_server() -> None:
    """Compatibility helper to run the SyntH Web UI server in the foreground."""
    if not synth_webui_interface.autostart:
        await synth_webui_interface._run_server()
        return

    # If autostart is enabled we already spawned the background server. Keep
    # the coroutine alive so ``uvicorn`` keeps running until interrupted.
    event = asyncio.Event()
    await event.wait()
