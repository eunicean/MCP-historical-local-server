import os
import anthropic
import json
import sys
import asyncio
from typing import List, Dict, Any
from datetime import datetime, timezone
from dotenv import load_dotenv, dotenv_values
from fastmcp import Client

load_dotenv()

LOG_PATH = "MCPchatlog.json"

API_KEY = os.getenv("APIKEY")
MODEL = "claude-3-haiku-20240307"
MAX_HISTORY_MESSAGES = 30 # mensajes de contexto

client = anthropic.Anthropic(api_key=API_KEY)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def load_logs(path: str = LOG_PATH) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Advertencia: no se pudo leer log ({e}), empezando log vacío.")
        return []

def save_logs(logs: List[Dict[str, Any]], path: str = LOG_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)

def append_log(entry: Dict[str, Any], path: str = LOG_PATH):
    logs = load_logs(path)
    logs.append(entry)
    save_logs(logs, path)

def build_history_from_logs(logs: List[Dict[str, Any]], max_messages: int = MAX_HISTORY_MESSAGES):
    msgs = []
    for e in [x for x in logs if x.get("role") in ("user", "assistant")]:
        msgs.append({"role": e["role"], "content": e["content"]})
    # mantener solo las últimas max_messages
    return msgs[-max_messages:]

def safe_extract_response_text(response) -> str:
    try:
        # response.content que puede ser str o lista/obj
        content = getattr(response, "content", None)
        if isinstance(content, str):
            return content
        # es lista de objetos
        if isinstance(content, (list, tuple)) and len(content) > 0:
            first = content[0]
            # .text o .content en el item
            if isinstance(first, dict):
                # busca claves conocidas
                for k in ("text", "content", "output_text"):
                    if k in first:
                        return first[k]
                return json.dumps(first)
            # si es objeto con attr .text
            if hasattr(first, "text"):
                return first.text
            return str(first)
        return str(response)
    except Exception:
        return str(response)

def send_to_claude(history: List[Dict[str,str]], user_input: str, model: str = MODEL, max_tokens: int = 1000) -> str:
    """
    Envía la conversación (history + user_input) a Claude y retorna el texto de respuesta.
    history: lista de {"role":"user"/"assistant", "content": "..."}
    """
    messages = history + [{"role": "user", "content": user_input}]
    try:
        resp = client.messages.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens
        )
    except Exception as e:
        raise RuntimeError(f"Error al llamar a la API de Anthropic: {e}")

    reply_text = safe_extract_response_text(resp)
    return reply_text

def show_history(history: List[Dict[str,str]]):
    print("---- CONTEXTO (últimos mensajes) ----")
    for m in history:
        role = m.get("role", "?")
        content = m.get("content", "")
        prefix = "Tú:" if role == "user" else "Claude:"
        print(f"{prefix} {content}")
    print("------------------------------------")

# MCP ----------------------------------------------------------
def serialize_mcp_result(result):
    """Convierte cualquier resultado de MCP en algo serializable JSON."""
    try:
        if hasattr(result, "structured_content") and result.structured_content is not None:
            return result.structured_content
        if hasattr(result, "content") and result.content is not None:
            return [str(c) for c in result.content]
        return str(result)
    except Exception as e:
        return {"error": str(e), "raw": str(result)}

async def run_tool(query: str):
    client = Client("historical_mcp.py")

    async with client:
        print("Sesión MCP abierta")

        result = await client.call_tool("find_event", {"title": query})
        response = result.structured_content if hasattr(result, "structured_content") else str(result)

        append_log({
            "time": now_iso(),
            "role": "MCP",
            "tool": "find_event",
            "request": {"title": query},
            "response": response
        })

        return response

# MCP ----------------------------------------------------------

async def main():
    logs = load_logs()
    history = build_history_from_logs(logs)

    print("Chatbot  historical mcp")
    print("Comandos: /history, /log, /clear, /find_event <query>, exit")

    while True:
        try:
            user_input = input("Tú: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSaliendo...")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            break

        if user_input == "/history":
            for h in history:
                role = "Tú" if h["role"] == "user" else "Claude"
                print(f"{role}: {h['content']}")
            continue
        if user_input == "/log":
            print(f"Log: {os.path.abspath(LOG_PATH)}")
            continue
        if user_input == "/clear":
            save_logs([])
            history = []
            print(" Log y contexto limpiados.")
            continue

        if user_input.startswith("/find_event"):
            query = user_input.replace("/find_event", "").strip()
            results = await run_tool(query)
            print("📚 Resultados:", results)
            continue

        append_log({"time": now_iso(), "role": "user", "content": user_input})
        history.append({"role": "user", "content": user_input})

        try:
            reply = send_to_claude(history, user_input)
        except RuntimeError as e:
            print(e)
            continue

        print("Claude:", reply)
        append_log({"time": now_iso(), "role": "assistant", "content": reply})
        history.append({"role": "assistant", "content": reply})

if __name__ == "__main__":
    asyncio.run(main())