from django.contrib import admin
from .models import Attendance, DisciplineIncident, TeacherAttendance, OtherPersonnelAttendance

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("date", "enrollment", "school_type_display", "status", "recorded_by")
    list_filter = ("status", "date", "enrollment__classe__education_level__school_type")
    search_fields = ("enrollment__student__last_name", "enrollment__student__first_name")

@admin.register(DisciplineIncident)
class DisciplineIncidentAdmin(admin.ModelAdmin):
    list_display = ("date", "enrollment", "school_type_display", "incident_type", "severity", "resolved")
    list_filter = ("incident_type", "severity", "resolved", "date", "enrollment__classe__education_level__school_type")
    search_fields = ("enrollment__student__last_name", "enrollment__student__first_name", "description")


@admin.register(TeacherAttendance)
class TeacherAttendanceAdmin(admin.ModelAdmin):
    list_display = ("date", "teacher", "school_year", "status", "entry_time", "exit_time", "recorded_by")
    list_filter = ("status", "date", "school_year")
    search_fields = ("teacher__last_name", "teacher__first_name", "teacher__employee_number")


@admin.register(OtherPersonnelAttendance)
class OtherPersonnelAttendanceAdmin(admin.ModelAdmin):
    list_display = ("date", "personnel", "school_year", "status", "entry_time", "exit_time", "recorded_by")
    list_filter = ("status", "date", "school_year")
    search_fields = ("personnel__last_name", "personnel__first_name", "personnel__employee_number")
