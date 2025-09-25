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

connectionString = "mongodb+srv://MCPonlyRead:123@wiwi.rbesc9b.mongodb.net/"
dbString = "history"
collectionString = "historical_events"

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
    
    # Si tenemos tanto título como tags, intentamos una búsqueda más inteligente
    if title and tags:
        # Primero intentamos con el título exacto
        query["title"] = {"$regex": title, "$options": "i"}
        docs = list(collection.find(query))
        
        # Si no encontramos resultados, intentamos con los tags
        if not docs:
            query = {"tags": {"$in": tags}}
            docs = list(collection.find(query))
            
            # Si aún no encontramos, intentamos con al menos 2 tags que coincidan
            if not docs:
                pipeline = [
                    {
                        "$match": {
                            "tags": {"$in": tags}
                        }
                    },
                    {
                        "$addFields": {
                            "matching_tags": {
                                "$size": {
                                    "$setIntersection": ["$tags", tags]
                                }
                            }
                        }
                    },
                    {
                        "$match": {
                            "matching_tags": {"$gte": 2}
                        }
                    }
                ]
                docs = list(collection.aggregate(pipeline))
    
    # Si solo tenemos título
    elif title:
        query["title"] = {"$regex": title, "$options": "i"}
        docs = list(collection.find(query))
        
        # Si no encontramos por título, intentamos buscar palabras clave del título como tags
        if not docs:
            # Extraemos palabras clave del título (excluyendo palabras comunes)
            stop_words = {"de", "del", "la", "el", "los", "las", "y", "en", "a", "con"}
            title_words = [word.lower() for word in title.split() if word.lower() not in stop_words and len(word) > 3]
            
            if title_words:
                query = {"tags": {"$in": title_words}}
                docs = list(collection.find(query))
                
                # Si aún no encontramos, intentamos con al menos 2 tags que coincidan
                if not docs:
                    pipeline = [
                        {
                            "$match": {
                                "tags": {"$in": title_words}
                            }
                        },
                        {
                            "$addFields": {
                                "matching_tags": {
                                    "$size": {
                                        "$setIntersection": ["$tags", title_words]
                                    }
                                }
                            }
                        },
                        {
                            "$match": {
                                "matching_tags": {"$gte": 2}
                            }
                        }
                    ]
                    docs = list(collection.aggregate(pipeline))
    
    # Si solo tenemos tags
    elif tags:
        # Primero intentamos con cualquier tag que coincida
        query["tags"] = {"$in": tags}
        docs = list(collection.find(query))
        
        # Si no encontramos o queremos más precisión, buscamos con al menos 2 tags que coincidan
        if not docs:
            pipeline = [
                {
                    "$match": {
                        "tags": {"$in": tags}
                    }
                },
                {
                    "$addFields": {
                        "matching_tags": {
                            "$size": {
                                "$setIntersection": ["$tags", tags]
                            }
                        }
                    }
                },
                {
                    "$match": {
                        "matching_tags": {"$gte": 2}
                    }
                }
            ]
            docs = list(collection.aggregate(pipeline))
    
    # Si tenemos fecha
    elif date:
        query["date"] = date
        docs = list(collection.find(query))
    
    else:
        docs = []

    try:
        for doc in docs:
            doc["_id"] = str(doc["_id"])  # convertir ObjectId → str
        return docs
    except Exception as e:
        raise ToolError(f"Error en find_event: {e}")
    

if __name__ == "__main__":
    print("corriendo server")
    mcp.run()