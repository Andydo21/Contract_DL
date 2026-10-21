from django.test import SimpleTestCase, TestCase, override_settings
from NewIdea.services.spec_drift_service import compare_sources, grounding, discovered_warnings
from contracts.tests.test_intelligence import ContractIntelligenceTests
from ai_extract.models import LayoutExtractionRun, LayoutExtractionPage, LayoutExtractionBlock
import json
from unittest.mock import patch
from NewIdea.services.search_evidence_service import attach_document_checks
from NewIdea.services.knowledge_answer_service import answer_from_sources


def source(value, part='AX-203', **updates):
    row = dict(chunk_id='block:7', text=f'Part number: {part}\n{value}', version_id=1,
               bbox=[100, 100, 300, 250], page_number=1, image_path='p1.png', source_url='/pages/1/?version_id=1')
    row.update(updates)
    return row


class SpecDriftChecks(SimpleTestCase):
    def test_same_part_material_difference_has_two_source_bboxes(self):
        result = compare_sources([source('Material: SUS304')], [source('Material: SUS316')])
        self.assertEqual(len(result['differences']), 1)
        difference = result['differences'][0]
        self.assertFalse(difference['semantic_conflict_verified'])
        self.assertEqual(difference['left']['source']['bbox'], [100, 100, 300, 250])
        self.assertIn('#block-7', difference['right']['source']['source_url'])

    def test_equivalent_units_are_not_drift(self):
        self.assertEqual(compare_sources([source('Diameter: 10 mm')], [source('Diameter: 1 cm')])['differences'], [])

    def test_distinct_parts_and_ambiguous_subjects_are_not_paired(self):
        self.assertEqual(compare_sources([source('Voltage: 24 V')], [source('Voltage: 48 V', part='AX-204')])['differences'], [])
        multi = source('Voltage: 24 V\nPart number: OTHER')
        result = compare_sources([multi], [source('Voltage: 48 V')])
        self.assertEqual(result['differences'], [])
        self.assertGreater(result['coverage']['ambiguous_specs'], 0)

    def test_tolerances_and_incompatible_units_require_review_not_numeric_guess(self):
        for value in ('24 V ± 2 V', '24 A', '24,5 V', '24–48 V', '24 mm'):
            result = compare_sources([source('Voltage: '+value)], [source('Voltage: 48 V')])
            self.assertEqual(result['differences'], [])
            self.assertEqual(result['coverage']['ambiguous_specs'], 1)

    def test_multiple_values_of_same_field_are_ambiguous(self):
        result = compare_sources([source('Voltage: 24 V\nVoltage: 48 V')], [source('Voltage: 12 V')])
        self.assertEqual(result['differences'], [])

    def test_duplicate_text_is_not_claimed_as_binary_duplicate(self):
        text = ' '.join('word'+str(i) for i in range(40))
        result = compare_sources([source('', text=text)], [source('', text=text.upper())])
        self.assertEqual(result['duplicate']['status'], 'same_extracted_text')
        self.assertFalse(result['duplicate']['binary_identical'])

    def test_missing_or_invalid_bbox_never_produces_coordinates(self):
        for update in (dict(bbox=[]), dict(bbox=[0, 0, 1001, 5]), dict(image_path='')):
            result = grounding(source('Material: SUS304', **update))
            self.assertEqual(result['bbox'], [])
            self.assertEqual(result['grounding_status'], 'bbox_unavailable')

    def test_auto_checks_only_discovered_versions_and_skips_truncated_sources(self):
        rows = [source('Material: SUS304', version_id=1), source('Material: SUS316', version_id=2),
                source('Material: OTHER', version_id=99)]
        result = discovered_warnings(rows, [1, 2])
        self.assertEqual(len(result['warnings']), 1)
        self.assertEqual(result['documents_checked'], 2)
        self.assertFalse(result['whole_collection_checked'])
        self.assertEqual(discovered_warnings(rows, [1, 2], partial=True)['warnings'], [])

    def test_audit_question_gets_both_actual_sources_and_review_warning(self):
        rows = [source('Material: SUS304', version_id=1), source('Material: SUS316', version_id=2)]
        checks = discovered_warnings(rows, [1, 2])
        citations, checks = attach_document_checks([], checks)
        self.assertEqual([c['evidence_id'] for c in citations], ['E1', 'E2'])
        calls = []
        def model(task, payload):
            calls.append((task, payload))
            return {'supported': True} if task == 'verify_answer' else {'answer': 'Vật liệu khác nhau, cần chuyên gia kiểm tra [E1] [E2].'}
        with patch('NewIdea.services.knowledge_answer_service.request_qwen', side_effect=model):
            result = answer_from_sources('Tài liệu nào có vấn đề hoặc khác nhau?', citations, dict(document_checks=checks))
        self.assertEqual(result['generation_status'], 'generated')
        self.assertEqual(result['document_checks_in_generation'], 1)
        self.assertTrue(result['quality_gate']['document_audit_evidence_available'])
        self.assertIn('not proven contradictions', calls[0][1]['instruction'])
        self.assertIn('SUS304', calls[0][1]['evidence'][0]['text'])
        self.assertIn('SUS316', calls[0][1]['evidence'][1]['text'])

    def test_missing_number_cannot_be_bypassed_by_audit_intent(self):
        rows = [source('Material: SUS304', version_id=1), source('Material: SUS316', version_id=2)]
        citations, checks = attach_document_checks([], discovered_warnings(rows, [1, 2]))
        with patch('NewIdea.services.knowledge_answer_service.request_qwen') as model:
            result = answer_from_sources('Có sai lệch 9999 mm không?', citations, dict(document_checks=checks))
        model.assert_not_called()
        self.assertEqual(result['generation_status'], 'abstained')


@override_settings(A3_HYBRID_ENABLED=False)
class SpecDriftAuthorization(TestCase):
    setUp = ContractIntelligenceTests.setUp

    def extract(self, version, material):
        run = LayoutExtractionRun.objects.create(version=version, status='COMPLETED')
        page = LayoutExtractionPage.objects.create(run=run, page_number=1, image_path='p.png')
        LayoutExtractionBlock.objects.create(page=page, block_order=1,
            text=f'Part number: AX-203\nMaterial: {material}', bbox=[100, 100, 300, 250])

    def compare(self, right=None):
        return self.client.post('/api/newidea/spec-drift/', json.dumps(dict(cad_version_id=self.version.pk,
            sop_version_id=(right or self.new_version).pk)), content_type='application/json')

    def test_completed_sources_are_compared_and_foreign_versions_denied(self):
        self.extract(self.version, 'SUS304'); self.extract(self.new_version, 'SUS316')
        result = self.compare()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(result.json()['differences']), 1)
        self.assertEqual(self.compare(self.foreign_version).status_code, 404)

    def test_unextracted_and_anonymous_requests_are_rejected(self):
        self.assertEqual(self.compare().status_code, 400)
        self.client.logout()
        self.assertEqual(self.compare().status_code, 401)
