from django.contrib import admin
from .models import SwapProposal

@admin.register(SwapProposal)
class SwapProposalAdmin(admin.ModelAdmin):
    list_display = ('sender', 'receiver', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('sender__phone_number', 'receiver__phone_number')
