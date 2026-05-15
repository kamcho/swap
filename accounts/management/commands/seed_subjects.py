from django.core.management.base import BaseCommand
from accounts.models import Subject

class Command(BaseCommand):
    help = 'Seeds the database with teaching subjects'

    def handle(self, *args, **kwargs):
        jss_subjects = [
            "Mathematics", "English", "Kiswahili", "Integrated Science", 
            "Social Studies", "Business Studies", "Agriculture", 
            "Pre-Technical Studies", "Health Education", "Life Skills Education"
        ]
        
        senior_subjects = [
            "Mathematics", "English", "Kiswahili", "Biology", "Chemistry", 
            "Physics", "History", "Geography", "CRE", "IRE", "Agriculture", 
            "Business Studies", "Computer Studies", "Home Science", "Art and Design"
        ]

        for sub in jss_subjects:
            Subject.objects.get_or_create(name=sub, level='JSS')
            
        for sub in senior_subjects:
            Subject.objects.get_or_create(name=sub, level='SENIOR')

        self.stdout.write(self.style.SUCCESS('Successfully seeded subjects for JSS and Senior School.'))
