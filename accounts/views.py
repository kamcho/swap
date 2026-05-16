from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .forms import (
    CustomUserCreationForm, CustomAuthenticationForm, 
    PersonalInfoForm, AcademicInfoForm, LocationInfoForm
)
from .models import User, TeacherProfile, TeacherSubject, PreferredLocation, Subject

def signup_view(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            TeacherProfile.objects.create(user=user)
            return redirect('accounts:step_personal')
    else:
        form = CustomUserCreationForm()
    return render(request, 'accounts/signup.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = CustomAuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('accounts:dashboard')
    else:
        form = CustomAuthenticationForm()
    return render(request, 'accounts/login.html', {'form': form})

def logout_view(request):
    if request.method == 'POST':
        logout(request)
        return redirect('core:landing')
    return render(request, 'accounts/logout_confirm.html')

@login_required
def step_personal(request):
    profile, created = TeacherProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        form = PersonalInfoForm(request.POST, instance=profile)
        if form.is_valid():
            request.user.first_name = form.cleaned_data['first_name']
            request.user.last_name = form.cleaned_data['last_name']
            request.user.save()
            form.save()
            return redirect('accounts:step_academic')
    else:
        form = PersonalInfoForm(instance=profile, initial={
            'first_name': request.user.first_name,
            'last_name': request.user.last_name
        })
    return render(request, 'accounts/wizard/step_personal.html', {'form': form})

@login_required
def step_academic(request):
    profile = request.user.profile
    # Restriction: Non-staff cannot change academic info once set
    if not request.user.is_staff and profile.school_name and profile.level:
        return redirect('accounts:step_swap')
        
    if request.method == 'POST':
        form = AcademicInfoForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            return redirect('accounts:step_location')
    else:
        form = AcademicInfoForm(instance=profile)
    return render(request, 'accounts/wizard/step_academic.html', {'form': form})

@login_required
def step_location(request):
    profile = request.user.profile
    # Restriction: Non-staff cannot change location info once set
    if not request.user.is_staff and profile.county:
        return redirect('accounts:step_swap')

    if request.method == 'POST':
        form = LocationInfoForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            return redirect('accounts:step_swap')
    else:
        form = LocationInfoForm(instance=profile)
    return render(request, 'accounts/wizard/step_location.html', {'form': form})

@login_required
def step_swap(request):
    profile = request.user.profile
    if request.method == 'POST':
        selected_subjects = request.POST.getlist('subjects')
        profile.teaching_subjects.all().delete()
        for sub_id in selected_subjects[:2]:
            subject = Subject.objects.get(id=sub_id)
            TeacherSubject.objects.create(profile=profile, subject=subject)
            
        pref_counties = request.POST.getlist('pref_county[]')
        pref_sub_counties = request.POST.getlist('pref_sub_county[]')
        
        profile.preferred_locations.all().delete()
        from locations.models import County, SubCounty
        
        for i in range(len(pref_counties)):
            county_id = pref_counties[i]
            if not county_id: continue
            sub_county_id = pref_sub_counties[i] if i < len(pref_sub_counties) else None
            county = County.objects.get(id=county_id)
            sub_county = None
            if sub_county_id:
                sub_county = SubCounty.objects.get(id=sub_county_id)
            PreferredLocation.objects.create(profile=profile, county=county, sub_county=sub_county)
            
        return redirect('accounts:dashboard')
    
    subjects = Subject.objects.filter(level=profile.level)
    from locations.models import County
    counties = County.objects.all()
    return render(request, 'accounts/wizard/step_swap.html', {'profile': profile, 'subjects': subjects, 'counties': counties})

@login_required
def dashboard(request):
    profile, created = TeacherProfile.objects.get_or_create(user=request.user)
    
    # If the profile is brand new or missing essential info, redirect to setup
    if not profile.school_name or not profile.county:
        return redirect('accounts:step_personal')

    from .services import get_potential_matches, get_triangle_matches
    matches = get_potential_matches(profile)
    triangles = get_triangle_matches(profile)
    return render(request, 'accounts/dashboard.html', {
        'profile': profile, 
        'potential_matches': matches, 
        'triangle_matches': triangles
    })

@login_required
def teacher_profile(request, profile_id):
    profile = get_object_or_404(TeacherProfile, id=profile_id)
    
    # If viewing own profile OR if viewer is staff
    can_see_private = (request.user == profile.user or request.user.is_staff)
    conversations = []
    whatsapp_logs = []
    
    if can_see_private:
        conversations = profile.user.conversations.all().prefetch_related('messages', 'participants').order_by('-updated_at')
        from messenger.models import WhatsAppInteraction
        whatsapp_logs = WhatsAppInteraction.objects.filter(phone_number__icontains=profile.user.phone_number[-9:]).order_by('-created_at')[:10]

    return render(request, 'accounts/teacher_profile.html', {
        'target_profile': profile,
        'can_see_private': can_see_private,
        'conversations': conversations,
        'whatsapp_logs': whatsapp_logs
    })

@login_required
def swap_analytics(request):
    if not request.user.is_staff:
        return redirect('accounts:dashboard')
    
    from django.db.models import Count
    from locations.models import County
    from .models import TeacherProfile, TeacherSubject, Subject, PreferredLocation
    
    level = request.GET.get('level', 'PRIMARY')
    
    # Base query
    profiles = TeacherProfile.objects.filter(level=level)
    
    # 1. Top Current Counties
    top_current = profiles.values('county__name').annotate(count=Count('id')).order_by('-count')[:10]
    
    # 2. Top Preferred Counties
    top_preferred = PreferredLocation.objects.filter(profile__level=level).values('county__name').annotate(count=Count('id')).order_by('-count')[:10]
    
    # 3. Top Subjects (Only for JSS/Senior)
    top_subjects = []
    if level in ['JSS', 'SENIOR']:
        top_subjects = TeacherSubject.objects.filter(profile__level=level).values('subject__name').annotate(count=Count('id')).order_by('-count')[:10]
        
    # 4. Level Distribution for Sidebar/Tabs
    all_levels = TeacherProfile.objects.values('level').annotate(count=Count('id'))
    
    context = {
        'selected_level': level,
        'top_current': top_current,
        'top_preferred': top_preferred,
        'top_subjects': top_subjects,
        'all_levels': all_levels,
    }
    return render(request, 'accounts/swap_analytics.html', context)

@login_required
def staff_dashboard(request):
    if not request.user.is_staff:
        return redirect('accounts:dashboard')
        
    from .services import get_potential_matches, get_triangle_matches
    from locations.models import County
    
    teachers = TeacherProfile.objects.all().select_related('user', 'county').prefetch_related('preferred_locations__county')
    
    # Search
    q = request.GET.get('q', '')
    level = request.GET.get('level', '')
    county_id = request.GET.get('county', '')
    
    if q:
        teachers = teachers.filter(Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q) | Q(user__phone_number__icontains=q))
    if level:
        teachers = teachers.filter(level=level)
    if county_id:
        teachers = teachers.filter(county_id=county_id)

    total_users = teachers.count()
    level_stats = {
        'PRIMARY': TeacherProfile.objects.filter(level='PRIMARY').count(),
        'JSS': TeacherProfile.objects.filter(level='JSS').count(),
        'SENIOR': TeacherProfile.objects.filter(level='SENIOR').count(),
    }
    
    # Calculate global matches (Expensive but fine for Demo)
    all_teachers = TeacherProfile.objects.all()
    mutual_matches_count = 0
    triangle_matches_count = 0
    seen_pairs = set()
    for t in all_teachers:
        m_matches = get_potential_matches(t)
        for m in m_matches:
            pair = tuple(sorted((t.id, m.id)))
            if pair not in seen_pairs:
                mutual_matches_count += 1
                seen_pairs.add(pair)
        triangle_matches_count += len(get_triangle_matches(t))
    
    triangle_matches_count = triangle_matches_count // 3
    counties = County.objects.all()

    return render(request, 'accounts/admin_dashboard.html', {
        'total_users': total_users,
        'level_stats': level_stats,
        'mutual_matches_count': mutual_matches_count,
        'triangle_matches_count': triangle_matches_count,
        'teachers': teachers,
        'counties': counties,
        'q': q,
        'selected_level': level,
        'selected_county': county_id
    })

@login_required
def admin_mutual_matches(request):
    if not request.user.is_staff: return redirect('accounts:dashboard')
    from .services import get_potential_matches
    teachers = TeacherProfile.objects.all()
    all_mutuals = []
    seen_pairs = set()
    for t in teachers:
        matches = get_potential_matches(t)
        for m in matches:
            pair = tuple(sorted((t.id, m.id)))
            if pair not in seen_pairs:
                all_mutuals.append((t, m))
                seen_pairs.add(pair)
    return render(request, 'accounts/admin_mutual_matches.html', {'matches': all_mutuals})

@login_required
def admin_triangle_matches(request):
    if not request.user.is_staff: return redirect('accounts:dashboard')
    from .services import get_triangle_matches
    teachers = TeacherProfile.objects.all()
    all_triangles = []
    # This is expensive, but for a demo it works.
    # Triangle loops are usually found 3 times (A-B-C, B-C-A, C-A-B).
    # We should deduplicate.
    seen_loops = set()
    for t in teachers:
        loops = get_triangle_matches(t)
        for loop in loops:
            ids = sorted([t.id, loop['partner_1'].id, loop['partner_2'].id])
            loop_key = tuple(ids)
            if loop_key not in seen_loops:
                all_triangles.append({
                    't1': t,
                    't2': loop['partner_1'],
                    't3': loop['partner_2']
                })
                seen_loops.add(loop_key)
    return render(request, 'accounts/admin_triangle_matches.html', {'triangles': all_triangles})

@login_required
def find_swaps(request):
    profile, created = TeacherProfile.objects.get_or_create(user=request.user)
    if not profile.school_name or not profile.county:
        return redirect('accounts:step_personal')
        
    from .services import get_potential_matches, get_triangle_matches, get_possible_matches, _subjects_compatible
    from locations.models import County
    
    county_ids = request.GET.getlist('county')
    
    # Base results always calculated for preference checking
    mutual_base = get_potential_matches(profile)
    triangles_base = get_triangle_matches(profile)
    possible_base = get_possible_matches(profile)
    
    if county_ids:
        # Explicit search
        candidates = TeacherProfile.objects.filter(
            level=profile.level,
            county_id__in=county_ids
        ).exclude(id=profile.id).distinct()
        
        possible = []
        for match in candidates:
            if _subjects_compatible(profile, match):
                possible.append(match)
        
        mutual = [m for m in mutual_base if str(m.county_id) in county_ids]
        triangles = [t for t in triangles_base if str(t['partner_1'].county_id) in county_ids or str(t['partner_2'].county_id) in county_ids]
        
        # Deduplicate
        m_ids = [m.id for m in mutual]
        possible = [p for p in possible if p.id not in m_ids]
    else:
        mutual = mutual_base
        triangles = triangles_base
        possible = possible_base

    counties = County.objects.all()
    user_pref_ids = list(profile.preferred_locations.values_list('county_id', flat=True))
    
    # Check if they are searching for something OTHER than their preferences
    is_searching_custom = False
    if county_ids:
        search_set = set(map(int, county_ids))
        pref_set = set(user_pref_ids)
        if search_set != pref_set:
            is_searching_custom = True

    return render(request, 'accounts/find_swaps.html', {
        'profile': profile, 
        'mutual': mutual, 
        'triangles': triangles, 
        'possible': possible,
        'counties': counties,
        'selected_counties': [int(cid) for cid in county_ids],
        'user_pref_ids': user_pref_ids,
        'is_searching_custom': is_searching_custom
    })
