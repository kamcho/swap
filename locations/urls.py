from django.urls import path
from . import views

app_name = 'locations'

urlpatterns = [
    path('api/sub-counties/', views.get_sub_counties, name='get_sub_counties'),
    path('api/wards/', views.get_wards, name='get_wards'),
]
