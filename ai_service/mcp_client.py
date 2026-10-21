import os
import requests
import logging
from typing import List

logger = logging.getLogger("mcp_client")

class MCPClient:
    def __init__(self, server_url: str = None):
        if not server_url:
            server_url = os.environ.get("LEGAL_MCP_SERVER_URL", "http://127.0.0.1:8005/rpc")
        self.server_url = server_url
        logger.info(f"Initialized MCPClient targeting: {self.server_url}")

    def extract_search_keywords(self, title: str, content: str) -> str:
        """Extract key legal concepts from clause title and content for Vietnamese laws."""
        text = f"{title} {content}".lower()
        search_terms = []
        
        if "phạt" in text or "vi phạm" in text or "penalty" in text:
            search_terms.append("phạt vi phạm")
        if "bồi thường" in text or "thiệt hại" in text or "damages" in text:
            search_terms.append("bồi thường thiệt hại")
        if "bất khả kháng" in text or "force majeure" in text or "thiên tai" in text or "dịch bệnh" in text:
            search_terms.append("bất khả kháng")
        if "đơn phương" in text or "chấm dứt" in text or "huỷ bỏ" in text or "termination" in text:
            search_terms.append("đơn phương chấm dứt")
        if "thử việc" in text or "probation" in text or "học việc" in text:
            search_terms.append("thử việc")
        if "hiệu lực" in text or "vô hiệu" in text or "validity" in text:
            search_terms.append("hiệu lực giao dịch dân sự")
        if "miễn trách" in text or "miễn trừ" in text or "liability" in text:
            search_terms.append("miễn trách nhiệm")
        if "loại hợp đồng" in text or "thời hạn hợp đồng" in text or "duration" in text:
            search_terms.append("loại hợp đồng")

        if not search_terms:
            # Fallback: clean the clause title and use it as keywords
            clean_title = "".join([char if char.isalnum() or char.isspace() else " " for char in title])
            return clean_title.strip()
            
        return " ".join(search_terms)

    def get_legal_references(self, clause_title: str, clause_content: str) -> str:
        """Query the Legal MCP Server for relevant Vietnamese law articles."""
        query = self.extract_search_keywords(clause_title, clause_content)
        if not query:
            return ""
            
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search_laws",
                "arguments": {
                    "query": query
                }
            },
            "id": 1
        }
        
        try:
            logger.info(f"Sending MCP query: '{query}' for clause '{clause_title}'")
            response = requests.post(self.server_url, json=payload, timeout=5)
            response.raise_for_status()
            res_json = response.json()
            
            if "error" in res_json:
                logger.error(f"MCP Server error: {res_json['error']}")
                return ""
                
            contents = res_json.get("result", {}).get("content", [])
            if contents and contents[0].get("type") == "text":
                text_content = contents[0].get("text", "")
                if "Không tìm thấy" in text_content:
                    return ""
                
                # Format legal references beautifully
                ref_block = (
                    f"\n\n[THAM CHIẾU LUẬT PHÁP VIỆT NAM (MCP)]:\n"
                    f"{text_content}\n"
                    f"[HẾT THAM CHIẾU MCP]"
                )
                return ref_block
                
        except Exception as e:
            logger.warning(f"Failed to query MCP Server at {self.server_url}: {e}. AI will fallback to general legal knowledge.")
            
        return ""
