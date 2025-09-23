from mcp.server.fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from typing import List, Optional, Dict, Any

import json
import sys
import os
from pymongo import MongoClient
from dotenv import load_dotenv, dotenv_values

# name for the MCP server
mcp = FastMCP(name="HistoryClass")

load_dotenv()

connectionString = os.getenv("CONNECTION_STRING")
dbString = os.getenv("MONGODATABASE")
collectionString = os.getenv("MONGOCOLLECTION")

client = MongoClient(connectionString)
db = client[dbString]
collection = db[collectionString]

@mcp.tool()
def find_event(
    title: Optional[str] = None,
    tags: Optional[List[str]] = None,
    date: Optional[str] = None
) -> List[Dict[str,Any]]:
    query = {}
    if title:
        query["title"] = {"$regex": title, "$options": "i"}
    if tags:
        query["tags"] = {"$in": tags}
    if date:
        query["date"] = date

    try:
        docs = list(collection.find(query))
        for doc in docs:
            doc["_id"] = str(doc["_id"])  # convertir ObjectId → str
        return docs
    except Exception as e:
        raise ToolError(f"Error en find_event: {e}")
    

if __name__ == "__main__":
    print("corriendo server")
    mcp.run()