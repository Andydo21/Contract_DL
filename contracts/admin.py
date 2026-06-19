from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Contract, ContractFile, Clause, Risk, AIAnalysis, RiskFinding, Review, AuditLog

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'role', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Custom Roles', {'fields': ('role',)}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Custom Roles', {'fields': ('role',)}),
    )

class ContractFileInline(admin.TabularInline):
    model = ContractFile
    extra = 1

class ClauseInline(admin.TabularInline):
    model = Clause
    extra = 1

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ('contract_code', 'title', 'contract_type', 'status', 'contract_value', 'start_date', 'end_date', 'created_at')
    list_filter = ('status', 'contract_type', 'created_at')
    search_fields = ('contract_code', 'title', 'contract_type')
    inlines = [ContractFileInline, ClauseInline]

@admin.register(Clause)
class ClauseAdmin(admin.ModelAdmin):
    list_display = ('clause_title', 'contract')
    list_filter = ('contract',)
    search_fields = ('clause_title', 'clause_content')

@admin.register(Risk)
class RiskAdmin(admin.ModelAdmin):
    list_display = ('risk_name', 'severity_level')
    list_filter = ('severity_level',)
    search_fields = ('risk_name', 'description')

class RiskFindingInline(admin.TabularInline):
    model = RiskFinding
    extra = 1

@admin.register(AIAnalysis)
class AIAnalysisAdmin(admin.ModelAdmin):
    list_display = ('contract', 'model_name', 'overall_score', 'created_at')
    list_filter = ('model_name', 'created_at')
    search_fields = ('contract__contract_code', 'contract__title')
    inlines = [RiskFindingInline]

@admin.register(RiskFinding)
class RiskFindingAdmin(admin.ModelAdmin):
    list_display = ('analysis', 'risk', 'risk_level')
    list_filter = ('risk_level', 'risk')
    search_fields = ('explanation', 'recommendation')

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('analysis', 'user', 'final_risk_level', 'reviewed_at')
    list_filter = ('final_risk_level', 'reviewed_at')
    search_fields = ('comment',)

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'target_model', 'target_id', 'timestamp')
    list_filter = ('action', 'target_model', 'timestamp')
    search_fields = ('user__username', 'action')
    readonly_fields = ('user', 'action', 'target_model', 'target_id', 'timestamp')
