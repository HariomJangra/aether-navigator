"""
FastAPI backend for the ReAct Agent.
Streams agent thought/tool steps via Server-Sent Events (SSE).
"""

import subprocess
import json
import sys
import os
import threading
import uvicorn
import socket
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

import warnings
warnings.filterwarnings("ignore", message="Core Pydantic V1 functionality")


# ── load .env (GROQ_API_KEY etc.)
load_dotenv()

# ── absolute path so imports resolve regardless of cwd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── LangChain imports
from langchain.agents import create_agent          
from langchain.tools import tool                   
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# ── Browser command Runner
def run(cmd: str) -> str:
    result = subprocess.run(cmd, shell=True, capture_output=True, encoding='utf-8', errors='replace')
    return result.stdout + (result.stderr if result.returncode != 0 else "")


# ── Tool definitions
@tool(
    "snapshot",
    description="Return interactive accessibility snapshot from agent-browser.")
def snapshot() -> str:
    result = run("agent-browser snapshot -i") 
    return result
    

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
    result = run(cmd)
    return result

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
    result = run(cmd)
    return result


# ── System prompt & memory
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


memory = ConversationMemory()

# ── Stop flag
_stop_event = threading.Event()

# ── Agent
agent = create_agent("groq:openai/gpt-oss-120b", tools=[snapshot, navigate, interact])


# ── FastAPI app
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ChatRequest(BaseModel):
    message: str


def event(payload: dict) -> str:
    """Format a dict as a single SSE data line."""
    return f"data: {json.dumps(payload)}\n\n"


def stream_chat(user_input: str):
    """Generator: yields SSE events while the agent is running."""
    _stop_event.clear()
    memory.add("user", user_input)

    ai_reply = ""
    send_winui_signal("START")

    try:
        for step in agent.stream({"messages": memory.get()}, stream_mode="updates"):
            if _stop_event.is_set():
                yield event({"type": "stopped", "content": "Task stopped by user."})
                break
            for node, update in step.items():
                for msg in update.get("messages", []):
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tc in msg.tool_calls:
                            yield event({
                                "type": "tool_call",
                                "name": tc["name"],
                                "args": tc["args"],
                            })

                    elif hasattr(msg, "name") and msg.name:
                        preview = (msg.content or "")[:400].replace("\n", " ")
                        yield event({
                            "type": "tool_result",
                            "name": msg.name,
                            "preview": preview,
                        })

                    elif hasattr(msg, "content") and msg.content:
                        ai_reply = msg.content
                        yield event({"type": "ai_message", "content": ai_reply})

    except Exception as exc:
        yield event({"type": "error", "content": str(exc)})
    finally:
        send_winui_signal("STOP")

    memory.add("ai", ai_reply)
    yield event({"type": "done"})


# ── Routes
@app.post("/chat")
async def chat_endpoint(body: ChatRequest):
    user_input = body.message.strip()
    if not user_input:
        return {"error": "Empty message"}

    return StreamingResponse(
        stream_chat(user_input),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/stop")
async def stop_task():
    _stop_event.set()
    send_winui_signal("STOP")
    return {"status": "stopping"}


@app.post("/clear")
async def clear_memory():
    memory.clear()
    return {"status": "cleared"}


@app.get("/status")
async def status():
    return {"status": "running", "messages": len(memory.get())}


@app.get("/context")
async def get_context():
    """Return the conversation history (excluding the system message)."""
    msgs = memory.get()
    result = []
    for m in msgs:
        if isinstance(m, SystemMessage):
            result.append({"role": "system", "content": m.content})
        elif isinstance(m, HumanMessage):
            result.append({"role": "user", "content": m.content})
        elif isinstance(m, AIMessage):
            result.append({"role": "ai", "content": m.content})
    return {"messages": result}


# ── Serve React frontend (built with `npm run build`)
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file = _frontend_dist / full_path
        if file.is_file():
            return FileResponse(file)
        return FileResponse(_frontend_dist / "index.html")

def send_winui_signal(signal: str):
    """Sends a raw TCP string to the WinUI 3 listener on port 8080."""
    try:
        # We use AF_INET (IPv4) and SOCK_STREAM (TCP)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)  # Don't let it hang if the app isn't open
            s.connect(("127.0.0.1", 8080))
            s.sendall(signal.encode('utf-8'))
    except (ConnectionRefusedError, socket.timeout):
        # This is expected if the WinUI app is closed
        print(f"WinUI 3 app not found. Signal '{signal}' not sent.")
    except Exception as e:
        print(f"Error signaling WinUI: {e}")

if __name__ == "__main__":
    try:
        # 2. Launch your browser connection
        subprocess.Popen("agent-browser connect 9222", shell=True)
        
        # 3. Start the FastAPI server
        # Note: This is a blocking call
        uvicorn.run(app, host="0.0.0.0", port=5050)
        
    finally:
        # 4. This runs when uvicorn stops (Ctrl+C or shutdown)
        # Trigger StopGlow() in WinUI
        send_winui_signal("STOP")
