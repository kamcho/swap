from django.urls import path
from . import views

app_name = 'messenger'

urlpatterns = [
    path('webhook/', views.whatsapp_webhook, name='webhook'),
    path('simulator/', views.chat_simulator, name='simulator'),
    path('inbox/', views.inbox, name='inbox'),
    path('chat/<int:conversation_id>/', views.chat_view, name='chat_view'),
    path('start/<int:user_id>/', views.start_chat, name='start_chat'),
    path('block/<int:user_id>/', views.block_user, name='block_user'),
    path('report/<int:user_id>/', views.report_user, name='report_user'),
    path('bulk-onboard/', views.bulk_onboard, name='bulk_onboard'),
    path('whatsapp-admin/', views.whatsapp_admin, name='whatsapp_admin'),
    path('bulk-campaign/', views.bulk_campaign_admin, name='bulk_campaign_admin'),
]
