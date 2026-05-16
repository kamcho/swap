from django.contrib import admin
from .models import WhatsAppInteraction, WhatsAppState, WhatsAppMessageLog

admin.site.register(WhatsAppInteraction)
admin.site.register(WhatsAppState)
admin.site.register(WhatsAppMessageLog)
