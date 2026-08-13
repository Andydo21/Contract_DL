import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'workflow_service'))

from workflow.rules import recommend_workflow

def test_real_recommendation():
    print("Testing recommend_workflow with real AI service (running on port 8001, which forwards to Kaggle)...")
    contract_text = "Hợp đồng mua bán thiết bị văn phòng trị giá 500,000,000 VND. Thanh toán theo điều khoản Net 30."
    clause_types = ["Payment Terms", "Termination"]
    contract_type = "Hợp đồng Mua bán"
    
    # We set the environment variable to point to our local AI service
    os.environ["AI_SERVICE_URL"] = "http://localhost:8001"
    
    workflow_type, ordered, reasons, ai_workflow_name = recommend_workflow(
        contract_text, clause_types, contract_type
    )
    
    print("\nResult:")
    print("Workflow Type:", workflow_type)
    print("Ordered Steps:", ordered)
    print("Reasons:\n", reasons)
    print("AI Workflow Name:", ai_workflow_name)
    
    assert workflow_type == "WF_PURCHASE"
    assert "Legal Review" in ordered
    assert "Finance Review" in ordered
    assert ai_workflow_name is None
    print("\nSUCCESS: Fallback worked beautifully even when AI service returned 500!")

if __name__ == "__main__":
    test_real_recommendation()
