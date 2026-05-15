import random
from django.core.management.base import BaseCommand
from accounts.models import User, TeacherProfile, PreferredLocation
from locations.models import County, SubCounty, Ward

class Command(BaseCommand):
    help = "Seed 10 primary teachers with specific swap scenarios"

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding teachers...")
        
        # Cleanup existing demo users
        User.objects.filter(phone_number__startswith="0700000").delete()
        
        # Counties we'll use
        county_names = [
            "Nairobi", "Mombasa", "Kisumu", "Nakuru", "Uasin Gishu", 
            "Kiambu", "Nyeri", "Kwale", "Garissa", "Meru"
        ]
        
        counties = {}
        for name in county_names:
            c = County.objects.filter(name__icontains=name).first()
            if not c:
                self.stdout.write(self.style.ERROR(f"County {name} not found! Run seed_locations first."))
                return
            counties[name] = c

        # Setup 10 Users
        # Format: (Phone, Current County, Preferred County, Name)
        scenarios = [
            # Triangle 1
            ("0700000001", "Nairobi", "Mombasa", "Alice"),
            ("0700000002", "Mombasa", "Kisumu", "Bob"),
            ("0700000003", "Kisumu", "Nairobi", "Charlie"),
            
            # Triangle 2
            ("0700000004", "Nakuru", "Uasin Gishu", "David"),
            ("0700000005", "Uasin Gishu", "Kiambu", "Eve"),
            ("0700000006", "Kiambu", "Nakuru", "Frank"),
            
            # Mutual 1
            ("0700000007", "Nyeri", "Kwale", "Grace"),
            ("0700000008", "Kwale", "Nyeri", "Heidi"),
            
            # Mutual 2
            ("0700000009", "Garissa", "Meru", "Ivan"),
            ("0700000010", "Meru", "Garissa", "Judy"),
        ]

        for phone, current_name, pref_name, first_name in scenarios:
            user = User.objects.create_user(
                phone_number=phone,
                password=phone,
                first_name=first_name,
                last_name="Teacher"
            )
            
            county = counties[current_name]
            sub_county = county.subcounties.first()
            ward = sub_county.wards.first()
            
            profile = TeacherProfile.objects.create(
                user=user,
                school_name=f"{current_name} Primary School",
                level="PRIMARY",
                county=county,
                sub_county=sub_county,
                ward=ward
            )
            
            # Add preference
            pref_county = counties[pref_name]
            PreferredLocation.objects.create(
                profile=profile,
                county=pref_county
            )
            
            self.stdout.write(f"Created {first_name} at {current_name} (Wants {pref_name})")

        self.stdout.write(self.style.SUCCESS("Successfully seeded 10 teachers!"))
