from django.contrib import admin

from .models import LegalDocument, LegalProvision, LegalRelation


@admin.register(LegalDocument)
class LegalDocumentAdmin(admin.ModelAdmin):
    list_display = ('number', 'doc_type', 'effective_from', 'effective_to', 'status', 'domain', 'imported_at')
    list_filter = ('domain', 'doc_type', 'status')
    search_fields = ('number', 'title')


@admin.register(LegalProvision)
class LegalProvisionAdmin(admin.ModelAdmin):
    list_display = ('document', 'article', 'clause', 'heading')
    list_filter = ('document__domain', 'document')
    search_fields = ('heading', 'text')
    exclude = ('search',)


@admin.register(LegalRelation)
class LegalRelationAdmin(admin.ModelAdmin):
    list_display = ('actor_number', 'effect', 'subject_number', 'actor_effective_from', 'label')
    list_filter = ('effect',)
    search_fields = ('actor_number', 'subject_number')
