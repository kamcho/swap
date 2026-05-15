import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TscSwap.settings')
django.setup()

from accounts.models import User

phones = ['254742134431', '0700000007', '0742134434']
for p in phones:
    u = User.objects.filter(phone_number__icontains=p[-9:]).first()
    if u:
        print(f"User: {u.first_name} {u.last_name} ({u.phone_number})")
        prof = u.profile
        print(f"  Station: {prof.county.name if prof.county else 'None'}")
        print(f"  Prefs: {[pl.county.name for pl in prof.preferred_locations.all()]}")
    else:
        print(f"User with phone matching {p} not found.")
