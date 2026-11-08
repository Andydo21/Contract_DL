from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models

from .parser import ref


class LegalDocument(models.Model):
    """One law, decree or circular from vbpl.vn, as listed in a `sources/<domain>.json` manifest."""
    source_id = models.CharField(max_length=64, unique=True)  # vbpl id
    number = models.CharField(max_length=64, db_index=True)  # số ký hiệu, e.g. 45/2019/QH14
    title = models.TextField()
    doc_type = models.CharField(max_length=64)
    issuer = models.CharField(max_length=255, blank=True)
    issued_on = models.DateField(null=True, blank=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)  # first day it no longer applies
    status = models.CharField(max_length=64, blank=True)
    # Set when the manifest overrides vbpl's dates or status, or knows of text that is missing.
    status_note = models.TextField(blank=True)
    gaps = models.TextField(blank=True)
    note = models.CharField(max_length=255, blank=True)
    domain = models.CharField(max_length=32, db_index=True)
    content_hash = models.CharField(max_length=64)
    parse_warnings = models.JSONField(default=list, blank=True)
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['domain', '-effective_from', 'number']

    def __str__(self):
        return self.number


class LegalRelation(models.Model):
    """A vbpl link read as "actor <effect> subject", e.g. 293/2025/NĐ-CP replaces 74/2024/NĐ-CP.

    At least one side is in the corpus; the other is kept by number so that a change made by a document outside the
    corpus is still visible.
    """
    actor_source_id = models.CharField(max_length=64, db_index=True)
    actor_number = models.CharField(max_length=64, blank=True)
    actor_title = models.TextField(blank=True)
    actor_effective_from = models.DateField(null=True, blank=True)
    effect = models.CharField(max_length=32)
    subject_source_id = models.CharField(max_length=64, db_index=True)
    subject_number = models.CharField(max_length=64, blank=True)
    label = models.CharField(max_length=128)  # vbpl's own wording

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['actor_source_id', 'effect', 'subject_source_id'], name='legal_relation_unique'),
        ]

    def __str__(self):
        return f'{self.actor_number} {self.effect} {self.subject_number}'


class LegalProvision(models.Model):
    """A clause with its points, or an article's text before its first clause (`clause` blank)."""
    document = models.ForeignKey(LegalDocument, on_delete=models.CASCADE, related_name='provisions')
    position = models.PositiveIntegerField()
    article = models.CharField(max_length=32)
    clause = models.CharField(max_length=16, blank=True)
    heading = models.TextField(blank=True)
    chapter = models.TextField(blank=True)
    section = models.TextField(blank=True)
    text = models.TextField()
    search = SearchVectorField(null=True)

    class Meta:
        ordering = ['document', 'position']
        indexes = [
            GinIndex(fields=['search'], name='legal_provision_search'),
            models.Index(fields=['document', 'article'], name='legal_provision_article'),
        ]

    def __str__(self):
        return f'{self.document.number} {self.ref}'

    @property
    def ref(self):
        return ref(self.article, self.clause)
