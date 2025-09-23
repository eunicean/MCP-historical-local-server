import os
import anthropic
import json
import sys
from typing import List, Dict, Any
from datetime import datetime
from dotenv import load_dotenv, dotenv_values

load_dotenv()

LOG_PATH = "MCPchatlog.json"

API_KEY = os.getenv("APIKEY")
if not API_KEY:
    print("Error: no se encontró la API key. Define APIKEY en .env (o ANTHROPIC_API_KEY).")
    sys.exit(1)

MODEL = "claude-3-haiku-20240307"
MAX_HISTORY_MESSAGES = 30 # mensajes de contexto

client = anthropic.Anthropic(api_key=API_KEY)

def now_iso():
    return datetime.utcnow().isoformat() + "Z"

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
    # Selecciona solo entradas con role user/assistant
    for e in [x for x in logs if x.get("role") in ("user", "assistant")]:
        msgs.append({"role": e["role"], "content": e["content"]})
    # Mantener solo las últimas max_messages
    return msgs[-max_messages:]

def safe_extract_response_text(response) -> str:
    try:
        # response.content que puede ser str o lista/obj
        content = getattr(response, "content", None)
        if isinstance(content, str):
            return content
        # si es lista de objetos
        if isinstance(content, (list, tuple)) and len(content) > 0:
            first = content[0]
            # varios SDKs usan .text ó .content en el item
            if isinstance(first, dict):
                # busca claves conocidas
                for k in ("text", "content", "output_text"):
                    if k in first:
                        return first[k]
                # fallback
                return json.dumps(first)
            # si es objeto con attr .text
            if hasattr(first, "text"):
                return first.text
            return str(first)
        # fallback último recurso
        return str(response)
    except Exception:
        return str(response)

def send_to_claude(history: List[Dict[str,str]], user_input: str, model: str = MODEL, max_tokens: int = 1000) -> str:
    """
    Envía la conversación (history + user_input) a Claude y retorna el texto de respuesta.
    history: lista de {"role":"user"/"assistant", "content": "..."}
    """
    # construir mensajes: usar el historial ya existente y añadir el nuevo user message al final
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
    print("---- contexto (últimos mensajes) ----")
    for m in history:
        role = m.get("role", "?")
        content = m.get("content", "")
        prefix = "Tú:" if role == "user" else "Claude:"
        print(f"{prefix} {content}")
    print("------------------------------------")

def main():
    logs = load_logs()
    history = build_history_from_logs(logs)

    print("Chatbot con Claude (Punto 1). Escribe 'exit' para salir.")
    print("Comandos especiales: /history (ver contexto), /log (abrir archivo de log), /clear (limpiar contexto actual y log).")
    while True:
        try:
            user_input = input("Tú: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSaliendo...")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("Adiós.")
            break

        if user_input == "/history":
            show_history(history)
            continue
        if user_input == "/log":
            print(f"Log guardado en: {os.path.abspath(LOG_PATH)}")
            continue
        if user_input == "/clear":
            confirm = input("¿Seguro? Esto borrará el log en disco y el contexto actual. (s/N): ").strip().lower()
            if confirm == "s":
                save_logs([])
                history = []
                print("Contexto y log limpiados.")
            continue

        # Log de la entrada del usuario
        entry_user = {"time": now_iso(), "role": "user", "content": user_input, "meta": {}}
        append_log(entry_user)
        history.append({"role": "user", "content": user_input})

        try:
            reply = send_to_claude(history, user_input)
        except RuntimeError as e:
            print(f"[ERROR] {e}")
            # Guardar error en log
            append_log({"time": now_iso(), "role": "assistant", "content": f"ERROR: {e}", "meta": {"error": True}})
            continue

        # Mostrar y loggear la respuesta
        print("Claude:", reply)
        entry_assistant = {"time": now_iso(), "role": "assistant", "content": reply, "meta": {"model": MODEL}}
        append_log(entry_assistant)
        history.append({"role": "assistant", "content": reply})

        # Mantener el tamaño del contexto (por mensajes)
        if len(history) > MAX_HISTORY_MESSAGES:
            history = history[-MAX_HISTORY_MESSAGES:]

if __name__ == "__main__":
    main()