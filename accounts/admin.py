from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Subject, TeacherProfile, TeacherSubject, PreferredLocation

class UserAdmin(BaseUserAdmin):
    list_display = ('phone_number', 'first_name', 'last_name', 'email', 'is_staff')
    list_filter = ('is_staff', 'is_superuser', 'is_active')
    fieldsets = (
        (None, {'fields': ('phone_number', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    search_fields = ('phone_number', 'first_name', 'last_name', 'email')
    ordering = ('phone_number',)
    filter_horizontal = ('groups', 'user_permissions',)

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'level')
    list_filter = ('level',)
    search_fields = ('name',)

class TeacherSubjectInline(admin.TabularInline):
    model = TeacherSubject
    fields = ('subject', 'is_required')
    extra = 1
    max_num = 2

class PreferredLocationInline(admin.TabularInline):
    model = PreferredLocation
    extra = 1

@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'school_name', 'level', 'county')
    list_filter = ('level', 'county')
    search_fields = ('user__first_name', 'user__last_name', 'school_name')
    inlines = [TeacherSubjectInline, PreferredLocationInline]

admin.site.register(User, UserAdmin)
