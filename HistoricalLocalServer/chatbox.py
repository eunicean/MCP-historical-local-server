import os
import anthropic
import json
import sys
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from dotenv import load_dotenv
from fastmcp import Client

load_dotenv()

LOG_PATH = "MCPchatlog.json"
API_KEY = os.getenv("APIKEY")
MODEL = "claude-3-haiku-20240307"
MAX_HISTORY_MESSAGES = 30

client = anthropic.Anthropic(api_key=API_KEY)

MCP_SERVERS = {
    "history": "historical_mcp.py",
    "filesystem": "filesystem_mcp.py"
}

class MCPServerManager:
    def __init__(self):
        self.clients = {}
        self.tools = []
        self.available_servers = {}

    async def start_server(self, server_name: str, script_path: str):
        if not os.path.exists(script_path):
            print(f"- No se encuentra el script {script_path} para el servidor {server_name}")
            return False

        try:
            mcp_client = Client(script_path)
            self.clients[server_name] = mcp_client
            self.available_servers[server_name] = script_path

            async with mcp_client:
                tools_list = await mcp_client.list_tools()
                for tool in tools_list:
                    # Crear tool en formato Anthropic
                    anthropic_tool = {
                        "name": f"{server_name}_{tool.name}",
                        "description": tool.description,
                        "input_schema": {
                            "type": "object",
                            "properties": tool.input_schema if hasattr(tool, 'input_schema') else {},
                            "required": []
                        }
                    }
                    self.tools.append(anthropic_tool)

            print(f"☆ Servidor {server_name} conectado con herramientas: {[tool.name for tool in tools_list]}")
            return True

        except Exception as e:
            print(f"- Error al conectar con el servidor {server_name}: {e}")
            return False

    async def start_all_servers(self):
        tasks = []
        for server_name, script_path in MCP_SERVERS.items():
            tasks.append(self.start_server(server_name, script_path))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return any(results)

    async def call_tool(self, tool_name: str, arguments: Dict) -> Any:
        if "_" in tool_name:
            server_name, original_tool_name = tool_name.split("_", 1)
        else:
            # Si no tiene prefix, buscar en todos los servidores
            for server in self.clients.keys():
                async with self.clients[server]:
                    tools_list = await self.clients[server].list_tools()
                    if any(tool.name == tool_name for tool in tools_list):
                        server_name = server
                        original_tool_name = tool_name
                        break
            else:
                raise ValueError(f"Herramienta no encontrada: {tool_name}")

        if server_name not in self.clients:
            raise ValueError(f"Servidor {server_name} no está conectado")

        client = self.clients[server_name]
        
        async with client:
            result = await client.call_tool(original_tool_name, arguments)
            
            if hasattr(result, 'structured_content'):
                response_data = result.structured_content
            else:
                response_data = getattr(result, 'content', str(result))
            
            return response_data

    def get_anthropic_tools(self):
        return self.tools

    async def close(self):
        for client in self.clients.values():
            await client.close()
        print("✴ Todas las conexiones MCP cerradas")

# Instancia global del gestor de servidores MCP
mcp_manager = MCPServerManager()

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
        if isinstance(e["content"], str):
            msgs.append({"role": e["role"], "content": e["content"]})
        else:
            msgs.append(e)
    return msgs[-max_messages:]

def safe_extract_response_text(response) -> str:
    try:
        content = getattr(response, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, (list, tuple)) and len(content) > 0:
            first = content[0]
            if isinstance(first, dict):
                for k in ("text", "content", "output_text"):
                    if k in first:
                        return first[k]
                return json.dumps(first)
            if hasattr(first, "text"):
                return first.text
            return str(first)
        return str(response)
    except Exception:
        return str(response)

async def process_with_claude(messages: List[Dict], tools: List[Dict] = None, max_tokens: int = 1000) -> Dict:
    try:
        if tools:
            response = client.messages.create(
                model=MODEL,
                messages=messages,
                tools=tools,
                max_tokens=max_tokens
            )
        else:
            response = client.messages.create(
                model=MODEL,
                messages=messages,
                max_tokens=max_tokens
            )
        return response
    except Exception as e:
        raise RuntimeError(f"Error al llamar a la API de Anthropic: {e}")

async def handle_tool_calls(response, messages: List[Dict]) -> str:
    final_response = ""
    tool_use_detected = False

    for content in response.content:
        if content.type == "text":
            final_response += content.text + "\n"
            messages.append({
                "role": "assistant",
                "content": content.text,
            })
        elif content.type == "tool_use":
            tool_use_detected = True
            tool_name = content.name
            tool_args = content.input

            print(f"Claude quiere usar herramienta: {tool_name}")
            print(f"Argumentos: {tool_args}")

            messages.append({
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": content.id,
                    "name": tool_name,
                    "input": tool_args
                }]
            })

            try:
                # Ejecutar la herramienta
                tool_result = await mcp_manager.call_tool(tool_name, tool_args)
                result_content = str(tool_result) if not isinstance(tool_result, str) else tool_result

                print(f"✮ Resultado de {tool_name}: {result_content[:100]}...")

                # Añadir tool result al historial
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": content.id,
                        "content": result_content
                    }]
                })

                final_response += f"[Usada herramienta: {tool_name}]\n"

            except Exception as e:
                error_msg = f"Error ejecutando {tool_name}: {str(e)}"
                print(f"- {error_msg}")

                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": content.id,
                        "content": error_msg,
                        "is_error": True
                    }]
                })

                final_response += f"[Error con herramienta {tool_name}]\n"

    return final_response, tool_use_detected

async def main():
    print("☆ Iniciando servidores MCP...")
    success = await mcp_manager.start_all_servers()
    
    if not success:
        print("- No se pudo conectar a ningún servidor MCP")
        return
    
    logs = load_logs()
    history = build_history_from_logs(logs)

    anthropic_tools = mcp_manager.get_anthropic_tools()

    print("\nChatbot Multi-MCP con Herramientas Automáticas")
    print("Servidores conectados:", list(mcp_manager.available_servers.keys()))
    print("Herramientas disponibles:", [tool['name'] for tool in anthropic_tools])
    print("\nComandos: /history, /log, /clear, /tools, /servers, exit")

    while True:
        try:
            user_input = input("\nTú: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n Saliendo...")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            break

        if user_input == "/history":
            for i, h in enumerate(history[-10:], 1):
                role = "Tú" if h["role"] == "user" else "Claude"
                content_preview = h["content"][:100] + "..." if len(str(h["content"])) > 100 else h["content"]
                print(f"{i}. {role}: {content_preview}")
            continue
        
        if user_input == "/log":
            print(f" Log: {os.path.abspath(LOG_PATH)}")
            continue
        
        if user_input == "/clear":
            save_logs([])
            history = []
            print("☆ Log y contexto limpiados.")
            continue
        
        if user_input == "/tools":
            print("\n  Herramientas disponibles:")
            for tool in anthropic_tools:
                print(f"  • {tool['name']}: {tool['description']}")
            continue
        
        if user_input == "/servers":
            print("\n Servidores conectados:")
            for server, path in mcp_manager.available_servers.items():
                print(f"  • {server}: {path}")
            continue

        user_message = {"role": "user", "content": user_input}
        history.append(user_message)
        append_log({"time": now_iso(), "role": "user", "content": user_input})

        try:
            max_iterations = 8
            iteration = 0
            final_response = ""

            while iteration < max_iterations:
                iteration += 1
                print(f" Iteración {iteration}")

                response = await process_with_claude(history, anthropic_tools if anthropic_tools else None)
                
                iteration_response, tool_used = await handle_tool_calls(response, history)
                final_response += iteration_response

                if not tool_used:
                    break

                if iteration == max_iterations:
                    final_response += "\n Límite de iteraciones alcanzado."

            print("Claude:", final_response)
            
            history.append({"role": "assistant", "content": final_response})
            append_log({"time": now_iso(), "role": "assistant", "content": final_response})
            
        except Exception as e:
            error_msg = f"Error: {e}"
            print(error_msg)
            history.append({"role": "assistant", "content": error_msg})
            append_log({"time": now_iso(), "role": "system", "content": error_msg})

    await mcp_manager.close()

if __name__ == "__main__":
    
    for server_name, script_path in MCP_SERVERS.items():
        if not os.path.exists(script_path):
            print(f"- Error: {script_path} no encontrado para servidor {server_name}")
            exit(1)
    
    asyncio.run(main())