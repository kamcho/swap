from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

class CustomUserManager(BaseUserManager):
    def create_user(self, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError('The Phone Number field must be set')
        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(phone_number, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    phone_number = models.CharField(max_length=15, unique=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(null=True, blank=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.phone_number})"

    @property
    def is_online(self):
        if self.last_seen:
            from django.utils import timezone
            import datetime
            now = timezone.now()
            return self.last_seen > now - datetime.timedelta(minutes=5)
        return False

class Subject(models.Model):
    LEVEL_CHOICES = [
        ('JSS', 'Junior Secondary School'),
        ('SENIOR', 'Senior School'),
    ]
    name = models.CharField(max_length=100)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES)

    def __str__(self):
        return f"{self.name} ({self.get_level_display()})"
    
    class Meta:
        unique_together = ('name', 'level')

class TeacherProfile(models.Model):
    LEVEL_CHOICES = [
        ('PRIMARY', 'Primary School'),
        ('JSS', 'Junior Secondary School (JSS)'),
        ('SENIOR', 'Senior/High School'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    school_name = models.CharField(max_length=255, null=True, blank=True)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, null=True, blank=True)
    
    # Current location
    county = models.ForeignKey('locations.County', on_delete=models.SET_NULL, null=True, related_name='teachers')
    sub_county = models.ForeignKey('locations.SubCounty', on_delete=models.SET_NULL, null=True, related_name='teachers')
    ward = models.ForeignKey('locations.Ward', on_delete=models.SET_NULL, null=True, related_name='teachers')
    
    def __str__(self):
        return f"Profile of {self.user.first_name} - {self.school_name}"

    def get_completion_stats(self):
        """Calculates profile completion across 4 steps equally (25% each)."""
        steps = {
            'personal': bool(self.user.first_name and self.user.last_name),
            'academic': bool(self.school_name and self.level),
            'location': bool(self.county and self.sub_county and self.ward),
            'swap': bool(self.preferred_locations.exists()) if self.level == 'PRIMARY' else bool(self.teaching_subjects.exists() and self.preferred_locations.exists())
        }
        completed_count = sum(steps.values())
        percentage = (completed_count / 4) * 100
        
        # Determine the first missing step for the link
        next_step_url = 'accounts:step_personal'
        if not steps['personal']: next_step_url = 'accounts:step_personal'
        elif not steps['academic']: next_step_url = 'accounts:step_academic'
        elif not steps['location']: next_step_url = 'accounts:step_location'
        elif not steps['swap']: next_step_url = 'accounts:step_swap'
        
        return {
            'percentage': int(percentage),
            'steps': steps,
            'is_complete': percentage == 100,
            'next_step_url': next_step_url
        }

class PreferredLocation(models.Model):
    profile = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='preferred_locations')
    county = models.ForeignKey('locations.County', on_delete=models.CASCADE)
    sub_county = models.ForeignKey('locations.SubCounty', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.profile.user.first_name}'s preference: {self.county.name}"

class TeacherSubject(models.Model):
    profile = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='teaching_subjects')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    is_required = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.profile.user.first_name} teaches {self.subject.name} (Required: {self.is_required})"
    
    class Meta:
        unique_together = ('profile', 'subject')
