from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from pedagogie.models import Enrollment


class Attendance(models.Model):
    """État de présence quotidien d'une inscription scolaire."""

    STATUS_CHOICES = [
        ("PRESENT", "Présent"),
        ("ABSENT", "Absent"),
        ("LATE", "Retard"),
    ]

    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="attendance_records")
    date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=7, choices=STATUS_CHOICES, default="PRESENT")
    is_justified = models.BooleanField(default=False, verbose_name="Justification")
    justification_note = models.CharField(max_length=255, blank=True, verbose_name="Motif / justificatif")
    late_minutes = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Durée du retard (minutes)")
    note = models.CharField(max_length=255, blank=True, verbose_name="Observation")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_records",
    )

    @property
    def school_type(self):
        return self.enrollment.classe.education_level.school_type

    @property
    def school_type_display(self):
        return self.enrollment.classe.education_level.get_school_type_display()

    def clean(self):
        super().clean()
        if self.enrollment_id and self.date:
            year = self.enrollment.school_year
            if year.start_date and self.date < year.start_date:
                raise ValidationError({"date": "La date est antérieure au début de l'année scolaire."})
            if year.end_date and self.date > year.end_date:
                raise ValidationError({"date": "La date est postérieure à la fin de l'année scolaire."})

        # Une absence comme un retard peuvent être justifiés. La justification
        # reste sans effet pour un élève présent.
        if self.status == "PRESENT" and self.is_justified:
            raise ValidationError({"is_justified": "Un élève présent ne peut pas être marqué comme justifié."})

        if self.status == "LATE":
            if not self.late_minutes or self.late_minutes <= 0:
                raise ValidationError({"late_minutes": "Indiquez une durée de retard supérieure à zéro."})
        elif self.late_minutes:
            raise ValidationError({"late_minutes": "La durée du retard ne s'applique qu'à un retard."})

    def save(self, *args, **kwargs):
        # Une présence journalière est un enregistrement de constat : une
        # fois enregistrée, elle ne peut plus être modifiée. La correction
        # d'une erreur doit passer par un mécanisme administratif dédié,
        # distinct de la saisie quotidienne.
        if self.pk:
            raise ValidationError("Une présence déjà enregistrée ne peut plus être modifiée.")
        self.full_clean()
        return super().save(*args, **kwargs)

    class Meta:
        ordering = ["-date", "enrollment__student__last_name"]
        constraints = [
            models.UniqueConstraint(fields=["enrollment", "date"], name="unique_attendance_day"),
        ]
        # Historique et tableau de bord filtrent par date : sans index, chaque
        # consultation parcourt toutes les présences de l'année.
        indexes = [models.Index(fields=["date"], name="attendance_date_idx")]
        verbose_name = "Présence"
        verbose_name_plural = "Présences"


class TeacherAttendance(models.Model):
    """Présence quotidienne d'un enseignant pour une année scolaire.

    Le modèle reste volontairement neutre sur le mode de pointage : les
    modalités concrètes d'enregistrement seront ajoutées séparément. Il
    conserve déjà les horaires d'entrée/sortie nécessaires aux permanents
    comme aux vacataires.
    """

    STATUS_CHOICES = [
        ("PRESENT", "Présent"),
        ("ABSENT", "Absent"),
        ("LATE", "Retard"),
    ]

    teacher = models.ForeignKey(
        "administration.Teacher",
        on_delete=models.CASCADE,
        related_name="attendance_records",
        verbose_name="Enseignant",
    )
    school_year = models.ForeignKey(
        "administration.SchoolYear",
        on_delete=models.CASCADE,
        related_name="teacher_attendance_records",
        verbose_name="Année scolaire",
    )
    date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=7, choices=STATUS_CHOICES, default="PRESENT")
    entry_time = models.TimeField(null=True, blank=True, verbose_name="Heure d'entrée")
    exit_time = models.TimeField(null=True, blank=True, verbose_name="Heure de sortie")
    late_minutes = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Durée du retard (minutes)")
    note = models.CharField(max_length=255, blank=True, verbose_name="Observation")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teacher_attendance_records",
    )

    def clean(self):
        super().clean()
        if self.school_year_id and self.date:
            if self.school_year.start_date and self.date < self.school_year.start_date:
                raise ValidationError({"date": "La date est antérieure au début de l'année scolaire."})
            if self.school_year.end_date and self.date > self.school_year.end_date:
                raise ValidationError({"date": "La date est postérieure à la fin de l'année scolaire."})
        if self.status == "LATE":
            if not self.late_minutes or self.late_minutes <= 0:
                raise ValidationError({"late_minutes": "Indiquez une durée de retard supérieure à zéro."})
        elif self.late_minutes:
            raise ValidationError({"late_minutes": "La durée du retard ne s'applique qu'à un retard."})
        if self.entry_time and self.exit_time and self.exit_time < self.entry_time:
            raise ValidationError({"exit_time": "L'heure de sortie doit être postérieure à l'heure d'entrée."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    class Meta:
        ordering = ["-date", "teacher__last_name", "teacher__first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "school_year", "date"],
                name="unique_teacher_attendance_day",
            ),
        ]
        verbose_name = "Présence enseignant"
        verbose_name_plural = "Présences enseignants"


class OtherPersonnelAttendance(models.Model):
    """Présence quotidienne d'un membre de l'autre personnel, pour une année scolaire.

    Symétrique de TeacherAttendance : mêmes champs, même logique, appliqués
    au personnel non enseignant (administratif, surveillance, entretien...).
    """

    STATUS_CHOICES = [
        ("PRESENT", "Présent"),
        ("ABSENT", "Absent"),
        ("LATE", "Retard"),
    ]

    personnel = models.ForeignKey(
        "administration.OtherPersonnel",
        on_delete=models.CASCADE,
        related_name="attendance_records",
        verbose_name="Personnel",
    )
    school_year = models.ForeignKey(
        "administration.SchoolYear",
        on_delete=models.CASCADE,
        related_name="other_personnel_attendance_records",
        verbose_name="Année scolaire",
    )
    date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=7, choices=STATUS_CHOICES, default="PRESENT")
    entry_time = models.TimeField(null=True, blank=True, verbose_name="Heure d'entrée")
    exit_time = models.TimeField(null=True, blank=True, verbose_name="Heure de sortie")
    late_minutes = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Durée du retard (minutes)")
    note = models.CharField(max_length=255, blank=True, verbose_name="Observation")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="other_personnel_attendance_records",
    )

    def clean(self):
        super().clean()
        if self.school_year_id and self.date:
            if self.school_year.start_date and self.date < self.school_year.start_date:
                raise ValidationError({"date": "La date est antérieure au début de l'année scolaire."})
            if self.school_year.end_date and self.date > self.school_year.end_date:
                raise ValidationError({"date": "La date est postérieure à la fin de l'année scolaire."})
        if self.status == "LATE":
            if not self.late_minutes or self.late_minutes <= 0:
                raise ValidationError({"late_minutes": "Indiquez une durée de retard supérieure à zéro."})
        elif self.late_minutes:
            raise ValidationError({"late_minutes": "La durée du retard ne s'applique qu'à un retard."})
        if self.entry_time and self.exit_time and self.exit_time < self.entry_time:
            raise ValidationError({"exit_time": "L'heure de sortie doit être postérieure à l'heure d'entrée."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    class Meta:
        ordering = ["-date", "personnel__last_name", "personnel__first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["personnel", "school_year", "date"],
                name="unique_other_personnel_attendance_day",
            ),
        ]
        verbose_name = "Présence autre personnel"
        verbose_name_plural = "Présences autre personnel"


class DisciplineIncident(models.Model):
    TYPE_CHOICES = [
        ("DISCIPLINE", "Discipline"),
        ("MERIT", "Mérite"),
        ("SANCTION", "Sanction"),
        ("OTHER", "Autre"),
    ]
    SEVERITY_CHOICES = [
        ("LOW", "Faible"),
        ("MEDIUM", "Moyenne"),
        ("HIGH", "Élevée"),
    ]

    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="discipline_incidents")
    date = models.DateField(default=timezone.localdate)
    incident_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="DISCIPLINE")
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default="LOW")
    description = models.TextField()
    action = models.CharField(max_length=255, blank=True)
    resolved = models.BooleanField(default=False)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discipline_records",
    )

    @property
    def school_type(self):
        return self.enrollment.classe.education_level.school_type

    @property
    def school_type_display(self):
        return self.enrollment.classe.education_level.get_school_type_display()

    def clean(self):
        super().clean()
        if self.enrollment_id and self.date:
            year = self.enrollment.school_year
            if year.start_date and self.date < year.start_date:
                raise ValidationError({"date": "La date est antérieure au début de l'année scolaire."})
            if year.end_date and self.date > year.end_date:
                raise ValidationError({"date": "La date est postérieure à la fin de l'année scolaire."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name = "Événement de vie scolaire"
        verbose_name_plural = "Événements de vie scolaire"


# --------------------------------------------------------------------------
# Pointage par QR code (retours V8-8) : un téléphone scanne hors connexion
# les badges du personnel (entrées et sorties) et les cartes des élèves
# (présence), puis synchronise avec KIS (réseau local ou fichier).
# --------------------------------------------------------------------------
def _new_pointage_key():
    import secrets
    return secrets.token_urlsafe(18)


class PointageConfig(models.Model):
    """Réglages du pointage (une seule ligne)."""

    api_key = models.CharField(max_length=64, default=_new_pointage_key, verbose_name="Clé des téléphones de pointage")
    staff_start_time = models.TimeField(null=True, blank=True, verbose_name="Heure d'arrivée attendue du personnel",
                                        help_text="Facultatif : une entrée après cette heure est comptée comme un retard.")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Réglages du pointage"

    @classmethod
    def get(cls):
        obj = cls.objects.order_by("id").first()
        return obj or cls.objects.create()

    def regenerate_key(self):
        self.api_key = _new_pointage_key()
        self.save(update_fields=["api_key", "updated_at"])


class PointageScan(models.Model):
    """Un passage scanné par un téléphone (conservé tel quel, même s'il n'a pas pu être reconnu)."""

    class Kind(models.TextChoices):
        IN = "IN", "Entrée"
        OUT = "OUT", "Sortie"

    class Person(models.TextChoices):
        STUDENT = "student", "Élève"
        TEACHER = "teacher", "Enseignant"
        STAFF = "staff", "Personnel"
        UNKNOWN = "unknown", "Inconnu"

    device_id = models.CharField(max_length=64, verbose_name="Téléphone")
    scan_id = models.CharField(max_length=64, verbose_name="N° du passage sur le téléphone")
    code = models.CharField(max_length=255, verbose_name="Code lu")
    kind = models.CharField(max_length=3, choices=Kind.choices, default=Kind.IN, verbose_name="Sens")
    scanned_at = models.DateTimeField(verbose_name="Date et heure du passage")
    person_type = models.CharField(max_length=10, choices=Person.choices, default=Person.UNKNOWN)
    student = models.ForeignKey("pedagogie.Student", on_delete=models.CASCADE, null=True, blank=True, related_name="pointage_scans")
    teacher = models.ForeignKey("administration.Teacher", on_delete=models.CASCADE, null=True, blank=True, related_name="pointage_scans")
    personnel = models.ForeignKey("administration.OtherPersonnel", on_delete=models.CASCADE, null=True, blank=True, related_name="pointage_scans")
    result = models.CharField(max_length=255, blank=True, verbose_name="Résultat")
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-scanned_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["device_id", "scan_id"], name="unique_pointage_scan")]
        indexes = [models.Index(fields=["scanned_at"], name="pointage_scanned_idx")]
        verbose_name = "Passage pointé"
        verbose_name_plural = "Passages pointés"

    @property
    def person_label(self):
        person = self.student or self.teacher or self.personnel
        if not person:
            return "Badge inconnu"
        return f"{person.last_name} {person.first_name}"
