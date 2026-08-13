import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add project root to sys.path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from fastapi.testclient import TestClient

class TestMCPIntegration(unittest.TestCase):
    
    def setUp(self):
        self.mcp_url = "http://127.0.0.1:8005/rpc"
        
    def test_01_mcp_server_connection(self):
        """Test direct connection to the Legal MCP Server and check tools/list."""
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": 1
        }
        try:
            r = requests.post(self.mcp_url, json=payload, timeout=2)
            self.assertEqual(r.status_code, 200)
            res = r.json()
            self.assertIn("result", res)
            self.assertIn("tools", res["result"])
            tools = res["result"]["tools"]
            tool_names = [t["name"] for t in tools]
            self.assertIn("search_laws", tool_names)
            self.assertIn("get_law_article", tool_names)
            print("[OK] Legal MCP Server connection and tools/list validated successfully.")
        except requests.exceptions.ConnectionError:
            self.fail("MCP Server is not running on port 8005. Start it first.")

    def test_02_mcp_client_search_laws(self):
        """Test MCPClient's keyword extraction and search_laws lookup."""
        from ai_service.mcp_client import MCPClient
        client = MCPClient(self.mcp_url)
        
        # Test penalty clause concept
        ref_text = client.get_legal_references(
            "Phạt vi phạm nghĩa vụ",
            "Mức phạt vi phạm nghĩa vụ là 10% giá trị hợp đồng."
        )
        self.assertIn("[THAM CHIẾU LUẬT PHÁP VIỆT NAM (MCP)]", ref_text)
        self.assertIn("Điều 301: Mức phạt vi phạm", ref_text)
        self.assertIn("Luật Thương mại 2005", ref_text)
        print("[OK] MCPClient successfully matched and fetched law articles for commercial penalty.")

        # Test labor probation concept
        ref_labor = client.get_legal_references(
            "Thời gian thử việc",
            "Thời gian thử việc đối với vị trí kỹ sư lập trình là 90 ngày."
        )
        self.assertIn("Điều 25: Thời gian thử việc", ref_labor)
        self.assertIn("Bộ luật Lao động 2019", ref_labor)
        print("[OK] MCPClient successfully matched and fetched law articles for labor probation.")

    @patch("ai_service.main.model", "mock-model") # Avoid triggering GPU model loading
    @patch("ai_service.main.tokenizer", "mock-tokenizer")
    def test_03_ai_service_endpoint_injection(self):
        """Test AI Service analyze endpoint receives and injects MCP laws into prompt content."""
        from ai_service.main import app
        
        # Setup TestClient for AI Service FastAPI
        client = TestClient(app)
        
        payload = {
            "clauses": [
                {
                    "title": "Phạt vi phạm nghĩa vụ",
                    "content": "Bên vi phạm phải chịu phạt 10% giá trị hợp đồng."
                }
            ],
            "extracted_entities": [],
            "risk_rules": []
        }
        
        # Mock _forward_to_kaggle to capture what was sent
        with patch("ai_service.main._forward_to_kaggle") as mock_forward:
            mock_forward.return_value = {
                "overall_score": 50,
                "summary": "Mock summary",
                "findings": []
            }
            
            response = client.post("/api/v1/analyze", json=payload)
            self.assertEqual(response.status_code, 200)
            
            # Verify _forward_to_kaggle was called
            self.assertTrue(mock_forward.called)
            called_payload = mock_forward.call_args[0][0]
            
            # Check the forwarded clauses
            forwarded_clauses = called_payload["clauses"]
            first_clause = forwarded_clauses[0]
            
            # Confirm that MCP legal references were appended to the content
            self.assertIn("[THAM CHIẾU LUẬT PHÁP VIỆT NAM (MCP)]", first_clause["content"])
            self.assertIn("Điều 301: Mức phạt vi phạm", first_clause["content"])
            print("[OK] AI Service correctly injected MCP database law context into incoming clause text.")

if __name__ == "__main__":
    unittest.main()
