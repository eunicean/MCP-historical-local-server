# MCP historical local server
Un MCP que tiene herramientas para revisar una base de datos específica que contiene algunos eventos históricos

## Librerias necesarias
Uv
```
pip install uv
```
fastMCP
```
pip install fastmcp
```
pymongo
```
pip install pymongo
```


## Usar con Claude Desktop
Para descargar librerías necesarias para mcp:
```
py -m uv add "mcp[cli]"
```

Para instalar automaticamente el servidor sin tener que configurar el claude_desktop_config.json se necesita usar el comando:
```
py -m uv run mcp install historical_mcp.py
```

Después de esto solo hay que reiniciar Claude Desktop y el servidor aparecerá en la lista de Tools.