# AI Extract & Summarize App

# Application-owned Neo4j types; model output never supplies Cypher identifiers.
SEMANTIC_RELATIONS = {name: name.upper() for name in (
    'references', 'defines', 'obligates', 'depends_on', 'part_of', 'describes',
    'applies_to', 'has_amount', 'has_deadline', 'pays_to')}
SEMANTIC_EDGE_TYPES = tuple(SEMANTIC_RELATIONS.values())
STRUCTURE_REVIEW_SCHEMA = 'surya-gliner-review-v1'
