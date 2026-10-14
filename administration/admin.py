from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import School, SchoolTypeActivation, SchoolYear, Teacher, User, OtherPersonnel


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "first_name", "last_name", "email", "is_admin", "is_prof", "is_secretary", "is_active")
    list_filter = ("is_admin", "is_prof", "is_secretary", "is_active")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("username",)


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "school_type", "active_types_display", "city", "phone", "is_active")
    list_filter = ("school_type", "type_activations__school_type", "is_active")
    search_fields = ("name", "code", "city")

    @admin.display(description="Types actifs")
    def active_types_display(self, obj):
        return ", ".join(obj.get_type_activation_display_values())


@admin.register(SchoolTypeActivation)
class SchoolTypeActivationAdmin(admin.ModelAdmin):
    list_display = ("school", "school_type", "is_active", "activated_at")
    list_filter = ("school_type", "is_active")
    search_fields = ("school__name", "school__code")


@admin.register(SchoolYear)
class SchoolYearAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "start_date", "end_date", "is_active", "is_closed")
    list_filter = ("school", "is_active", "is_closed")
    search_fields = ("name", "school__name", "school__code")


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ("employee_number", "user", "contract_type", "pedagogical_profile", "specialty", "hire_date", "is_active")
    list_filter = ("is_active", "contract_type", "pedagogical_profile", "specialty")
    search_fields = ("employee_number", "first_name", "last_name", "email")

@admin.register(OtherPersonnel)
class OtherPersonnelAdmin(admin.ModelAdmin):
    list_display = ("employee_number", "last_name", "first_name", "function", "contract_type", "phone", "is_active")
    list_filter = ("contract_type", "is_active")
    search_fields = ("employee_number", "last_name", "first_name", "function", "phone")
