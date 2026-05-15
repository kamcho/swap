from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
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

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["pin"])
        if commit:
            user.save()
        return user

class CustomAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label="Phone Number", widget=forms.TextInput(attrs={'placeholder': 'Enter your phone number'}))
    password = forms.CharField(label="PIN", widget=forms.PasswordInput(attrs={'placeholder': 'Enter PIN'}))

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
