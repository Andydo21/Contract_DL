import os
import sys
import django
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
sys.stdout.reconfigure(encoding='utf-8')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import RequestFactory
from core.views import interview_view, api_interview_reply, api_generate_knowledge
from core.models import Interview, Knowledge

print("--- 1. Testing interview_view for ID 4 (previously 404) ---")
rf = RequestFactory()
req = rf.get('/interviews/4/')
res = interview_view(req, 4)
print(f"Status: {res.status_code}")
assert res.status_code == 200, "interview_view failed!"

interview = Interview.objects.first()
print(f"Interview ID: {interview.id}, Code: {interview.interview_code}, Topic: {interview.topic}")

print("\n--- 2. Testing real expert reply & dynamic Socratic question ---")
req_reply = rf.post(
    f'/api/interviews/{interview.id}/reply/',
    data=json.dumps({
        'message': "Theo kinh nghiệm xử lý thực tế của tôi, với máy M12 khi nhiệt độ phòng vượt 40 độ C, dầu bôi trơn ISO VG 32 bị giảm độ nhớt làm tăng ma sát. Kỹ sư không được tháo cụm trục mà phải kích hoạt chế độ làm mát cưỡng bức của hệ thống chiller và kiểm tra áp suất bôi trơn trước."
    }),
    content_type='application/json'
)
res_reply = api_interview_reply(req_reply, interview.id)
data_reply = json.loads(res_reply.content.decode('utf-8'))
print(f"Expert Message Saved: {data_reply.get('expert_message')[:80]}...")
print(f"AI Socratic Question Generated: {data_reply.get('ai_question')}")

print("\n--- 3. Testing Dynamic Rule Synthesis from expert conversation ---")
req_gen = rf.post(f'/api/interviews/{interview.id}/generate-knowledge/')
res_gen = api_generate_knowledge(req_gen, interview.id)
data_gen = json.loads(res_gen.content.decode('utf-8'))
print(f"Rule Code: {data_gen.get('knowledge_code')}")
print(f"Rule Title: {data_gen.get('title')}")
print(f"Rule Content:\n{data_gen.get('content')}")

print("\n=== ALL TESTS PASSED SUCCESSFULLY! ===")
