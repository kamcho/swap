import json
from django.core.management.base import BaseCommand
from locations.models import County, SubCounty, Ward
from counties import data

class Command(BaseCommand):
    help = 'Seed the database with counties, sub-counties, and wards'

    def handle(self, *args, **options):
        self.stdout.write('Seeding locations...')
        County.objects.all().delete()
        SubCounty.objects.all().delete()
        Ward.objects.all().delete()
        for county_name, subcounties in data.items():
            county, created = County.objects.get_or_create(name=county_name)
            if created:
                self.stdout.write(f'Created County: {county_name}')
            
            for subcounty_name, wards in subcounties.items():
                subcounty, created = SubCounty.objects.get_or_create(
                    county=county, 
                    name=subcounty_name
                )
                if created:
                    self.stdout.write(f'  Created Sub-County: {subcounty_name}')
                
                for ward_name in wards:
                    ward, created = Ward.objects.get_or_create(
                        subcounty=subcounty,
                        name=ward_name
                    )
                    if created:
                        self.stdout.write(f'    Created Ward: {ward_name}')
        
        self.stdout.write(self.style.SUCCESS('Successfully seeded locations'))
