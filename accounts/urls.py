from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Wizard Steps
    path('setup/personal/', views.step_personal, name='step_personal'),
    path('setup/academic/', views.step_academic, name='step_academic'),
    path('setup/location/', views.step_location, name='step_location'),
    path('setup/swap/', views.step_swap, name='step_swap'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('staff-dashboard/', views.staff_dashboard, name='staff_dashboard'),
    path('staff/mutuals/', views.admin_mutual_matches, name='admin_mutual_matches'),
    path('staff/triangles/', views.admin_triangle_matches, name='admin_triangle_matches'),
    path('staff/analytics/', views.swap_analytics, name='swap_analytics'),
    path('profile/<int:profile_id>/', views.teacher_profile, name='teacher_profile'),
    path('find-swaps/', views.find_swaps, name='find_swaps'),
]
