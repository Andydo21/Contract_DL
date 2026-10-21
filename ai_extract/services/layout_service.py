"""Prepare pipeline screens and run the authorized A3 extraction workflow."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from django.db import transaction, close_old_connections
from django.utils import timezone
from .inference_runtime_service import PipelineProgress
from django.conf import settings
from ai_extract.services.contract_pipeline_service import LayoutExtractionService
from ai_extract.repositories import layout_repository
from NewIdea.repositories.contract_repository import contract_version

def image_url(path):
    return f"/{settings.MEDIA_URL.strip('/')}/{path.lstrip('/')}" if path else ''

def dashboard(user):
    cards = []
    for contract in layout_repository.dashboard_contracts(user):
        version = contract.latest_version
        cards.append(dict(contract=contract, version=version, run=layout_repository.latest_run(version)))
    return dict(cards=cards)

def pipeline(user, contract_id, version_id=None, graph_page=None, graph_relation='structure', graph_offset=0, graph_node=None):
    if version_id and not str(version_id).isdecimal():
        raise ValueError('Version ID không hợp lệ.')
    contract = layout_repository.contract_for(user, contract_id)
    version = contract_version(contract, version_id) if version_id else contract.latest_version
    run = layout_repository.latest_run(version)
    pages = layout_repository.pages(run)
    for page in pages:
        page.preview_url = image_url(page.image_path)
    from .graph_visualization_service import tree_payload
    from .graph_visualization_service import graph_payload
    return dict(contract=contract, version=version, run=run, pages=pages,
                can_extract=version is not None and version == contract.latest_version,
                graph_visualization=graph_payload(run, contract.pk, version.pk if version else None,
                                                  graph_page, graph_relation, graph_offset, graph_node),
                structure_visualization=tree_payload(run.structure or {}, contract.pk, version.pk) if run else {})

def inspect_page(user, contract_id, page_number, version_id=None, graph_relation='all', graph_offset=0, graph_node=None, run_id=None):
    if run_id and not str(run_id).isdecimal():
        raise ValueError('Invalid extraction run ID')
    if version_id and (not str(version_id).isdecimal()):
        raise ValueError('Version ID không hợp lệ.')
    contract = layout_repository.contract_for(user, contract_id)
    version = contract_version(contract, version_id)
    run = layout_repository.run_for_version(version, run_id) if run_id else layout_repository.latest_run(version, completed=True)
    page = layout_repository.page_for(run, page_number)
    page.preview_url = image_url(page.image_path)
    for block in layout_repository.page_blocks(page):
        if len(block.bbox) == 4:
            x1, y1, x2, y2 = block.bbox
            block.box_style = f'left:{x1 / 10:.2f}%;top:{y1 / 10:.2f}%;width:{max(0, x2 - x1) / 10:.2f}%;height:{max(0, y2 - y1) / 10:.2f}%;'
        else:
            block.box_style = 'display:none;'
    numbers = layout_repository.page_numbers(run)
    index = numbers.index(page_number)
    from .graph_visualization_service import page_payload
    from .graph_visualization_service import graph_payload
    return dict(contract=contract, version=version, run=run, page=page,
                graph_page_fixed=True,
                graph_visualization=graph_payload(run, contract.pk, version.pk, page_number, graph_relation, graph_offset, graph_node),
                page_visualization=page_payload(run, page), previous_page=numbers[index - 1] if index else None, next_page=numbers[index + 1] if index + 1 < len(numbers) else None)

def extract(user, contract_id):
    contract = layout_repository.contract_for(user, contract_id)
    version = contract.latest_version
    if not version:
        raise ValueError('Contract has no version.')
    run = LayoutExtractionService().extract_version(version)
    processing=run.structure.get('processing', {})
    failed_pages = processing.get('failed_pages', [])
    incomplete = {key:processing.get(key,[]) for key in (
        'visual_ocr_incomplete_pages','body_ocr_incomplete_pages','entity_incomplete_pages')}
    return dict(success=run.status == 'COMPLETED', partial=bool(failed_pages or any(incomplete.values())), error=run.error_message,
                **incomplete,
                failed_pages=failed_pages, run_id=run.id, status=run.status, total_pages=run.total_pages, total_blocks=run.total_blocks, dense_index_status=run.dense_index_status, dense_points_count=run.dense_points_count, colpali_index_status=run.colpali_index_status, colpali_points_count=run.colpali_points_count, structure_status=run.structure.get('structure_status'), structure_analysis=run.structure.get('analysis', {}), graph_index=run.structure.get('graph_index', {}), knowledge_status=run.structure.get('knowledge_graph', {}).get('status', 'not_analyzed'))


def reindex_versions(version_id=None, *, dense_only=False):
    seen = set()
    for run in layout_repository.completed_runs(version_id):
        if run.version_id in seen:
            continue
        seen.add(run.version_id)
        LayoutExtractionService()._index_plan_a_collections(run,dense_only=dense_only)
        yield run


def enrich_entity_graph(run):
    """Enrich a completed source tree without redoing OCR or changing vector IDs."""
    from copy import deepcopy
    from .gliner_entity_service import extract_graph_entities, enrich_document_relations
    from .document_structure_service import attach_reading_streams
    from .document_graph_service import sync_graph
    from ai_extract.services.inference_runtime_service import PipelineProgress
    if run.status!='COMPLETED' or not run.structure.get('source_fingerprint'):
        raise ValueError('A completed source-grounded extraction is required')
    original=run.structure
    tree=attach_reading_streams(deepcopy(original))
    progress=PipelineProgress(run.id)
    with progress.stage('gliner_entities',pages=run.total_pages) as details:
        extracted=extract_graph_entities(tree)
        if extracted['status'] not in {'complete','empty'}:
            raise RuntimeError('GLiNER did not complete: '+str(extracted['errors']))
        extracted=enrich_document_relations(tree,extracted)
        if extracted['status'] not in {'complete','empty'}:
            raise RuntimeError('GLiNER document relation pass did not complete')
        previous=tree.get('knowledge_graph',{})
        retained=[e for e in previous.get('entities',[]) if e.get('origin')!='gliner_source_span']
        tree['knowledge_graph']=dict(extracted,entities=retained+extracted['entities'],
            relations=[r for r in previous.get('relations',[]) if r.get('origin')!='gliner_relex_source_span']+extracted.get('relations',[]),
            source_relations=[r for r in previous.get('source_relations',[]) if r.get('origin')!='gliner_relex_source_span']
                +extracted.get('source_relations',[]))
        details.update(model=extracted.get('model'),entities=len(extracted['entities']),relations=len(extracted.get('relations',[])),status=extracted['status'])
    run.structure=tree
    try:
        with progress.stage('neo4j_entities') as details:
            graph=sync_graph(run,review_structure=True)
            if graph['status']!='ready':raise RuntimeError('Neo4j enrichment unavailable: '+str(graph))
            tree['graph_index']=graph
            tree.setdefault('processing',{})['entity_enrichment']=dict(provider='gliner',model=extracted.get('model'),status=extracted['status'],entities=len(extracted['entities']),relations=len(extracted.get('relations',[])))
            layout_repository.save_run(run,['structure'])
            details.update(status='ready',nodes=graph.get('nodes'),edges=graph.get('edges'))
    except Exception:
        run.structure=original
        raise
    return run


def rebuild_structures(version_id=None):
    from ai_extract.services.document_structure_service import analyze_document_structure
    count = 0
    for run in layout_repository.completed_runs(version_id):
        run.structure = analyze_document_structure(layout_repository.structure_records(run), run.version.contract.title)
        from .document_graph_service import enrich_and_sync
        enrich_and_sync(run)
        # Old dense points may contain different leaf IDs and heading vectors.
        # Retrieval must wait for reindexing rather than use stale points.
        run.dense_index_status = 'PENDING'
        run.colpali_index_status = 'PENDING'
        layout_repository.save_run(run, ['structure', 'dense_index_status', 'colpali_index_status'])
        count += 1
    return count


class PageExtractionSession:
    def __init__(self, run):
        self.run = run
        self.page_states = []
        self.colpali_results = {}
        self.page_knowledge = []
        self.visual_tasks = {}
        self.executor = None
        self.progress = PipelineProgress(run.pk)
        self.expected_pages = None
        self.current_page = None
        self.records = []
        self.failed_pages = []
        self.visual_inputs = {}

    def __enter__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='a3-colpali-page')
        return self

    def __exit__(self, *exc):
        if self.executor is not None:
            self.executor.shutdown(wait=True, cancel_futures=True)

    def _submit_visual(self, page_number):
        if self.executor is None:
            raise RuntimeError('PageExtractionSession must be used as a context manager')
        self.visual_tasks[page_number] = self.executor.submit(self._index_visual, page_number)

    def _index_visual(self, page_number):
        from .contract_pipeline_service import PlanACollectionIndexer, IndexResult
        # ORM connections belong to their thread. Only the main thread saves
        # run status; the background branch writes its own Qdrant points.
        close_old_connections()
        try:
            with self.progress.stage('colpali', page=page_number, total_pages=self.expected_pages) as details:
                def index():
                    prepared = self.visual_inputs.get(page_number)
                    if prepared is not None:
                        run, visuals = prepared
                    else:
                        from .layout_extractor import visual_sources
                        with self.progress.stage('colpali_sources', page=page_number):
                            run = layout_repository.indexed_run(self.run)
                            visuals = list(visual_sources(run, page_number=page_number))
                    return PlanACollectionIndexer().index_colpali(run, page_number=page_number, visuals=visuals)
                result = IndexResult.capture(index)
                details.update(status=result.status, points=result.indexed_count)
                return result
        finally:
            close_old_connections()

    def start_page_image(self, page_number, image_path, width, height, *, total_pages=None):
        if self.visual_tasks or any(s.get('structure') == 'RUNNING' for s in self.page_states):
            raise RuntimeError('Finish both branches of the previous page first')
        relative = Path(image_path).resolve().relative_to(Path(settings.MEDIA_ROOT).resolve()).as_posix()
        layout_repository.persist_rendered_page(self.run, page_number, relative, width, height)
        self.expected_pages = total_pages or self.expected_pages
        self.progress.emit('render', 'completed', page=page_number, total_pages=self.expected_pages,
                           width=width, height=height)
        self.page_states.append(dict(page_number=page_number, structure='RUNNING',
                                     graph='PENDING', dense='DEFERRED', colpali='PENDING'))
        self.run.colpali_index_status = 'RUNNING'
        self._save_progress('pages')


    def fail_page(self, page_number, error):
        from .contract_pipeline_service import IndexResult
        self.failed_pages.append(dict(page_number=page_number, stage='surya', error_type=type(error).__name__))
        state = next(s for s in self.page_states if s['page_number'] == page_number)
        task = self.visual_tasks.pop(page_number, None)
        result = task.result() if task else IndexResult('SKIPPED')
        self._record_visual_result(page_number, result)
        state.update(structure='FAILED', graph='SKIPPED', error_type=type(error).__name__)
        self._save_progress('pages')
        self.progress.emit('page', 'failed_continuing', page=page_number,
                           total_pages=self.expected_pages, error_type=type(error).__name__)

    def process_page(self, page):
        from .document_graph_service import sync_graph, infer_relations
        from ai_extract.services.document_structure_service import analyze_document_structure
        run = self.run
        self.current_page = page.page_number
        with transaction.atomic():
            records, _ = layout_repository.persist_pages(run, SimpleNamespace(pages=[page]),
                                                         incremental=True, cumulative=False)
        self.records=[record for record in self.records if record['page_number']!=page.page_number]+records
        self.colpali_results.pop(page.page_number,None)
        state = next((s for s in self.page_states if s['page_number'] == page.page_number), None)
        if state is None:
            # Office sources do not have a full rendered page; their embedded
            # visuals become available only after parser persistence.
            state = dict(page_number=page.page_number, colpali='RUNNING', dense='DEFERRED')
            self.page_states.append(state)
        # Surya blocks now exist: only their confirmed figures enter ColPali.
        self._submit_visual(page.page_number)
        with self.progress.stage('structure', page=page.page_number, total_pages=self.expected_pages) as details:
            run.structure = analyze_document_structure(self.records, run.version.contract.title)
            run.structure['colpali_point_ids'] = [pid for r in self.colpali_results.values() for pid in r.point_ids]
            details.update(status=run.structure['structure_status'], chunks=len(run.structure['leaves']))
        page_tree = dict(run.structure, leaves=[leaf for leaf in run.structure['leaves'] if leaf.get('page_number') == page.page_number])
        with self.progress.stage('entities',page=page.page_number,provider=getattr(settings,'A3_ENTITY_PROVIDER','disabled')) as details:
            knowledge=infer_relations(page_tree)
            self.page_knowledge=[r for r in self.page_knowledge if r.get('page_number')!=page.page_number]
            self.page_knowledge.append(dict(knowledge,page_number=page.page_number))
            details.update(status=knowledge['status'],entities=len(knowledge.get('entities',[])),
                           sources_completed=len(knowledge.get('source_coverage',{}).get('completed_ids',[])),
                           relations=len(knowledge.get('relations',[])),errors=len(knowledge.get('errors',[])))
        run.structure['knowledge_graph'] = self._combined_knowledge()
        state.update(structure=run.structure['structure_status'],
                     entities=knowledge['status'],entity_count=len(knowledge.get('entities',[])),
                     graph='PENDING', dense='DEFERRED')
        visual_states = [(record.get('structure_metadata') or {}).get('visual_ocr_status')
                         for record in records if (record.get('structure_metadata') or {}).get('visual_ocr_status')]
        state['visual_ocr'] = dict(regions=len(visual_states),failed=visual_states.count('failed'),
                                  unreadable=sum(v in {'unreadable','partial','unresolved'} for v in visual_states))
        state['body_ocr_failed_regions']=sum(
            not (record.get('structure_metadata') or {}).get('visual_depth')
            and (record.get('structure_metadata') or {}).get('ocr_status') in {'failed','rejected','unresolved'}
            for record in records)
        run.total_pages += 1
        run.total_blocks += len(page.blocks)
        run.colpali_index_status = 'RUNNING'
        self._save_progress('pages')
        with self.progress.stage('wait_colpali', page=page.page_number):
            result = self.visual_tasks.pop(page.page_number).result()
        self._record_visual_result(page.page_number, result)
        with self.progress.stage('neo4j_page', page=page.page_number) as details:
            run.structure['graph_index'] = sync_graph(run)
            details.update(status=run.structure['graph_index']['status'])
        state['graph'] = run.structure['graph_index']['status']
        self._save_progress('pages')
        self.progress.emit('page', 'completed', page=page.page_number, total_pages=self.expected_pages,
                           blocks=len(page.blocks), graph=state['graph'], colpali=result.status, dense='DEFERRED')

    def _record_visual_result(self, page_number, result):
        from .contract_pipeline_service import IndexResult
        previous = self.colpali_results.get(page_number)
        if previous and result.status != 'COMPLETED':
            # Upserts reuse deterministic IDs. A failed retry must neither lose
            # acknowledged vectors nor count the same point twice.
            ids = tuple(sorted(set(previous.point_ids) | set(result.point_ids)))
            tracked = (len(previous.point_ids) == previous.indexed_count and
                       len(result.point_ids) == result.indexed_count)
            count = len(ids) if tracked else max(previous.indexed_count, result.indexed_count)
            result = IndexResult('PARTIAL' if count else 'FAILED', count,
                                 result.error or previous.error, ids)
        self.colpali_results[page_number] = result
        state = next(s for s in self.page_states if s['page_number'] == page_number)
        state.update(colpali=result.status, colpali_points=result.indexed_count,
                     colpali_error=result.error, colpali_attempts=state.get('colpali_attempts', 0) + 1)
        IndexResult.combine(self.colpali_results.values()).apply_to(self.run, 'colpali')
        return result

    def _retry_failed_visuals(self):
        pending = [page for page, result in self.colpali_results.items()
                   if result.status in {'FAILED', 'PARTIAL'}]
        if not pending:
            return
        self.run.colpali_index_status = 'RUNNING'
        self._save_progress('retrying_colpali')
        self.progress.emit('colpali_retry', 'started', pages=pending, max_attempts=1)
        for page_number in pending:
            with self.progress.stage('colpali_retry_page', page=page_number, attempt=2) as details:
                self._submit_visual(page_number)
                result = self._record_visual_result(page_number, self.visual_tasks.pop(page_number).result())
                details.update(status=result.status, points=result.indexed_count)
            self._save_progress('retrying_colpali')
        remaining = [page for page, result in self.colpali_results.items()
                     if result.status in {'FAILED', 'PARTIAL'}]
        self.progress.emit('colpali_retry', 'completed', pages=pending, missing_pages=remaining)

    def _save_progress(self, phase):
        self.run.structure['processing'] = dict(phase=phase, pages=self.page_states,
                                               pages_total=self.expected_pages,
                                               dense_policy='after_complete_structure',
                                               failed_pages=list(self.failed_pages),
                                               colpali_missing_pages=[page for page, result in self.colpali_results.items()
                                                                      if result.status in {'FAILED', 'PARTIAL'}],
                                               global_relations='PENDING' if phase == 'pages' else phase)
        layout_repository.save_run(self.run, ['structure', 'total_pages', 'total_blocks',
            'colpali_index_status', 'colpali_points_count', 'colpali_index_error',
            'dense_index_status', 'dense_points_count', 'dense_index_error'])

    def _combined_knowledge(self):
        results = self.page_knowledge
        return dict(model=next((r['model'] for r in results if r.get('model')),None),
            provider='gliner' if any(r.get('provider')=='gliner' for r in results) else 'source_layout',
            status='disabled' if all(r['status']=='disabled' for r in results) else 'complete' if all(r['status'] in {'complete', 'empty'} for r in results) else 'partial',
            entities=[e for r in results for e in r.get('entities', [])],
            relations=[e for r in results for e in r.get('relations', [])],
            source_relations=[e for r in results for e in r.get('source_relations',[])],
            errors=[e for r in results for e in r.get('errors', [])],
            source_coverage={key:[i for r in results for i in r.get('source_coverage',{}).get(key,[])]
                for key in ('eligible_ids','completed_ids','without_entity_ids','excluded_ocr_ids')},
            cross_page_semantics='not_inferred', validation_scope='source_alignment_not_semantic_truth')

    def finish(self):
        from .contract_pipeline_service import PlanACollectionIndexer, IndexResult
        from .document_graph_service import sync_graph
        run = self.run
        if self.visual_tasks:
            raise RuntimeError('Cannot finalize while a page is still processing')
        if not self.records and self.failed_pages:
            self._retry_failed_visuals()
            run.status = 'FAILED'
            run.error_message = 'OCR failed on every page; rendered pages and visual index retained.'
            run.completed_at = timezone.now()
            self._save_progress('finished')
            layout_repository.save_run(run, ['status', 'error_message', 'completed_at'])
            self.progress.emit('pipeline', 'partial', failed_pages=self.failed_pages, pages=0)
            return
        self._save_progress('finalizing')
        # The last cumulative tree already carries cross-page heading continuity.
        # Reconcile the complete source hierarchy and all page proposals. Text
        # relations were already inferred per page; never call Qwen or repeat
        # model inference to pretend distant cross-page semantics are verified.
        run.structure['knowledge_graph'] = self._combined_knowledge()
        run.structure['visual_graph'] = dict(status='disabled', images=[], objects=[], relations=[], text_links=[])
        # Dense text uses the completed source hierarchy.
        run.dense_index_status = 'RUNNING'
        self._save_progress('indexing_dense')
        with self.progress.stage('dense_index', pages=run.total_pages,
                                 chunks=len(run.structure.get('leaves', []))) as details:
            dense = IndexResult.capture(lambda: PlanACollectionIndexer().index_dense(run, replace_existing=False))
            dense.apply_to(run, 'dense')
            details.update(status=dense.status, points=dense.indexed_count)
        if getattr(settings,'A3_KNOWLEDGE_ENABLED',False) and getattr(settings,'A3_ENTITY_PROVIDER','disabled')=='gliner':
            from .gliner_entity_service import enrich_document_relations
            with self.progress.stage('document_relations',pages=run.total_pages,provider='gliner') as details:
                run.structure['knowledge_graph']=enrich_document_relations(run.structure,run.structure['knowledge_graph'])
                document=run.structure['knowledge_graph']['document_relations']
                details.update(status=document['status'],candidate_search=document['candidate_search'],
                               source_relations=len(run.structure['knowledge_graph']['source_relations']))
        self._retry_failed_visuals()
        IndexResult.combine(self.colpali_results.values()).apply_to(run, 'colpali')
        with self.progress.stage('neo4j_final', pages=run.total_pages, chunks=len(run.structure.get('leaves', []))) as details:
            run.structure['graph_index'] = sync_graph(run,review_structure=True)
            details['structure_review']=run.structure.get('structure_review',{}).get('counts',{})
            details.update(status=run.structure['graph_index']['status'])
        self._save_progress('finished')
        visual_missing = [s['page_number'] for s in self.page_states if
                          s.get('visual_ocr',{}).get('failed') or s.get('visual_ocr',{}).get('unreadable')]
        run.structure['processing']['visual_ocr_incomplete_pages'] = visual_missing
        body_missing=[s['page_number'] for s in self.page_states if s.get('body_ocr_failed_regions')]
        run.structure['processing']['body_ocr_incomplete_pages']=body_missing
        entity_missing=[s['page_number'] for s in self.page_states if s.get('entities') in {'partial','unavailable'}]
        run.structure['processing']['entity_incomplete_pages']=entity_missing
        run.structure['processing']['global_relations'] = dict(
            graph=run.structure.get('graph_index', {}).get('status'),
            knowledge=run.structure.get('knowledge_graph', {}).get('status'),
            visual=run.structure.get('visual_graph', {}).get('status'))
        run.structure['processing']['global_relations']['document_relations']=run.structure.get('knowledge_graph',{}).get('document_relations',{})
        review=run.structure.get('structure_review',{})
        run.structure['processing']['global_relations']['structure_review']={k:review[k] for k in ('status','counts','relations_total','errors') if k in review}
        run.status = 'FAILED' if self.failed_pages else 'COMPLETED'
        if self.failed_pages:
            run.error_message = 'OCR incomplete on pages: '+', '.join(str(p['page_number']) for p in self.failed_pages)+'. Successful pages retained; rerun reuses completed OCR cache.'
        elif visual_missing:
            run.error_message = 'Visual-region OCR incomplete on pages: '+', '.join(map(str,visual_missing))+'. Readable text retained; failed requests retry on rerun, unreadable crops remain marked.'
        if body_missing:
            run.error_message=(getattr(run,'error_message','')+'\nBody OCR incomplete on pages: '+', '.join(map(str,body_missing))+'. Failed source regions are excluded from retrieval and entities.').strip()
        if entity_missing:
            run.error_message=(getattr(run,'error_message','')+'\nEntity extraction incomplete on pages: '+', '.join(map(str,entity_missing))+'. Source text, structure and dense index retained.').strip()
        document_missing=run.structure.get('knowledge_graph',{}).get('document_relations',{}).get('status') in {'partial','unavailable'}
        if document_missing:
            run.error_message=(getattr(run,'error_message','')+'\nDocument relation analysis incomplete; source structure and local relation proposals retained.').strip()
        review_missing=review.get('status')=='partial'
        if review_missing:
            run.error_message=(getattr(run,'error_message','')+'\nStructure review incomplete; source proposals and pending review status retained.').strip()
        graph_ready = run.structure['graph_index']['status'] == 'ready'
        if not graph_ready:
            run.error_message=(getattr(run,'error_message','')+'\nNeo4j index unavailable; extracted sources and vector indexes retained.').strip()
        run.completed_at = timezone.now()
        layout_repository.save_run(run, ['structure', 'status', 'error_message', 'completed_at'])
        from .document_graph_service import cleanup_old_run_graphs
        with self.progress.stage('neo4j_cleanup') as details:
            details.update(cleanup_old_run_graphs(run))
        with self.progress.stage('artifact_cleanup') as details:
            details.update(retire_superseded_artifacts(run))
        if run.status == 'COMPLETED':
            with self.progress.stage('retrieval_index'):
                from NewIdea.repositories.contract_repository import refresh_snapshot
                refresh_snapshot(run.version)
        indexes_ready = graph_ready and run.dense_index_status == 'COMPLETED' and run.colpali_index_status in {'COMPLETED', 'SKIPPED'}
        self.progress.emit('pipeline', 'partial' if self.failed_pages else 'completed_with_source_warnings' if visual_missing or body_missing or entity_missing or document_missing or review_missing else 'completed' if indexes_ready else 'completed_with_index_errors',
                           pages=run.total_pages, blocks=run.total_blocks, indexes_ready=indexes_ready,
                           dense=run.dense_index_status, colpali=run.colpali_index_status,
                           graph=run.structure['graph_index']['status'])


def retire_superseded_artifacts(run):
    """Retire derived indexes through the pipeline, preserving original run history."""
    from .contract_pipeline_service import PlanACollectionIndexer
    if getattr(run,'status',None)!='COMPLETED':return dict(status='skipped')
    result={}
    try:
        result['page_contexts_deleted']=layout_repository.retire_old_page_contexts(run)
        result['vectors']=PlanACollectionIndexer().prune_old_run_points(run)
        result['status']='completed' if all(v in {'completed','skipped','not_created'} for v in result['vectors'].values()) else 'partial'
    except Exception as error:
        result.update(status='failed',error_type=type(error).__name__)
    run.structure.setdefault('processing',{})['artifact_cleanup']=result
    layout_repository.save_run(run,['structure'])
    return result
