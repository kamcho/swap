from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('api/chatbot/', views.chatbot, name='chatbot'),
    path('privacy-policy/', views.privacy_policy, name='privacy_policy'),
]
