import requests, json, sys
sys.stdout.reconfigure(encoding='utf-8')

payload = {
    "contract_text": "This Non-Disclosure Agreement is entered into between Company A and Company B for sharing confidential information.",
    "clause_types": ["confidentiality", "non-disclosure"],
    "contract_type": "NDA"
}

r = requests.post(
    "https://rummage-triangle-figurine.ngrok-free.dev/api/v1/recommend_workflow",
    json=payload,
    timeout=30
)
print("Status:", r.status_code)
data = r.json()
print("workflow_type:", data.get("workflow_type"))
print("workflow_name:", data.get("workflow_name"))
print("reasons:", data.get("reasons", "")[:120])
print("steps:")
for s in data.get("steps", []):
    print(f"  - {s['step_name']} (role_id={s['role_id']}): {s['description'][:60]}...")
