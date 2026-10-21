import os
import sqlite3
import logging
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("legal_mcp_server")

app = FastAPI(title="Legal MCP Server", version="1.0.0")

DB_PATH = os.path.join(os.path.dirname(__file__), "legal_db.sqlite")

class JSONRPCRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Optional[Any] = None

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Helper function: score and search law articles using keywords
def query_db_search(query_text: str, law_name: Optional[str] = None) -> List[Dict[str, Any]]:
    # Split query into words, removing very short ones
    words = [w.strip().lower() for w in query_text.replace(",", " ").replace(".", " ").split() if len(w.strip()) >= 2]
    if not words:
        return []
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Simple base fetch
    if law_name:
        cursor.execute("SELECT law_name, article_number, article_title, content, tags FROM laws WHERE law_name = ?", (law_name,))
    else:
        cursor.execute("SELECT law_name, article_number, article_title, content, tags FROM laws")
        
    rows = cursor.fetchall()
    conn.close()
    
    scored_results = []
    query_lower = query_text.lower().strip()
    
    for row in rows:
        content = row["content"].lower()
        tags = (row["tags"] or "").lower()
        title = row["article_title"].lower()
        art_num = row["article_number"].lower()
        
        # Calculate matching score
        score = 0
        
        # Phrase match boosts
        if query_lower in title:
            score += 20
        if query_lower in tags:
            score += 15
        if query_lower in content:
            score += 10
            
        for word in words:
            # tag matches are highly relevant (check exact tag match to avoid substring bugs)
            tag_list = [t.strip() for t in tags.split(",")]
            if word in tag_list:
                score += 5
            # article number/title matches are very relevant
            if word in art_num or word in title:
                score += 3
            # content matches
            if word in content:
                score += 1
                
        if score > 0:
            scored_results.append({
                "law_name": row["law_name"],
                "article_number": row["article_number"],
                "article_title": row["article_title"],
                "content": row["content"],
                "score": score
            })
            
    # Sort by score descending
    scored_results.sort(key=lambda x: x["score"], reverse=True)
    return scored_results[:5]  # return top 5 matches

@app.get("/health")
def health():
    exists = os.path.exists(DB_PATH)
    return {"status": "healthy" if exists else "unhealthy", "db_exists": exists}

@app.post("/rpc")
async def handle_rpc(payload: JSONRPCRequest):
    logger.info(f"Received MCP RPC Call: {payload.method}")
    method = payload.method
    
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "result": {
                "tools": [
                  {
                    "name": "search_laws",
                    "description": "Tìm kiếm cơ sở dữ liệu luật pháp Việt Nam theo từ khóa (Dân sự, Thương mại, Lao động) làm căn cứ đối chiếu rủi ro hợp đồng.",
                    "inputSchema": {
                      "type": "object",
                      "properties": {
                        "query": {
                          "type": "string",
                          "description": "Từ khóa tìm kiếm (ví dụ: 'phạt vi phạm', 'bồi thường thiệt hại', 'thử việc', 'đơn phương chấm dứt')"
                        },
                        "law_name": {
                          "type": "string",
                          "description": "Tên luật tùy chọn (ví dụ: 'Bộ luật Dân sự 2015', 'Luật Thương mại 2005', 'Bộ luật Lao động 2019')"
                        }
                      },
                      "required": ["query"]
                    }
                  },
                  {
                    "name": "get_law_article",
                    "description": "Lấy chi tiết một điều luật cụ thể theo tên luật và số hiệu điều.",
                    "inputSchema": {
                      "type": "object",
                      "properties": {
                        "law_name": {
                          "type": "string",
                          "description": "Tên luật (ví dụ: 'Bộ luật Dân sự 2015')"
                        },
                        "article_number": {
                          "type": "string",
                          "description": "Số hiệu điều (ví dụ: 'Điều 301')"
                        }
                      },
                      "required": ["law_name", "article_number"]
                    }
                  }
                ]
            },
            "id": payload.id
        }
        
    elif method == "tools/call":
        params = payload.params or {}
        name = params.get("name")
        arguments = params.get("arguments", {})
        
        if name == "search_laws":
            query = arguments.get("query", "")
            law_name = arguments.get("law_name")
            
            if not query:
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32602, "message": "Missing 'query' argument"},
                    "id": payload.id
                }
                
            results = query_db_search(query, law_name)
            
            if not results:
                content_text = "Không tìm thấy điều khoản luật tương ứng."
            else:
                formatted_list = []
                for idx, r in enumerate(results, 1):
                    formatted_list.append(
                        f"[{idx}] {r['law_name']} - {r['article_number']}: {r['article_title']}\n"
                        f"Nội dung: {r['content']}"
                    )
                content_text = "\n\n".join(formatted_list)
                
            return {
                "jsonrpc": "2.0",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": content_text
                        }
                    ]
                },
                "id": payload.id
            }
            
        elif name == "get_law_article":
            law_name = arguments.get("law_name")
            article_number = arguments.get("article_number")
            
            if not law_name or not article_number:
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32602, "message": "Missing 'law_name' or 'article_number' argument"},
                    "id": payload.id
                }
                
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT content, article_title FROM laws WHERE law_name = ? AND article_number = ?",
                (law_name, article_number)
            )
            row = cursor.fetchone()
            conn.close()
            
            if row:
                content_text = f"{law_name} - {article_number}: {row['article_title']}\nNội dung: {row['content']}"
            else:
                content_text = f"Không tìm thấy điều luật {article_number} của {law_name}."
                
            return {
                "jsonrpc": "2.0",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": content_text
                        }
                    ]
                },
                "id": payload.id
            }
            
        else:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Tool '{name}' not found"},
                "id": payload.id
            }
            
    elif method == "resources/list":
        # List of legal documents available as resources
        return {
            "jsonrpc": "2.0",
            "result": {
                "resources": [
                    {
                        "uri": "legal://vietnam/civil-code-2015",
                        "name": "Bộ luật Dân sự 2015",
                        "mimeType": "text/plain",
                        "description": "Các điều khoản liên quan tới hợp đồng dân sự, phạt vi phạm, bồi thường thiệt hại."
                    },
                    {
                        "uri": "legal://vietnam/commercial-law-2005",
                        "name": "Luật Thương mại 2005",
                        "mimeType": "text/plain",
                        "description": "Các quy định về phạt vi phạm hợp đồng thương mại (giới hạn 8%)."
                    },
                    {
                        "uri": "legal://vietnam/labor-code-2019",
                        "name": "Bộ luật Lao động 2019",
                        "mimeType": "text/plain",
                        "description": "Quy định về thời gian thử việc, đơn phương chấm dứt hợp đồng lao động."
                    }
                ]
            },
            "id": payload.id
        }
        
    else:
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": f"Method '{method}' not found"},
            "id": payload.id
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8005)
