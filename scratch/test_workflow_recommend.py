import os
import sys
from unittest.mock import patch, MagicMock

sys.stdout.reconfigure(encoding='utf-8')

# Add workflow_service to sys.path so we can import rules
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'workflow_service'))

from workflow.rules import recommend_workflow

def test_fallback():
    print("Testing recommend_workflow fallback (assuming ai_service is down or unresponsive)...")
    contract_text = "Hợp đồng mua bán thiết bị văn phòng trị giá 500,000,000 VND. Thanh toán theo điều khoản Net 30."
    clause_types = ["Payment Terms", "Termination"]
    contract_type = "Hợp đồng Mua bán"
    
    workflow_type, ordered, reasons, ai_workflow_name = recommend_workflow(
        contract_text, clause_types, contract_type
    )
    
    print("Workflow Type:", workflow_type)
    print("Ordered Steps:", ordered)
    print("Reasons:\n", reasons)
    print("AI Workflow Name:", ai_workflow_name)
    
    # Assertions for fallback behavior
    assert workflow_type == "WF_PURCHASE", f"Expected WF_PURCHASE, got {workflow_type}"
    assert "Legal Review" in ordered, "Expected Legal Review in steps"
    assert "Finance Review" in ordered, "Expected Finance Review in steps"
    assert ai_workflow_name is None, "Expected ai_workflow_name to be None when falling back"
    print("Fallback test passed successfully!\n")

@patch('requests.post')
def test_ai_success(mock_post):
    print("Testing recommend_workflow success (mocking successful AI response)...")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "workflow_name": "Quy trình Phê duyệt Hợp đồng Mua bán Thiết bị Cao cấp",
        "workflow_type": "WF_PURCHASE",
        "steps": ["Legal Review", "Finance Review", "Director Approval", "Contract Signing", "Document Archive"],
        "reasons": "Hợp đồng mua bán thiết bị giá trị cao."
    }
    mock_post.return_value = mock_response

    contract_text = "Hợp đồng mua bán thiết bị văn phòng trị giá 500,000,000 VND. Thanh toán theo điều khoản Net 30."
    clause_types = ["Payment Terms", "Termination"]
    contract_type = "Hợp đồng Mua bán"

    workflow_type, ordered, reasons, ai_workflow_name = recommend_workflow(
        contract_text, clause_types, contract_type
    )

    print("Workflow Type:", workflow_type)
    print("Ordered Steps:", ordered)
    print("Reasons:", reasons)
    print("AI Workflow Name:", ai_workflow_name)

    assert workflow_type == "WF_PURCHASE"
    assert ordered == ["Legal Review", "Finance Review", "Director Approval", "Contract Signing", "Document Archive"]
    assert reasons == "Hợp đồng mua bán thiết bị giá trị cao."
    assert ai_workflow_name == "Quy trình Phê duyệt Hợp đồng Mua bán Thiết bị Cao cấp"
    print("AI Success test passed successfully!")

if __name__ == "__main__":
    test_fallback()
    test_ai_success()
