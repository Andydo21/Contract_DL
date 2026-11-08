"""Marked legal documents, questions over them and contract comparison; the models are explicit stubs."""
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from ai_extract.models import LegalDocument
from ai_extract.services.contract_clause_service import extract_from_text, prepare_contract_clauses
from ai_extract.services.contract_pipeline_service import QwenGatewayError, plan_legal_questions
from contracts.models import Contract, ContractVersion, KnowledgeSearchLog
from contracts.tests.test_intelligence import ContractIntelligenceTests
from NewIdea.repositories import contract_repository, knowledge_repository
from NewIdea.services import contract_search_service, knowledge_search_service, search_job_service
from NewIdea.services.errors import KnowledgeError

LAW = 'Điều 1. Phạm vi\nLuật này quy định về nhà ở.\nĐiều 2. Công chứng\nHợp đồng mua bán nhà ở phải được công chứng.'
QUESTION = 'Hợp đồng mua bán nhà ở có phải công chứng không?'
ENGLISH_CONTRACT = 'The Seller transfers the house to the Buyer and no notarization is needed.'


def numbers(*values):
    """Stand in for GLiNER2, which marks the clause numbers it reads."""
    return lambda text, units: dict(starts=[dict(text=v, start=text.index(v), end=text.index(v)+len(v)) for v in values], parties=[], schema='x')


class LegalBase(TestCase):
    setUp = ContractIntelligenceTests.setUp

    def law(self, code='LAW-1', company=None, public=True, status=LegalDocument.FULLY_IN_FORCE, **fields):
        contract = Contract.objects.create(company=company or self.other, contract_code=code, title='Luật Nhà ở')
        version = ContractVersion.objects.create(contract=contract, version_number=1)
        knowledge_repository.mark_legal(contract, public=public, source_id=code, number=code, doc_type='Luật', status=status, **fields)
        return contract, version


class AccessTests(LegalBase):
    def readable(self, user):
        return set(contract_repository.legal_contracts(user).values_list('contract_code', flat=True))

    def test_public_law_is_open_to_other_companies(self):
        self.law()
        self.assertEqual(self.readable(self.user), {'LAW-1'})

    def test_a_marked_private_document_stays_with_its_company(self):
        self.law(company=self.company, public=False, status=LegalDocument.UPLOADED)
        self.assertEqual(self.readable(self.user), {'LAW-1'})
        self.assertEqual(self.readable(self.outsider), set())

    def test_an_account_without_a_company_reads_only_public_law(self):
        self.law('PRIVATE', company=self.company, public=False, status=LegalDocument.UPLOADED)
        self.law('PUBLIC')
        self.assertEqual(self.readable(get_user_model().objects.create_user(username='nobody')), {'PUBLIC'})

    def test_a_repealed_document_is_never_read(self):
        self.law(status='Hết hiệu lực toàn bộ')
        self.assertEqual(self.readable(self.user), set())

    def test_a_law_not_yet_in_force_counts_only_from_its_start_date(self):
        self.law('LATER', status=LegalDocument.NOT_YET_IN_FORCE, effective_on=date.today()+timedelta(days=1))
        self.law('STARTED', status=LegalDocument.NOT_YET_IN_FORCE, effective_on=date.today()-timedelta(days=1))
        self.assertEqual(self.readable(self.user), {'STARTED'})

    def test_legal_search_sees_only_marked_documents(self):
        _, version = self.law()
        versions, total = contract_repository.latest_visible_versions(self.user, limit=None, load_sources=False, legal=True)
        self.assertEqual(([v.pk for v in versions], total), ([version.pk], 1))

    def test_a_source_states_status_and_amendments(self):
        _, version = self.law(status=LegalDocument.PARTLY_REPEALED, amended_by=['43/2024/QH15'])
        stated = knowledge_repository.legal_fields([version])[version.pk]
        self.assertEqual(stated['evidence_kind'], 'legal_provision')
        self.assertIn('Hết hiệu lực một phần', stated['legal_note'])
        self.assertIn('43/2024/QH15', stated['legal_note'])

    def test_a_translation_says_it_is_one(self):
        _, version = self.law()
        LegalDocument.objects.update(doc_type=LegalDocument.TRANSLATION)
        self.assertIn('bản dịch', knowledge_repository.legal_fields([version])[version.pk]['legal_note'])


class ClauseGateTests(LegalBase):
    def tree(self):
        return dict(leaves=[dict(chunk_id='b1', text=LAW, layout_type='text', page_number=1)], source_fingerprint='f')

    def test_a_contract_is_split_even_without_parties_read(self):
        # Whether it is a contract comes from the table, not from the parties a scan yields.
        self.assertEqual(extract_from_text(LAW, requester=numbers('Điều 1', 'Điều 2'))['status'], 'complete')

    def test_a_marked_document_gets_its_articles_without_parties(self):
        _, version = self.law()
        result = prepare_contract_clauses(self.tree(), version, requester=numbers('Điều 1', 'Điều 2'))
        self.assertEqual((result['status'], [c['number'] for c in result['clauses']]), ('complete', ['Điều 1', 'Điều 2']))

    def test_an_unmarked_document_is_treated_as_a_contract(self):
        with patch('ai_extract.repositories.layout_repository.ensure_write_connection'):
            result = prepare_contract_clauses(self.tree(), self.version, requester=numbers('Điều 1', 'Điều 2'))
        self.assertEqual((result['status'], len(result['clauses'])), ('complete', 2))

    def identity_tree(self):
        """Two "cha" in different articles that GLiNER2 left unresolved."""
        data = self.tree()
        data['knowledge_graph'] = dict(entities=[dict(key='e1', name='cha', canonical_key='c1', source_id='b1', start=0),
                                                 dict(key='e2', name='cha', canonical_key='c2', source_id='b1', start=60)])
        data['identity_resolution'] = dict(status='complete', pairs=[], decisions=[])
        return data

    def test_a_law_links_a_name_mentioned_again_in_another_article(self):
        _, version = self.law()
        data = self.identity_tree()
        prepare_contract_clauses(data, version, requester=numbers('Điều 1', 'Điều 2'))
        self.assertEqual({e['canonical_key'] for e in data['knowledge_graph']['entities']}, {'c1'})

    def test_gliner2_difference_keeps_two_things_with_one_name_apart(self):
        _, version = self.law()
        data = self.identity_tree()
        side = lambda start: dict(scope=dict(source_id='b1', mention_start=start))
        data['identity_resolution'].update(pairs=[dict(id='p', left=side(0), right=side(60))], decisions=[dict(id='p', status='different')])
        prepare_contract_clauses(data, version, requester=numbers('Điều 1', 'Điều 2'))
        self.assertEqual({e['canonical_key'] for e in data['knowledge_graph']['entities']}, {'c1', 'c2'})

    def test_a_contract_still_merges_unresolved_equal_names(self):
        data = self.identity_tree()
        requester = lambda text, units: dict(numbers('Điều 1', 'Điều 2')(text, units), parties=[
            dict(name='Bên A', role='A', confidence=.9, start=0), dict(name='Bên B', role='B', confidence=.9, start=1)])
        with patch('ai_extract.repositories.extraction_repository.replace_contract_clauses'), \
                patch('ai_extract.repositories.layout_repository.ensure_write_connection'):
            result = prepare_contract_clauses(data, self.version, requester=requester)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual({e['canonical_key'] for e in data['knowledge_graph']['entities']}, {'c1'})

    def test_upload_form_marks_only_when_asked(self):
        from contracts.services.contract_operations_service import create_contract
        for code, kind, expected in (('UP-1', 'legal', True), ('UP-2', 'contract', False), ('UP-3', None, False)):
            form = dict(contract_code=code, title='Tài liệu', raw_content='Nội dung')
            if kind:
                form['document_kind'] = kind
            created = Contract.objects.create(company=self.company, contract_code=code, title='Tài liệu')
            with patch('contracts.services.contract_operations_service.contract_service.create_and_analyze_contract', return_value=created):
                create_contract(self.user, 'POST', form, {})
            self.assertEqual(bool(knowledge_repository.legal_document_for(created)), expected, kind)

    def test_unmarking_makes_it_a_contract_again(self):
        contract, _ = self.law()
        knowledge_repository.unmark_legal(contract)
        self.assertIsNone(knowledge_repository.legal_document_for(contract))


class PlanTests(SimpleTestCase):
    def test_qwen_reads_the_contract_and_asks_in_the_language_of_the_law(self):
        seen = {}

        def ask(task, payload):
            seen.update(payload)
            return dict(questions=[QUESTION, QUESTION, ' '])
        plan = plan_legal_questions('House sale', ENGLISH_CONTRACT, ask)
        self.assertEqual(plan['queries'], [QUESTION])
        self.assertEqual(plan['answer_parts'][0]['retrieval_query'], QUESTION)
        self.assertIn(ENGLISH_CONTRACT, seen['contract'])
        self.assertIn('any language', seen['instruction'])

    def test_no_usable_question_raises_rather_than_searching_nothing(self):
        with self.assertRaises(QwenGatewayError):
            plan_legal_questions('t', 'x', lambda task, payload: dict(questions=[' ']))


def law_passage(version):
    return dict(chunk_id=f'block:{version.pk}', text=LAW, document_id=f'contract-version-{version.pk}', version_id=version.pk, heading_path=[], page_number=1,
                bbox=[], original_name='Luật Nhà ở', source_location='Trang 1', source_url='/x', layout_type='text', expansion_reason='query_match', neural_logit=1.0)


class Corpus:
    """Keyword search over stored law finds nothing across languages."""
    snapshots = {}
    loaded = {}
    rebuilt = 0

    def __getitem__(self, version_id):
        return dict(leaves=[], nodes=[])

    def keyword_search(self, query, limit=60):
        return []

    def identifier_documents(self, requested):
        return set()


class Backend:
    def __init__(self, version, dense_error=None, rerank_error=None):
        self.version, self.dense_error, self.rerank_error = version, dense_error, rerank_error

    def prime_embeddings(self, queries):
        pass

    def dense_knowledge(self, query, versions, runs, records=()):
        if self.dense_error:
            raise self.dense_error
        payload = dict(source_app='contract_dl', company_id=self.version.contract.company_id, contract_id=self.version.contract_id, version_id=self.version.pk, contract_dl_run_id=1)
        return [SimpleNamespace(payload=payload, score=.9)]

    def rerank_many(self, groups):
        if self.rerank_error:
            raise self.rerank_error
        return [[dict(r, neural_logit=1.0) for r in rows] for _, rows in groups]


@override_settings(A3_HYBRID_ENABLED=True, A2_SEARCH_WORKERS=1)
class CompareTests(LegalBase):
    def compare(self, backend=None, extracted=True, law_version=None):
        receipt = KnowledgeSearchLog.objects.create(user=self.user, version=self.version, query=contract_search_service.COMPARE_QUERY, scope='legal_compare', generated=True, result={})
        run = SimpleNamespace(pk=1, dense_index_status='COMPLETED', colpali_index_status='SKIPPED') if extracted else None
        tree = dict(leaves=[dict(chunk_id='block:1', text=ENGLISH_CONTRACT, heading_path=[], page_number=1, bbox=[], layout_type='text')], nodes=[])
        answered = dict(answer='ok [E1]', generation_status='generated', citation_check=dict(valid=True))
        with patch.object(contract_repository, 'completed_extraction_run', return_value=run), \
                patch.object(contract_repository, 'version_sources', return_value=[]), \
                patch.object(contract_search_service, 'structure_for_version', return_value=tree), \
                patch('ai_extract.services.contract_pipeline_service.request_qwen', return_value=dict(questions=[QUESTION])), \
                patch.object(knowledge_search_service, 'SearchBackend', return_value=backend), \
                patch.object(knowledge_search_service, 'indexed_corpus', return_value=Corpus()), \
                patch.object(knowledge_search_service, 'hydrate', side_effect=lambda hits, *a, **k: [law_passage(law_version)]), \
                patch.object(knowledge_search_service, 'expand_retrieval_context', side_effect=lambda q, t, v, ranked, c, backend=None: (ranked, {})), \
                patch('NewIdea.services.knowledge_answer_service.answer_from_sources', return_value=answered) as generate:
            result = contract_search_service.compare_with_law(receipt)
        return result, generate

    def test_an_english_contract_reaches_vietnamese_law_and_the_source_states_its_status(self):
        _, version = self.law(status=LegalDocument.PARTLY_REPEALED)
        result, generate = self.compare(Backend(version), law_version=version)
        kinds = {c['evidence_kind'] for c in result['citations']}
        self.assertEqual(kinds, {'contract_under_review', 'legal_provision'})
        law = next(c for c in result['citations'] if c['evidence_kind'] == 'legal_provision')
        self.assertIn('Hết hiệu lực một phần', law['legal_note'])
        self.assertEqual(generate.call_args.kwargs['instruction'], contract_search_service.COMPARE_INSTRUCTION)

    def test_a_vector_outage_stops_the_comparison(self):
        _, version = self.law()
        with self.assertRaisesMessage(KnowledgeError, 'theo ngữ nghĩa'):
            self.compare(Backend(version, dense_error=RuntimeError('down')), law_version=version)

    def test_no_stored_law_stops_the_comparison(self):
        with self.assertRaisesMessage(KnowledgeError, 'theo ngữ nghĩa'):
            self.compare(Backend(self.version), law_version=self.version)

    def test_a_reranker_outage_stops_the_comparison(self):
        _, version = self.law()
        with self.assertRaisesMessage(KnowledgeError, 'xếp hạng'):
            self.compare(Backend(version, rerank_error=RuntimeError('down')), law_version=version)

    def test_a_contract_not_extracted_is_refused(self):
        with self.assertRaisesMessage(KnowledgeError, 'chưa được trích xuất'):
            self.compare(extracted=False)

    def test_a_job_for_another_companys_contract_is_refused(self):
        from django.core.exceptions import ObjectDoesNotExist
        with self.assertRaises(ObjectDoesNotExist):
            search_job_service.enqueue_search(self.user, dict(scope='legal_compare', contract_id=self.foreign.pk))

    def test_a_legal_document_cannot_be_the_contract_under_comparison(self):
        knowledge_repository.mark_legal(self.contract)
        with self.assertRaisesMessage(ValueError, 'thủ tục pháp lý'):
            search_job_service.enqueue_search(self.user, dict(scope='legal_compare', contract_id=self.contract.pk))

    def test_the_worker_shows_why_a_comparison_stopped(self):
        queued = search_job_service.enqueue_search(self.user, dict(scope='legal_compare', contract_id=self.contract.pk))
        with patch.object(contract_search_service, 'compare_with_law', side_effect=KnowledgeError('Kho luật chưa sẵn sàng.')):
            search_job_service.process_next_job(None)
        receipt = KnowledgeSearchLog.objects.get(pk=queued['search_id'])
        self.assertEqual((receipt.status, receipt.result['error']), ('FAILED', 'Kho luật chưa sẵn sàng.'))

    def test_the_worker_stores_a_finished_comparison(self):
        queued = search_job_service.enqueue_search(self.user, dict(scope='legal_compare', contract_id=self.contract.pk))
        with patch.object(contract_search_service, 'compare_with_law', return_value=dict(success=True, answer='ok')):
            search_job_service.process_next_job(None)
        receipt = KnowledgeSearchLog.objects.get(pk=queued['search_id'])
        self.assertEqual((receipt.status, receipt.result['response']['answer']), ('COMPLETED', 'ok'))

    def test_a_queued_question_keeps_the_chosen_corpus(self):
        queued = search_job_service.enqueue_search(self.user, dict(scope='knowledge', corpus='legal', query='thủ tục'))
        self.assertEqual(KnowledgeSearchLog.objects.get(pk=queued['search_id']).result['request']['corpus'], 'legal')

    def test_an_unknown_corpus_is_refused(self):
        with self.assertRaises(ValueError):
            knowledge_search_service.search_knowledge(self.user, 'câu hỏi', corpus='other')


class WholeClauseTests(SimpleTestCase):
    def test_passages_of_one_article_become_one_source_with_its_full_text(self):
        from types import SimpleNamespace
        from NewIdea.services.knowledge_search_service import whole_clauses
        clauses = dict(status='complete', clauses=[dict(title='Điều 16. Thủ tục', content='Điều 16. Thủ tục\n1. Nộp tờ khai.\n2. Ký sổ.', source_ids=['a', 'b'])])
        runs = {7: SimpleNamespace(version_id=7, structure=dict(contract_clauses=clauses))}
        sources = [dict(version_id=7, document_id='d', chunk_id='a', page_number=1, text='1. Nộp tờ khai.', neural_logit=2.,
                        retrieval_ranks=[dict(query=0, rank=1), dict(query=1, rank=4)]),
                   dict(version_id=7, document_id='d', chunk_id='b', page_number=1, text='2. Ký sổ.', neural_logit=1.,
                        retrieval_ranks=[dict(query=1, rank=2)], retrieval_hints=[dict(part=1, rank=2)]),
                   dict(version_id=7, document_id='d', chunk_id='c', page_number=2, text='Lời nói đầu', retrieval_ranks=[dict(query=0, rank=3)])]
        article, outside = whole_clauses(sources, runs)
        self.assertEqual(article['text'], clauses['clauses'][0]['content'])
        self.assertEqual(article['retrieval_ranks'], [dict(query=0, rank=1), dict(query=1, rank=2)])
        self.assertEqual(article['retrieval_hints'], [dict(part=1, rank=2)])
        self.assertEqual((article['clause_source_ids'], article['neural_logit']), (['a', 'b'], 2.))
        self.assertEqual(outside['text'], 'Lời nói đầu')
