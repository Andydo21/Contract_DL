"""A2 human reviewed case capture and exact-machine reuse."""
import json
import re
import unicodedata
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from .models import ExpertCase, CaseAuditEvent

FIELDS = ('title', 'machine', 'component', 'error_code', 'symptom', 'investigation',
          'root_cause', 'solution', 'verification', 'applicability', 'source_reference')


def normalize(value):
    return unicodedata.normalize('NFC', value).casefold().strip()


def serialize(case):
    return dict({field: getattr(case, field) for field in FIELDS}, id=case.pk,
                case_id=str(case.case_id), revision=case.revision, status=case.status,
                author=case.author.get_username(),
                reviewer=case.reviewer.get_username() if case.reviewer else None,
                updated_at=case.updated_at.isoformat(),
                evidence_id=f'A2:{case.case_id}:r{case.revision}')


def similar_cases(query, machine='', limit=5):
    """Lexical suggestions, never proof of applicability or calibrated confidence."""
    terms = set(re.findall(r'[^\W_]+(?:[-./][^\W_]+)*', normalize(query)))
    if not terms:
        return []
    result = []
    for case in ExpertCase.objects.filter(status='approved').select_related('author', 'reviewer'):
        if machine and normalize(case.machine) != normalize(machine):
            continue
        text = ' '.join(getattr(case, f) for f in ('title', 'symptom', 'component', 'error_code'))
        matched = terms & set(re.findall(r'[^\W_]+(?:[-./][^\W_]+)*', normalize(text)))
        if not matched:
            continue
        score = len(matched) / len(terms)
        item = serialize(case)
        item.update(match_score=round(score, 4), matched_terms=sorted(matched),
                    score_kind='lexical_overlap', requires_applicability_review=True)
        result.append(item)
    return sorted(result, key=lambda c: (-c['match_score'], c['case_id']))[:limit]


def case_library(request):
    initial = {}
    ticket_id = request.GET.get('ticket')
    if ticket_id and request.user.is_staff:
        from .models import ShopfloorInquiry
        if ticket_id.isdecimal():
            ticket = ShopfloorInquiry.objects.filter(pk=ticket_id).first()
            if ticket:
                entities = ticket.get_extracted_entities()
                initial = dict(title=f'Case {ticket.ticket_code}', machine=ticket.machine,
                               symptom=ticket.question, solution=ticket.expert_answer or '',
                               root_cause=entities.get('root_cause', ''),
                               component=entities.get('component', ''),
                               source_reference=ticket.ticket_code)
    return render(request, 'case_library.html', {'initial_case': initial})


@require_http_methods(['GET', 'POST'])
def case_api(request):
    if request.method == 'GET':
        query = request.GET.get('q', '').strip()
        if query:
            return JsonResponse({'success': True, 'cases': similar_cases(query, request.GET.get('machine', ''))})
        cases = ExpertCase.objects.select_related('author', 'reviewer')
        if not request.user.is_staff:
            cases = cases.filter(status='approved')
        return JsonResponse({'success': True, 'cases': [serialize(c) for c in cases[:100]]})
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Đăng nhập để lưu case.'}, status=401)
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError('JSON phải là object.')
        action = data.get('action', 'create')
        if action not in {'create', 'revise', 'approve', 'deprecate'}:
            raise ValueError('Thao tác không hợp lệ.')
        with transaction.atomic():
            if action == 'create':
                values = {}
                for field in FIELDS:
                    value = data.get(field, '')
                    if not isinstance(value, str):
                        raise ValueError(f'{field} phải là chuỗi.')
                    values[field] = value.strip()
                if any(not values[f] for f in ('title', 'machine', 'symptom')):
                    raise ValueError('Cần tiêu đề, máy và hiện tượng.')
                case = ExpertCase(author=request.user, **values)
                case.full_clean()
                case.save()
            else:
                try:
                    case = ExpertCase.objects.select_for_update().get(pk=data.get('id'))
                except ExpertCase.DoesNotExist:
                    return JsonResponse({'success': False, 'error': 'Không tìm thấy case.'}, status=404)
                if not request.user.is_staff and case.author_id != request.user.pk:
                    return JsonResponse({'success': False, 'error': 'Không có quyền sửa case.'}, status=403)
                if action in {'approve', 'deprecate'} and not request.user.is_staff:
                    return JsonResponse({'success': False, 'error': 'Cần tài khoản reviewer staff.'}, status=403)
                if action == 'revise':
                    # Lock all revisions in the lineage; never overwrite published content.
                    latest = ExpertCase.objects.select_for_update().filter(case_id=case.case_id).order_by('-revision').first()
                    values = {f: data.get(f, getattr(case, f)) for f in FIELDS}
                    if any(not isinstance(v, str) for v in values.values()):
                        raise ValueError('Các trường case phải là chuỗi.')
                    case = ExpertCase(case_id=case.case_id, revision=latest.revision + 1,
                                      author=request.user, **{f: v.strip() for f, v in values.items()})
                    if any(not getattr(case, f) for f in ('title', 'machine', 'symptom')):
                        raise ValueError('Cần tiêu đề, máy và hiện tượng.')
                    case.full_clean()
                    case.save()
                elif action == 'approve':
                    if case.author_id == request.user.pk:
                        return JsonResponse({'success': False, 'error': 'Reviewer phải khác tác giả.'}, status=403)
                    if case.status != 'draft':
                        raise ValueError('Chỉ duyệt case đang ở trạng thái nháp.')
                    if any(not getattr(case, f).strip() for f in
                           ('root_cause', 'solution', 'verification', 'applicability', 'source_reference')):
                        raise ValueError('Cần nguyên nhân, xử lý, xác minh, điều kiện áp dụng và nguồn trước khi duyệt.')
                    siblings = ExpertCase.objects.select_for_update().filter(case_id=case.case_id)
                    if siblings.filter(revision__gt=case.revision).exists():
                        raise ValueError('Chỉ duyệt revision mới nhất.')
                    for old in siblings.filter(status='approved'):
                        old.status = 'deprecated'
                        old.save(update_fields=['status', 'updated_at'])
                        CaseAuditEvent.objects.create(case=old, actor=request.user, action='superseded')
                    case.status = 'approved'
                    case.reviewer = request.user
                    case.approved_at = timezone.now()
                    case.save()
                else:
                    if case.status != 'approved':
                        raise ValueError('Chỉ ngừng sử dụng case đã duyệt.')
                    case.status = 'deprecated'
                    case.save(update_fields=['status', 'updated_at'])
            CaseAuditEvent.objects.create(case=case, actor=request.user, action=action)
        return JsonResponse({'success': True, 'case': serialize(case)})
    except (ValueError, TypeError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as exc:
        from django.core.exceptions import ValidationError
        if isinstance(exc, ValidationError):
            return JsonResponse({'success': False, 'error': '; '.join(exc.messages)}, status=400)
        raise
