import requests

def test_endpoints():
    print("Testing http://localhost:8001/health ...")
    try:
        r = requests.get("http://localhost:8001/health", timeout=5)
        print("Health response:", r.status_code, r.json())
    except Exception as e:
        print("Health failed:", e)

    print("\nTesting http://localhost:8001/api/v1/recommend_workflow ...")
    try:
        r = requests.post(
            "http://localhost:8001/api/v1/recommend_workflow",
            json={
                "contract_text": "Hợp đồng mua bán thiết bị văn phòng trị giá 500,000,000 VND. Thanh toán theo điều khoản Net 30.",
                "clause_types": ["Payment Terms", "Termination"],
                "contract_type": "Hợp đồng Mua bán"
            },
            timeout=10
        )
        print("Recommend workflow response:", r.status_code)
        if r.status_code == 200:
            print(r.json())
        else:
            print(r.text)
    except Exception as e:
        print("Recommend workflow failed:", e)

if __name__ == "__main__":
    test_endpoints()
