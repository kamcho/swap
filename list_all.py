import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TscSwap.settings')
django.setup()

from accounts.models import User

for u in User.objects.all():
    print(f"{u.id}: {u.first_name} {u.last_name} ({u.phone_number})")
    try:
        p = u.profile
        print(f"  Station: {p.county.name if p.county else 'None'}")
        print(f"  Prefs: {[pl.county.name for pl in p.preferred_locations.all()]}")
    except:
        print("  No profile found.")
