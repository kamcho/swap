from django.http import JsonResponse
from .models import SubCounty, Ward

def get_sub_counties(request):
    county_id = request.GET.get('county_id')
    sub_counties = SubCounty.objects.filter(county_id=county_id).values('id', 'name')
    return JsonResponse(list(sub_counties), safe=False)

def get_wards(request):
    sub_county_id = request.GET.get('sub_county_id')
    wards = Ward.objects.filter(subcounty_id=sub_county_id).values('id', 'name')
    return JsonResponse(list(wards), safe=False)
