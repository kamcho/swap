from django.db.models import Q
from .models import TeacherProfile, TeacherSubject
from locations.models import County

def get_potential_matches(profile, override_counties=None):
    """
    Finds potential swap matches for a given teacher profile based on:
    1. Geographic Mutual Interest (County level)
    2. Academic Level Matching (Primary/JSS/Senior)
    3. Subject Matching (for JSS/Senior)
    """
    potential_matches = TeacherProfile.objects.filter(
        level=profile.level,
        preferred_locations__county=profile.county
    ).exclude(id=profile.id).distinct()
    
    if override_counties:
        my_pref_counties = County.objects.filter(name__in=override_counties).values_list('id', flat=True)
    else:
        my_pref_counties = profile.preferred_locations.values_list('county', flat=True)
        
    potential_matches = potential_matches.filter(county__id__in=my_pref_counties)
    
    valid_matches = []
    for match in potential_matches:
        if _subjects_compatible(profile, match):
            valid_matches.append(match)
                
    return valid_matches

def get_triangle_matches(profile, override_counties=None):
    """
    Finds 3-way swap opportunities:
    A wants B's location, B wants C's location, C wants A's location.
    """
    triangles = []
    if override_counties:
        my_pref_counties = County.objects.filter(name__in=override_counties).values_list('id', flat=True)
    else:
        my_pref_counties = profile.preferred_locations.values_list('county', flat=True)

    potential_B = TeacherProfile.objects.filter(
        level=profile.level,
        county__id__in=my_pref_counties
    ).exclude(id=profile.id)
    
    for B in potential_B:
        if not _subjects_compatible(profile, B): continue
        
        b_pref_counties = B.preferred_locations.values_list('county', flat=True)
        potential_C = TeacherProfile.objects.filter(
            level=profile.level,
            county__id__in=b_pref_counties,
            preferred_locations__county=profile.county
        ).exclude(id__in=[profile.id, B.id])
        
        for C in potential_C:
            if _subjects_compatible(B, C) and _subjects_compatible(C, profile):
                triangles.append({
                    'partner_1': B,
                    'partner_2': C
                })
                
    return triangles

def get_possible_matches(profile):
    """
    Finds matches where academic criteria are perfect, but geographic 
    interest is only one-way (they are where I want to go, but they haven't picked me).
    """
    my_pref_counties = profile.preferred_locations.values_list('county', flat=True)
    
    # Teachers who are in my preferred counties
    candidates = TeacherProfile.objects.filter(
        level=profile.level,
        county__id__in=my_pref_counties
    ).exclude(id=profile.id).distinct()
    
    possible_matches = []
    for match in candidates:
        # Check if they teach the subjects I need
        if _subjects_compatible(profile, match):
            # Exclude mutual matches (already shown in dashboard)
            if not profile.county in match.preferred_locations.values_list('county', flat=True):
                possible_matches.append(match)
                
    return possible_matches

def _subjects_compatible(p1, p2):
    """Helper to check subject rules between two profiles"""
    if p1.level == 'PRIMARY': return True
    
    req1 = set(p1.teaching_subjects.filter(is_required=True).values_list('subject_id', flat=True))
    all1 = set(p1.teaching_subjects.values_list('subject_id', flat=True))
    
    req2 = set(p2.teaching_subjects.filter(is_required=True).values_list('subject_id', flat=True))
    all2 = set(p2.teaching_subjects.values_list('subject_id', flat=True))
    
    return req1.issubset(all2) and req2.issubset(all1)
