"""Simple Web UI interface for Rekku Freedom Project.

Provides a chat-like interface running on FastAPI with WebSocket support.
- Only English language supported for now.
- Chat shows Rekku image on the right.
- Includes settings page to configure basic options.
- Offers dark and light themes and responsive layout.
- Exposes log stream and basic runtime statistics pages.
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from datetime import datetime
from pathlib import Path

try:  # Optional dependency for system statistics
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional
    psutil = None

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from core.logging_utils import (
    log_info,
    log_warning,
    log_error,
    log_debug,
    _LOG_FILE,
)
from core.core_initializer import register_interface
import core.plugin_instance as plugin_instance


class WebUIInterface:
    """Web-based chat interface."""

    def __init__(self) -> None:
        self.app = FastAPI()
        self.connections: dict[str, WebSocket] = {}
        self.start_time = datetime.utcnow()

        # Serve static files (logo etc.)
        static_dir = Path(__file__).resolve().parent.parent / "docs" / "res"
        self.app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        # Routes
        self.app.get("/")(self.index)
        self.app.get("/settings")(self.settings_page)
        self.app.get("/logs")(self.logs_page)
        self.app.get("/stats")(self.stats_page)
        self.app.get("/stats/data")(self.stats_data)
        self.app.websocket("/ws")(self.websocket_endpoint)
        self.app.websocket("/logs/ws")(self.logs_ws_endpoint)

        register_interface("webui", self)
        log_info("[webui] Web UI interface registered")

    # ------------------------------------------------------------------
    # Interface metadata
    # ------------------------------------------------------------------
    @staticmethod
    def get_interface_id() -> str:  # pragma: no cover - used by action parser
        return "webui"

    @staticmethod
    def get_supported_actions() -> dict:
        return {
            "message_webui": {
                "required_fields": ["text", "target"],
                "optional_fields": [],
                "description": "Send a text message to a WebUI session.",
            }
        }

    @staticmethod
    def get_prompt_instructions(action_name: str) -> dict:
        if action_name == "message_webui":
            return {
                "description": "Send a message to the Web UI interface.",
                "payload": {
                    "text": {"type": "string", "example": "Hello!", "description": "Message text"},
                    "target": {
                        "type": "string",
                        "example": "session-id",
                        "description": "Web UI session identifier",
                    },
                },
            }
        return {}

    @staticmethod
    def get_interface_instructions() -> str:
        return (
            "Use interface: webui to converse through the browser. "
            "Target represents the session identifier received from the WebSocket connection."
        )

    # ------------------------------------------------------------------
    # FastAPI handlers
    # ------------------------------------------------------------------
    async def index(self):  # pragma: no cover - HTTP response
        """Return main chat page."""
        html = self._build_chat_html()
        return HTMLResponse(html)

    async def settings_page(self):  # pragma: no cover - HTTP response
        html = self._build_settings_html()
        return HTMLResponse(html)

    async def logs_page(self):  # pragma: no cover - HTTP response
        html = self._build_logs_html()
        return HTMLResponse(html)

    async def stats_page(self):  # pragma: no cover - HTTP response
        html = self._build_stats_html()
        return HTMLResponse(html)

    async def stats_data(self):
        uptime = int((datetime.utcnow() - self.start_time).total_seconds())
        memory_mb = 0.0
        if psutil:  # pragma: no cover - psutil optional
            proc = psutil.Process()
            memory_mb = proc.memory_info().rss / (1024 * 1024)
        return {"uptime": uptime, "memory_mb": round(memory_mb, 2)}

    async def logs_ws_endpoint(self, websocket: WebSocket):  # pragma: no cover - runtime
        await websocket.accept()
        path = Path(_LOG_FILE)
        try:
            if not path.exists():
                await websocket.send_text("Log file not found")
                return
            with path.open() as f:
                lines = f.readlines()[-100:]
                for line in lines:
                    await websocket.send_text(line.rstrip())
                while True:
                    line = f.readline()
                    if line:
                        await websocket.send_text(line.rstrip())
                    else:
                        await asyncio.sleep(1)
        except Exception as e:  # pragma: no cover - runtime errors
            log_error(f"[webui] log stream error: {e}")
        finally:
            await websocket.close()

    async def websocket_endpoint(self, websocket: WebSocket):  # pragma: no cover - runtime
        await websocket.accept()
        session_id = str(uuid.uuid4())
        self.connections[session_id] = websocket
        await websocket.send_json({"type": "session", "session_id": session_id})
        log_info(f"[webui] client connected: {session_id}")
        try:
            while True:
                data = await websocket.receive_json()
                text = data.get("text", "").strip()
                if not text:
                    continue
                await self._handle_user_message(session_id, text)
        except WebSocketDisconnect:
            self.connections.pop(session_id, None)
            log_info(f"[webui] client disconnected: {session_id}")

    async def _handle_user_message(self, session_id: str, text: str) -> None:
        """Forward user message to the LLM plugin."""
        # Build synthetic message similar to Telegram's update.message
        message = SimpleNamespace(
            chat_id=session_id,
            message_id=int(datetime.utcnow().timestamp() * 1000) % 1_000_000,
            text=text,
            date=datetime.utcnow(),
            from_user=SimpleNamespace(id=session_id, username=f"webui_{session_id[:8]}", first_name="WebUser"),
            chat=SimpleNamespace(id=session_id, type="web"),
            reply_to_message=None,
        )
        log_debug(f"[webui] message from {session_id}: {text}")
        try:
            response = await plugin_instance.handle_incoming_message(self, message, {})
            if response and session_id in self.connections:
                await self.connections[session_id].send_json(
                    {"type": "message", "sender": "rekku", "text": response}
                )
        except Exception as e:  # pragma: no cover - runtime errors
            log_error(f"[webui] error handling message: {e}")

    # ------------------------------------------------------------------
    # Methods used by plugins or action parser
    # ------------------------------------------------------------------
    async def send_message(self, payload_or_chat_id=None, text: str | None = None, **kwargs):
        """Send message to a connected session.

        Supports two calling styles:
        - send_message(payload_dict)
        - send_message(chat_id=..., text="...")
        """
        if isinstance(payload_or_chat_id, dict):
            payload = payload_or_chat_id
            text = payload.get("text", text)
            chat_id = payload.get("target") or payload.get("chat_id")
        else:
            chat_id = payload_or_chat_id or kwargs.get("chat_id")
            if text is None:
                text = kwargs.get("text")

        if not text or chat_id is None:
            log_warning("[webui] send_message missing text or chat_id")
            return

        ws = self.connections.get(str(chat_id))
        if ws:
            await ws.send_json({"type": "message", "sender": "rekku", "text": text})
        else:
            log_warning(f"[webui] no active connection for {chat_id}")

    async def execute_action(self, action: dict, context: dict, bot, original_message):
        """Execute actions forwarded from the action parser."""
        if action.get("type") == "message_webui":
            payload = action.get("payload", {})
            await self.send_message(payload, original_message=original_message)

    # ------------------------------------------------------------------
    # HTML builders
    # ------------------------------------------------------------------
    def _build_chat_html(self) -> str:
        logo = "/static/RFP_logo.png"
        return f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"UTF-8\" />
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
<title>Rekku WebUI</title>
<style>
body {{ margin:0; font-family: sans-serif; background: var(--bg); color: var(--fg); }}
:root.light {{ --bg:#ffffff; --fg:#000000; --bubble-user:#e0e0e0; --bubble-rekku:#4a90e2; }}
:root.dark {{ --bg:#121212; --fg:#ffffff; --bubble-user:#333333; --bubble-rekku:#4a90e2; }}
#chat {{ display:flex; flex-direction:column; height:90vh; padding:10px; overflow-y:auto; }}
.message {{ padding:8px; margin:4px; border-radius:8px; max-width:70%; }}
.user {{ background:var(--bubble-user); align-self:flex-start; }}
.rekku {{ background:var(--bubble-rekku); color:white; align-self:flex-end; position:relative; }}
.rekku img {{ position:absolute; right:-50px; top:0; width:40px; height:40px; }}
#input-area {{ display:flex; gap:4px; padding:10px; }}
#input-area input {{ flex:1; padding:8px; }}
#input-area button {{ padding:8px; }}
.nav {{ padding:8px; background:var(--bubble-user); display:flex; gap:10px; }}
@media (max-width:600px) {{ .rekku img {{ display:none; }} }}
</style>
</head>
<body class=\"light\" id=\"body\">
<div class=\"nav\">
 <a href=\"/settings\">Settings</a>
 <a href=\"/logs\">Logs</a>
 <a href=\"/stats\">Stats</a>
 <a href=\"https://github.com/RetroDECK/Rekku_Freedom_Project/wiki\" target=\"_blank\">Wiki</a>
 <a href=\"https://github.com/RetroDECK/Rekku_Freedom_Project\" target=\"_blank\">Project</a>
 <a href=\"https://retrodeck.net\" target=\"_blank\">RetroDeck</a>
 <button onclick=\"toggleTheme()\">Toggle theme</button>
</div>
<div id=\"chat\"></div>
<div id=\"input-area\">
 <input id=\"msg\" placeholder=\"Type your message...\" />
 <button onclick=\"sendMsg()\">Send</button>
</div>
<script>
let ws = new WebSocket(`ws://${{location.host}}/ws`);
let sessionId = null;
ws.onmessage = (ev) => {{
  const data = JSON.parse(ev.data);
  if(data.type === 'session') sessionId = data.session_id;
  if(data.type === 'message') addMessage(data.sender, data.text);
}};
function addMessage(sender, text) {{
  const div = document.createElement('div');
  div.className = 'message ' + (sender === 'rekku' ? 'rekku' : 'user');
  div.textContent = text;
  if(sender === 'rekku') {{
    const img = document.createElement('img');
    img.src = '{logo}';
    div.appendChild(img);
  }}
  document.getElementById('chat').appendChild(div);
  div.scrollIntoView();
}}
function sendMsg() {{
  const input = document.getElementById('msg');
  const text = input.value.trim();
  if(!text) return;
  addMessage('user', text);
  ws.send(JSON.stringify({{text:text}}));
  input.value='';
}}
function toggleTheme() {{
  const body = document.getElementById('body');
  body.className = body.className === 'light' ? 'dark' : 'light';
}}
</script>
</body>
</html>
"""

    def _build_settings_html(self) -> str:
        return """
<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"UTF-8\" />
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
<title>Settings</title>
<style>
body {{ font-family: sans-serif; padding:20px; }}
label {{ display:block; margin-bottom:8px; }}
</style>
</head>
<body>
<h2>Settings</h2>
<label>Language
 <select disabled>
  <option>English</option>
 </select>
</label>
<label>Dark Mode <input type=\"checkbox\" onclick=\"alert('Use the toggle in main page')\" /></label>
<label>LLM Mode
 <select id=\"llm\">
  <option>manual</option>
  <option>openai</option>
 </select>
</label>
<p><a href=\"/\">Back to chat</a></p>
</body>
</html>
"""

    def _build_logs_html(self) -> str:
        return """
<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"UTF-8\" />
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
<title>Logs</title>
<style>
body {{ font-family: monospace; background:#000; color:#0f0; margin:0; }}
#log {{ white-space:pre-wrap; padding:10px; height:90vh; overflow-y:auto; }}
.nav {{ padding:8px; background:#222; }}
.nav a {{ color:#0f0; margin-right:10px; }}
</style>
</head>
<body>
<div class=\"nav\"><a href=\"/\">Back to chat</a></div>
<div id=\"log\"></div>
<script>
let ws = new WebSocket(`ws://${location.host}/logs/ws`);
ws.onmessage = (ev) => {{
  const logDiv = document.getElementById('log');
  logDiv.textContent += ev.data + '\n';
  logDiv.scrollTop = logDiv.scrollHeight;
}};
</script>
</body>
</html>
"""

    def _build_stats_html(self) -> str:
        return """
<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"UTF-8\" />
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
<title>Stats</title>
<style>
body {{ font-family: sans-serif; padding:20px; }}
#stats {{ margin-top:20px; }}
</style>
</head>
<body>
<h2>Runtime statistics</h2>
<div id=\"stats\"></div>
<script>
async function load() {{
  const res = await fetch('/stats/data');
  const data = await res.json();
  document.getElementById('stats').innerHTML = `Uptime: ${data.uptime}s<br/>Memory: ${data.memory_mb} MB`;
}}
setInterval(load, 1000);
load();
</script>
<p><a href=\"/\">Back to chat</a></p>
</body>
</html>
"""


# Expose class for dynamic loading and register instance
INTERFACE_CLASS = WebUIInterface
webui_interface = WebUIInterface()
