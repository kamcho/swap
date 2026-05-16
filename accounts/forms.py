from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import authenticate
from .models import User, TeacherProfile, Subject
from django.core.validators import RegexValidator

class CustomUserCreationForm(forms.ModelForm):
    pin = forms.CharField(
        label="PIN",
        max_length=20,
        widget=forms.PasswordInput(attrs={'placeholder': 'Enter PIN'}),
    )
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'placeholder': 'Email (Optional)'}))
    phone_number = forms.CharField(widget=forms.TextInput(attrs={'placeholder': 'Phone Number'}))

    class Meta:
        model = User
        fields = ('phone_number', 'email')

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number')
        if phone:
            phone = str(phone).strip().replace(" ", "").replace("+", "")
            if phone.startswith('0') and len(phone) == 10:
                phone = "254" + phone[1:]
        return phone

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["pin"])
        if commit:
            user.save()
        return user

class CustomAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label="Phone Number", widget=forms.TextInput(attrs={'placeholder': 'Enter your phone number'}))
    password = forms.CharField(label="PIN", widget=forms.PasswordInput(attrs={'placeholder': 'Enter PIN'}))

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            # Clean the input
            raw_phone = str(username).strip().replace(" ", "").replace("+", "")
            
            # Generate variations
            variations = []
            if raw_phone.startswith('254') and len(raw_phone) == 12:
                variations = [raw_phone, "0" + raw_phone[3:]]
            elif raw_phone.startswith('0') and len(raw_phone) == 10:
                variations = ["254" + raw_phone[1:], raw_phone]
            else:
                variations = [raw_phone]

            # Try authenticating with each variation
            self.user_cache = None
            for v in variations:
                self.user_cache = authenticate(self.request, username=v, password=password)
                if self.user_cache:
                    break
            
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data

class PersonalInfoForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30, widget=forms.TextInput(attrs={'placeholder': 'First Name'}))
    last_name = forms.CharField(max_length=30, widget=forms.TextInput(attrs={'placeholder': 'Last Name'}))
    
    class Meta:
        model = TeacherProfile
        fields = []

class AcademicInfoForm(forms.ModelForm):
    class Meta:
        model = TeacherProfile
        fields = ('school_name', 'level')

class LocationInfoForm(forms.ModelForm):
    class Meta:
        model = TeacherProfile
        fields = ('county', 'sub_county', 'ward')
