import json
import os
import socket
import subprocess
import sys
import threading
import time
import warnings
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

warnings.filterwarnings("ignore", message="Core Pydantic V1 functionality")
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# Globals

agent = None
# Per-session state – keyed by session_id (a UUID generated per browser tab)
sessions: dict[str, object] = {}
_stop_events: dict[str, threading.Event] = {}


# WinUI signal

def send_winui_signal(signal: str):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(("127.0.0.1", 8080))
            s.sendall(signal.encode('utf-8'))
    except (ConnectionRefusedError, socket.timeout):
        print(f"WinUI 3 app not found. Signal '{signal}' not sent.")
    except Exception as e:
        print(f"Error signaling WinUI: {e}")


# LangChain init (lazy, runs in background thread)

def init_langchain():
    global agent

    if agent is not None:
        return

    from langchain.agents import create_agent
    from langchain.tools import tool
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    def run(cmd: str) -> str:
        result = subprocess.run(cmd, shell=True, capture_output=True, encoding='utf-8', errors='replace')
        return result.stdout + (result.stderr if result.returncode != 0 else "")

    @tool("snapshot", description="Return interactive accessibility snapshot from agent-browser.")
    def snapshot() -> str:
        return run("agent-browser snapshot -i")

    @tool(
        "navigate",
        description=(
            "Control browser navigation using agent-browser commands. "
            "Supported commands:"
            "- 'agent-browser open <url>' → Navigate to a URL (aliases: goto, navigate)"
            "- 'agent-browser tab new <url>' -> Create New tab (url is optional)"
            "- 'agent-browser back' → Go to previous page"
            "- 'agent-browser forward' → Go to next page"
            "- 'agent-browser reload' → Reload the current page"
            "Example: agent-browser open https://youtube.com"
            "Example: agent-browser tab new https://youtube.com"
        )
    )
    def navigate(cmd: str) -> str:
        return run(cmd)

    @tool(
        "interact",
        description=(
            "Interact with webpage elements using agent-browser commands. "
            "Mouse actions: 'agent-browser click <selector>' to click (--new-tab to open in new tab), "
            "'agent-browser dblclick <selector>' to double-click, "
            "'agent-browser hover <selector>' to hover, "
            "'agent-browser drag <source_selector> <target_selector>' to drag and drop. "
            "Text input: 'agent-browser fill <selector> <text>' to clear and fill input, "
            "'agent-browser type <selector> <text>' to type into element, "
            "'agent-browser keyboard type <text>' to type at current focus, "
            "'agent-browser keyboard inserttext <text>' to insert text without key events, "
            "'agent-browser upload <selector> <file_paths>' to upload files. "
            "Keyboard actions: 'agent-browser press <key>' to press a key (Enter, Tab, Control+a), "
            "'agent-browser keydown <key>' to hold key down, "
            "'agent-browser keyup <key>' to release key. "
            "Form controls: 'agent-browser focus <selector>' to focus element, "
            "'agent-browser select <selector> <value>' to select dropdown option, "
            "'agent-browser check <selector>' to check checkbox, "
            "'agent-browser uncheck <selector>' to uncheck checkbox. "
            "Scrolling: 'agent-browser scroll <direction> [pixels]' to scroll (up/down/left/right, optional --selector), "
            "'agent-browser scrollintoview <selector>' to scroll element into view. "
            "Selectors must use the ref format: @e4, @e12, etc. (NOT [ref=e4]). "
            "Example: agent-browser click @e4"
        )
    )
    def interact(cmd: str) -> str:
        return run(cmd)

    SYSTEM_PROMPT = (
        "You are a helpful browser automation agent. "
        "You can navigate websites, interact with elements, and take snapshots. "
        "Always take a snapshot first to understand the current page state before interacting. "
        "When the whole task given by user completes just give response as Task Completed."
    )

    class ConversationMemory:
        def __init__(self, system_prompt: str = SYSTEM_PROMPT):
            self.history = [SystemMessage(content=system_prompt)]

        def add(self, role: str, content: str):
            if role == "user":
                self.history.append(HumanMessage(content=content))
            else:
                self.history.append(AIMessage(content=content))

        def get(self):
            return self.history

        def clear(self):
            self.history = [self.history[0]]

    # Store the class so endpoints can instantiate per-session copies
    init_langchain._ConversationMemory = ConversationMemory
    agent = create_agent("groq:openai/gpt-oss-120b", tools=[snapshot, navigate, interact])

# FastAPI app
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def startup_event():
    threading.Thread(target=init_langchain, daemon=True).start()


# Models
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class SessionRequest(BaseModel):
    session_id: str = "default"


# Streaming
def event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def stream_chat(user_input: str, session_id: str):
    """Stream a chat response for an isolated per-tab session."""
    # Wait until the agent (and ConversationMemory class) are ready
    while agent is None or not hasattr(init_langchain, "_ConversationMemory"):
        time.sleep(0.1)

    # Ensure this session has its own memory and stop-event
    if session_id not in sessions:
        sessions[session_id] = init_langchain._ConversationMemory()
    if session_id not in _stop_events:
        _stop_events[session_id] = threading.Event()

    memory = sessions[session_id]
    stop_event = _stop_events[session_id]

    stop_event.clear()
    memory.add("user", user_input)

    ai_reply = ""
    send_winui_signal("START")

    try:
        for step in agent.stream({"messages": memory.get()}, stream_mode="updates"):
            if stop_event.is_set():
                yield event({"type": "stopped", "content": "Task stopped by user."})
                break

            for node, update in step.items():
                for msg in update.get("messages", []):
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tc in msg.tool_calls:
                            yield event({"type": "tool_call", "name": tc["name"], "args": tc["args"]})

                    elif hasattr(msg, "name") and msg.name:
                        preview = (msg.content or "")[:400].replace("\n", " ")
                        yield event({"type": "tool_result", "name": msg.name, "preview": preview})

                    elif hasattr(msg, "content") and msg.content:
                        ai_reply = msg.content
                        yield event({"type": "ai_message", "content": ai_reply})

    except Exception as exc:
        yield event({"type": "error", "content": str(exc)})
    finally:
        send_winui_signal("STOP")

    memory.add("ai", ai_reply)
    yield event({"type": "done"})


# Routes
@app.post("/chat")
async def chat_endpoint(body: ChatRequest):
    user_input = body.message.strip()
    if not user_input:
        return {"error": "Empty message"}
    return StreamingResponse(
        stream_chat(user_input, body.session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/stop")
async def stop_task(body: SessionRequest):
    ev = _stop_events.get(body.session_id)
    if ev:
        ev.set()
    send_winui_signal("STOP")
    return {"status": "stopping"}


@app.post("/clear")
async def clear_memory(body: SessionRequest):
    mem = sessions.get(body.session_id)
    if mem is not None:
        mem.clear()
    return {"status": "cleared"}


@app.get("/status")
async def status(session_id: str = "default"):
    mem = sessions.get(session_id)
    msgs_len = len(mem.get()) if mem is not None else 1
    return {"status": "running", "messages": msgs_len}


@app.get("/context")
async def get_context(session_id: str = "default"):
    mem = sessions.get(session_id)
    if mem is None:
        return {"messages": []}

    msgs = mem.get()
    result = []
    for m in msgs:
        cls_name = m.__class__.__name__
        if cls_name == "SystemMessage":
            result.append({"role": "system", "content": m.content})
        elif cls_name == "HumanMessage":
            result.append({"role": "user", "content": m.content})
        elif cls_name == "AIMessage":
            result.append({"role": "ai", "content": m.content})
    return {"messages": result}


# Serve React frontend (built with `npm run build`)

_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file = _frontend_dist / full_path
        if file.is_file():
            return FileResponse(file)
        return FileResponse(_frontend_dist / "index.html")


# Entry point

if __name__ == "__main__":
    try:
        subprocess.Popen("agent-browser connect 9222", shell=True)
        uvicorn.run(app, host="0.0.0.0", port=5050)
    finally:
        send_winui_signal("STOP")