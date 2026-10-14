from django.contrib import admin
from .models import (
    SchoolYearTransition, PromotionProposal,
    Classe, ClassTeacher, EducationLevel, EducationLevelSubject, Enrollment, EvaluationRule,
    Evaluation, EvaluationSubject, Grade, SchoolYearLevel, Student, Subject, SubjectGroup, TeacherSubject, Teaching, Term,
    PedagogicalTrack, TrackLevel, TrackLevelSubject, SchoolYearTrack, PassageDecision, PassageDecisionLine,
)


@admin.register(EducationLevel)
class EducationLevelAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "school_type", "order", "teaching_organization", "is_exam_level", "exam_name", "allows_free_candidate", "is_active")
    list_filter = ("school_type", "is_exam_level", "allows_free_candidate", "is_active")
    search_fields = ("code", "name", "exam_name")


@admin.register(SchoolYearLevel)
class SchoolYearLevelAdmin(admin.ModelAdmin):
    list_display = ("school_year", "education_level", "is_active")
    list_filter = ("school_year", "education_level__school_type", "is_active")


@admin.register(Classe)
class ClasseAdmin(admin.ModelAdmin):
    list_display = ("name", "education_level", "pedagogical_track", "school", "school_year")
    list_filter = ("school", "school_year", "education_level__school_type", "education_level")
    search_fields = ("name", "filiere", "pedagogical_track__name", "education_level__name")


@admin.register(PedagogicalTrack)
class PedagogicalTrackAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "domain", "kind", "school_type", "order", "is_active")
    list_filter = ("school_type", "kind", "is_active")
    search_fields = ("code", "name")


@admin.register(TrackLevel)
class TrackLevelAdmin(admin.ModelAdmin):
    list_display = ("track", "education_level", "order", "is_active")
    list_filter = ("track__school_type", "track", "education_level", "is_active")


@admin.register(TrackLevelSubject)
class TrackLevelSubjectAdmin(admin.ModelAdmin):
    list_display = ("track_level", "subject", "coefficient", "weekly_hours", "role", "is_required", "order", "is_active")
    list_filter = ("track_level__track__school_type", "track_level__track", "subject", "is_active")
    search_fields = ("track_level__track__name", "track_level__education_level__name", "subject__name")


@admin.register(SchoolYearTrack)
class SchoolYearTrackAdmin(admin.ModelAdmin):
    list_display = ("school_year", "track", "is_active")
    list_filter = ("school_year", "track__school_type", "track", "is_active")


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "coefficient", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(EducationLevelSubject)
class EducationLevelSubjectAdmin(admin.ModelAdmin):
    list_display = ("education_level", "subject", "coefficient", "weekly_hours", "role", "is_required", "order", "is_active")
    list_filter = ("education_level__school_type", "education_level", "is_active")
    search_fields = ("subject__name", "subject__code", "education_level__name")


@admin.register(EvaluationRule)
class EvaluationRuleAdmin(admin.ModelAdmin):
    list_display = ("education_level", "code", "label", "weight", "max_score", "order", "is_required", "is_active")
    list_filter = ("education_level__school_type", "education_level", "is_active")
    search_fields = ("code", "label")


@admin.register(SubjectGroup)
class SubjectGroupAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    filter_horizontal = ("subjects",)


@admin.register(TeacherSubject)
class TeacherSubjectAdmin(admin.ModelAdmin):
    list_display = ("teacher", "subject", "is_active")
    list_filter = ("subject", "is_active")
    search_fields = ("teacher__last_name", "teacher__first_name", "subject__name")


@admin.register(ClassTeacher)
class ClassTeacherAdmin(admin.ModelAdmin):
    list_display = ("classe", "teacher")
    list_filter = ("classe__school", "classe__school_year", "classe__education_level__school_type")
    search_fields = ("classe__name", "teacher__last_name", "teacher__first_name")


@admin.register(Teaching)
class TeachingAdmin(admin.ModelAdmin):
    list_display = ("teacher", "subject", "classe")
    list_filter = ("subject", "classe")


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("matricule", "last_name", "first_name", "sex")
    search_fields = ("matricule", "last_name", "first_name")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "classe", "school_year", "student_type")
    list_filter = ("school_year", "student_type", "classe")
    search_fields = ("student__last_name", "student__first_name", "student__matricule")



@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = ("name", "classe", "term", "date")
    list_filter = ("term__school_year", "classe__education_level__school_type", "classe__education_level", "date")
    search_fields = ("name", "classe__name", "classe__education_level__name")


@admin.register(EvaluationSubject)
class EvaluationSubjectAdmin(admin.ModelAdmin):
    list_display = ("evaluation", "subject", "order")
    list_filter = ("evaluation__term__school_year", "subject")
    search_fields = ("evaluation__name", "subject__name")

admin.site.register(Term)
admin.site.register(Grade)


@admin.register(SchoolYearTransition)
class SchoolYearTransitionAdmin(admin.ModelAdmin):
    list_display = ("source_year", "target_year", "status", "validated_at", "applied_at")
    list_filter = ("status",)


@admin.register(PromotionProposal)
class PromotionProposalAdmin(admin.ModelAdmin):
    list_display = ("source_enrollment", "target_education_level", "target_track", "target_group", "student_type", "decision", "transition")
    list_filter = ("decision", "student_type")


@admin.register(PassageDecision)
class PassageDecisionAdmin(admin.ModelAdmin):
    list_display = ("classe", "source_year", "status", "cap_decided_at", "director_validated_at")
    list_filter = ("status", "source_year", "classe__education_level__school_type")


@admin.register(PassageDecisionLine)
class PassageDecisionLineAdmin(admin.ModelAdmin):
    list_display = ("passage", "enrollment", "proposal_decision", "cap_decision", "director_decision")
    list_filter = ("proposal_decision", "cap_decision", "director_decision")
