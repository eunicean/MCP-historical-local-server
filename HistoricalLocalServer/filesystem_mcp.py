from mcp.server import FastMCP
import os

mcp = FastMCP("file_tools")

@mcp.tool()
async def list_dir(path: str = ".") -> list[str]:
    """List all files in a directory"""
    try:
        return os.listdir(path)
    except Exception as e:
        return [f"Error: {e}"]

@mcp.tool()
async def read_file(path: str) -> str:
    """Read the content of a file"""
    try:
        with open(path, "r") as f:
            return f.read()
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def write_file(path: str, content: str) -> str:
    """Write content to a file"""
    try:
        with open(path, "w") as f:
            f.write(content)
        return "File written successfully"
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    mcp.run(transport="stdio")