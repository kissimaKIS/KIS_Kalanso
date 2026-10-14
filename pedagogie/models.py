from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone

from administration.models import School, SchoolYear, Teacher
from .bulletin_appreciations import appreciation_for


class EducationLevel(models.Model):
    """Niveau pédagogique du référentiel KIS, indépendant des classes ouvertes."""

    class TeachingOrganization(models.TextChoices):
        CLASS_BASED = "class_based", "Organisation centrée sur la classe"
        SUBJECT_BASED = "subject_based", "Organisation par matière"
        HYBRID = "hybrid", "Organisation mixte"

    code = models.CharField(max_length=30, unique=True, verbose_name="Code")
    name = models.CharField(max_length=100, verbose_name="Niveau")
    school_type = models.CharField(max_length=30, choices=School.SchoolType.choices, verbose_name="Type d'établissement")
    order = models.PositiveSmallIntegerField(default=1, verbose_name="Ordre")
    is_exam_level = models.BooleanField(default=False, verbose_name="Classe d'examen")
    exam_name = models.CharField(max_length=50, blank=True, verbose_name="Examen")
    allows_free_candidate = models.BooleanField(default=False, verbose_name="Autorise candidat libre")
    teaching_organization = models.CharField(
        max_length=20,
        choices=TeachingOrganization.choices,
        default=TeachingOrganization.SUBJECT_BASED,
        verbose_name="Organisation pédagogique",
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        ordering = ["school_type", "order", "id"]
        verbose_name = "Niveau pédagogique"
        verbose_name_plural = "Niveaux pédagogiques"
        constraints = [
        ]

    def clean(self):
        if self.is_exam_level and not self.exam_name:
            raise ValidationError({"exam_name": "Le nom de l'examen est obligatoire pour un niveau d'examen."})
        if not self.is_exam_level and self.allows_free_candidate:
            raise ValidationError("Le statut candidat libre est réservé aux niveaux d'examen.")

    def __str__(self):
        return self.name


class SchoolYearLevel(models.Model):
    """Niveaux du référentiel proposés pour une année scolaire donnée."""

    school_year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE, related_name="configured_levels")
    education_level = models.ForeignKey(EducationLevel, on_delete=models.PROTECT, related_name="school_year_configurations")
    is_active = models.BooleanField(default=True, verbose_name="Ouvert dans l'établissement")

    class Meta:
        ordering = ["education_level__order"]
        verbose_name = "Niveau de l'année scolaire"
        verbose_name_plural = "Niveaux de l'année scolaire"
        constraints = [
            models.UniqueConstraint(fields=["school_year", "education_level"], name="unique_school_year_level"),
        ]

    def clean(self):
        if not self.school_year.school.has_school_type(self.education_level.school_type):
            raise ValidationError("Le niveau ne correspond pas à un type d'enseignement activé dans l'établissement.")

    def __str__(self):
        return f"{self.education_level.name} — {self.school_year.name}"


class Subject(models.Model):
    code = models.CharField(max_length=30, unique=True, verbose_name="Code")
    name = models.CharField(max_length=100, unique=True, verbose_name="Matière")
    coefficient = models.DecimalField(max_digits=5, decimal_places=2, default=1, verbose_name="Coefficient par défaut")
    is_active = models.BooleanField(default=True, verbose_name="Active")

    class Meta:
        ordering = ["name"]
        verbose_name = "Matière"
        verbose_name_plural = "Matières"

    def __str__(self):
        return self.name


class EducationLevelSubject(models.Model):
    """Association référentielle matière ↔ niveau.

    Le coefficient et le volume horaire appartiennent au programme, pas à la
    matière elle-même. Le contenu préchargé par KIS est un référentiel initial
    modifiable par l'administrateur et ne constitue pas une certification IPN.
    """

    class Role(models.TextChoices):
        PRINCIPAL = "principal", "Principale"
        SECONDARY = "secondary", "Secondaire"
        COMMON = "common", "Commune"

    education_level = models.ForeignKey(EducationLevel, on_delete=models.CASCADE, related_name="subject_links")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="level_links")
    name = models.CharField(max_length=100, blank=True, default="", verbose_name="Nom")
    coefficient = models.DecimalField(max_digits=5, decimal_places=2, default=1, verbose_name="Coefficient")
    weekly_hours = models.DecimalField(max_digits=4, decimal_places=1, default=0, verbose_name="Volume horaire / semaine")
    weekly_hours_max = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name="Volume horaire / semaine (max)")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.SECONDARY, verbose_name="Statut pédagogique")
    is_required = models.BooleanField(default=True, verbose_name="Obligatoire")
    order = models.PositiveSmallIntegerField(default=1, verbose_name="Ordre")
    is_active = models.BooleanField(default=True, verbose_name="Active")

    class Meta:
        ordering = ["order", "name", "subject__name"]
        verbose_name = "Matière par niveau"
        verbose_name_plural = "Matières par niveau"
        constraints = [
            models.UniqueConstraint(fields=["education_level", "subject"], name="unique_subject_per_level"),
        ]

    def save(self, *args, **kwargs):
        if not self.name and self.subject_id:
            self.name = self.subject.name
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.education_level} — {self.name or self.subject}"


class EvaluationRule(models.Model):
    """Règle d'évaluation du référentiel. Les écrans de notes pourront l'exploiter progressivement."""

    education_level = models.ForeignKey(EducationLevel, on_delete=models.CASCADE, related_name="evaluation_rules")
    code = models.CharField(max_length=30)
    label = models.CharField(max_length=100)
    weight = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    max_score = models.DecimalField(max_digits=6, decimal_places=2, default=20)
    order = models.PositiveSmallIntegerField(default=1)
    is_required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["education_level__order", "order", "id"]
        verbose_name = "Règle d'évaluation"
        verbose_name_plural = "Règles d'évaluation"
        constraints = [
            models.UniqueConstraint(fields=["education_level", "code"], name="unique_evaluation_rule_per_level"),
        ]

    def __str__(self):
        return f"{self.education_level} — {self.label}"


class PedagogicalTrack(models.Model):
    """Structure intermédiaire facultative : série, filière, formation, section ou option.

    Elle permet de modéliser les structures du lycée et du professionnel sans
    imposer leur forme aux autres types d'établissement.
    """

    class Kind(models.TextChoices):
        SECTION = "section", "Section"
        SERIES = "series", "Série"
        STREAM = "stream", "Filière"
        TRAINING = "training", "Formation"
        OPTION = "option", "Option"

    code = models.CharField(max_length=40, unique=True, verbose_name="Code")
    name = models.CharField(max_length=150, verbose_name="Nom")
    school_type = models.CharField(max_length=30, choices=School.SchoolType.choices, verbose_name="Type d'établissement")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.STREAM, verbose_name="Nature")
    domain = models.CharField(max_length=120, blank=True, default="", verbose_name="Domaine")
    order = models.PositiveSmallIntegerField(default=1, verbose_name="Ordre")
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        ordering = ["school_type", "kind", "order", "name"]
        verbose_name = "Parcours pédagogique"
        verbose_name_plural = "Parcours pédagogiques"

    def clean(self):
        if self.school_type not in dict(School.SchoolType.choices):
            raise ValidationError("Type d'établissement invalide.")

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"


class TrackLevel(models.Model):
    """Niveau proposé dans un parcours (ex. 11ème + une série)."""

    track = models.ForeignKey(PedagogicalTrack, on_delete=models.CASCADE, related_name="levels", verbose_name="Parcours")
    education_level = models.ForeignKey(EducationLevel, on_delete=models.PROTECT, related_name="track_links", verbose_name="Niveau")
    order = models.PositiveSmallIntegerField(default=1, verbose_name="Ordre")
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        ordering = ["order", "education_level__order", "id"]
        verbose_name = "Niveau du parcours"
        verbose_name_plural = "Niveaux des parcours"
        constraints = [
            models.UniqueConstraint(fields=["track", "education_level"], name="unique_track_level"),
        ]

    def clean(self):
        if self.track.school_type != self.education_level.school_type:
            raise ValidationError("Le parcours et le niveau doivent appartenir au même type d'établissement.")

    def __str__(self):
        return f"{self.track.name} — {self.education_level.name}"


class TrackLevelSubject(models.Model):
    """Matières, coefficients et horaires propres à un niveau de parcours."""

    track_level = models.ForeignKey(TrackLevel, on_delete=models.CASCADE, related_name="subject_links", verbose_name="Niveau du parcours")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="track_level_links", verbose_name="Matière")
    name = models.CharField(max_length=100, blank=True, default="", verbose_name="Nom")
    coefficient = models.DecimalField(max_digits=5, decimal_places=2, default=1, verbose_name="Coefficient")
    weekly_hours = models.DecimalField(max_digits=4, decimal_places=1, default=0, verbose_name="Volume horaire / semaine")
    weekly_hours_max = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, verbose_name="Volume horaire / semaine (max)")
    role = models.CharField(max_length=20, choices=EducationLevelSubject.Role.choices, default=EducationLevelSubject.Role.SECONDARY, verbose_name="Statut pédagogique")
    is_required = models.BooleanField(default=True, verbose_name="Obligatoire")
    order = models.PositiveSmallIntegerField(default=1, verbose_name="Ordre")
    is_active = models.BooleanField(default=True, verbose_name="Active")

    class Meta:
        ordering = ["order", "name", "subject__name"]
        verbose_name = "Matière du parcours"
        verbose_name_plural = "Matières des parcours"
        constraints = [
            models.UniqueConstraint(fields=["track_level", "subject"], name="unique_track_level_subject"),
        ]

    def save(self, *args, **kwargs):
        if not self.name and self.subject_id:
            self.name = self.subject.name
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.track_level} — {self.name or self.subject}"


class SchoolYearTrack(models.Model):
    """Parcours ouverts dans un établissement pour une année donnée."""

    school_year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE, related_name="configured_tracks", verbose_name="Année scolaire")
    track = models.ForeignKey(PedagogicalTrack, on_delete=models.PROTECT, related_name="school_year_configurations", verbose_name="Parcours")
    is_active = models.BooleanField(default=True, verbose_name="Ouvert dans l'établissement")

    class Meta:
        ordering = ["track__kind", "track__order", "track__name"]
        verbose_name = "Parcours de l'année scolaire"
        verbose_name_plural = "Parcours de l'année scolaire"
        constraints = [
            models.UniqueConstraint(fields=["school_year", "track"], name="unique_school_year_track"),
        ]

    def clean(self):
        if not self.school_year.school.has_school_type(self.track.school_type):
            raise ValidationError("Le parcours ne correspond pas à un type d'enseignement activé dans l'établissement.")

    def __str__(self):
        return f"{self.school_year} — {self.track.name}"


class ClasseManager(models.Manager):
    """Charge toujours le niveau et le parcours avec la classe.

    Le libellé d'une classe (``__str__``, ``display_name``) lit son niveau et
    son parcours. Sans ce chargement groupé, chaque liste déroulante ou
    tableau affichant N classes déclenchait 2×N requêtes supplémentaires.
    """

    def get_queryset(self):
        return super().get_queryset().select_related("education_level", "pedagogical_track")


class Classe(models.Model):
    objects = ClasseManager()

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="classes", verbose_name="Établissement")
    school_year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE, related_name="classes", verbose_name="Année scolaire")
    education_level = models.ForeignKey(EducationLevel, on_delete=models.PROTECT, related_name="classes", verbose_name="Niveau")
    # ``name`` est conservé pour compatibilité avec les anciennes données et
    # les modules existants. Pour les nouvelles classes, il est généré à partir
    # du niveau et du groupe.
    name = models.CharField(max_length=100, verbose_name="Libellé interne")
    group = models.CharField(
        max_length=10, blank=True, default="",
        verbose_name="Groupe",
        help_text="Optionnel : A, B, C… Laisser vide pour une classe unique au niveau.",
    )
    pedagogical_track = models.ForeignKey(PedagogicalTrack, on_delete=models.PROTECT, null=True, blank=True, related_name="classes", verbose_name="Parcours / série / filière")
    filiere = models.CharField(max_length=100, null=True, blank=True, verbose_name="Ancienne filière (compatibilité)")

    class Meta:
        ordering = ["education_level__order", "group", "name"]
        verbose_name = "Classe"
        verbose_name_plural = "Classes"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "school_year", "education_level", "group"],
                condition=models.Q(pedagogical_track__isnull=True),
                name="unique_classe_level_group_no_track",
            ),
            models.UniqueConstraint(
                fields=["school", "school_year", "education_level", "pedagogical_track", "group"],
                condition=models.Q(pedagogical_track__isnull=False),
                name="unique_classe_level_track_group",
            ),
        ]

    def clean(self):
        self.group = (self.group or "").strip().upper()
        if self.school_year and self.school_year.school_id != self.school_id:
            raise ValidationError("L'année scolaire doit appartenir au même établissement que la classe.")
        if self.school_year_id and self.school_year.is_archive:
            return  # classe technique de reprise des soldes : pas de référentiel
        # Le formulaire peut être invalide avant qu'un niveau ne soit choisi.
        # Ne jamais dereferencer education_level dans ce cas : la validation
        # du formulaire se charge d'afficher l'erreur sur le champ concerné.
        if not self.education_level_id:
            return
        if not self.school.has_school_type(self.education_level.school_type):
            raise ValidationError("Le niveau ne correspond pas à un type d'enseignement activé dans l'établissement.")
        if self.pedagogical_track:
            if not self.school.has_school_type(self.pedagogical_track.school_type):
                raise ValidationError("Le parcours ne correspond pas à un type d'enseignement activé dans l'établissement.")
            if not TrackLevel.objects.filter(track=self.pedagogical_track, education_level=self.education_level, is_active=True).exists():
                raise ValidationError("Ce parcours ne propose pas ce niveau.")
            if not SchoolYearTrack.objects.filter(school_year=self.school_year, track=self.pedagogical_track, is_active=True).exists():
                raise ValidationError("Ce parcours n'est pas ouvert pour cette année scolaire.")
        if not SchoolYearLevel.objects.filter(
            school_year=self.school_year, education_level=self.education_level, is_active=True
        ).exists():
            raise ValidationError("Ce niveau n'est pas ouvert pour cette année scolaire.")

        same_level_qs = Classe.objects.filter(
            school=self.school,
            school_year=self.school_year,
            education_level=self.education_level,
        ).exclude(pk=self.pk)
        if self.pedagogical_track:
            same_level_qs = same_level_qs.filter(pedagogical_track=self.pedagogical_track)
        else:
            same_level_qs = same_level_qs.filter(pedagogical_track__isnull=True)

        # Un niveau/parcours fonctionne dans l'un des deux modes suivants :
        #   1) une seule classe sans groupe ;
        #   2) plusieurs classes, toutes identifiées par un groupe (A, B, C...).
        # Les deux modes ne peuvent jamais coexister.
        if self.group:
            if same_level_qs.filter(group="").exists():
                raise ValidationError(
                    "Ce niveau possède déjà une classe sans groupe. Supprimez-la ou transformez-la en groupe avant d'ajouter A, B, C…"
                )
        else:
            if same_level_qs.filter(group__gt="").exists():
                raise ValidationError(
                    "Ce niveau possède déjà des classes groupées. Une classe sans groupe ne peut pas coexister avec A, B, C…"
                )

        duplicate_qs = same_level_qs.filter(group=self.group)
        if duplicate_qs.exists():
            raise ValidationError("Une classe avec ce niveau et ce groupe existe déjà pour cette année scolaire.")

        # Pour les nouvelles classes, le libellé est toujours dérivé du niveau
        # et du groupe. Les anciennes valeurs de ``name`` restent intactes.
        if self.pk is None:
            self.name = self.education_level.name + (f" {self.group}" if self.group else "")

    @property
    def programme_valide(self):
        """Indique si le programme de l'année a été explicitement validé."""
        return bool(self.school_year_id and self.school_year.catalog_is_validated)

    def programme_subject_links(self):
        """Retourne le programme applicable à cette classe.

        La classe n'enregistre pas une copie des matières : elle hérite du
        programme du niveau, ou du niveau/parcours lorsque la classe possède
        un parcours. Les coefficients, volumes et statuts restent donc ceux
        de la configuration pédagogique validée de l'établissement.
        """
        return self.applicable_subject_links()

    def programme_subject_ids(self):
        """Ensemble des matières du programme, mémorisé sur l'instance.

        Utilisé par les validations répétées (une note par élève) pour ne pas
        relancer deux requêtes à chaque note enregistrée.
        """
        cached = getattr(self, "_programme_subject_ids", None)
        if cached is None:
            cached = set(self.applicable_subject_links().values_list("subject_id", flat=True))
            self._programme_subject_ids = cached
        return cached

    def applicable_subject_links(self):
        if self.pedagogical_track:
            track_level = TrackLevel.objects.filter(
                track=self.pedagogical_track, education_level=self.education_level, is_active=True
            ).first()
            if track_level:
                return track_level.subject_links.filter(is_active=True).select_related("subject")
        return self.education_level.subject_links.filter(is_active=True).select_related("subject")

    def save(self, *args, **kwargs):
        # ``name`` is the canonical class label. Keep it synchronized with the
        # pedagogical structure so classes created outside the form (imports,
        # services, tests, admin, etc.) follow the same rule.
        if self.education_level_id and not (self.school_year_id and self.school_year.is_archive):
            group = (self.group or "").strip().upper()
            self.group = group
            self.name = self.education_level.name + (f" {group}" if group else "")

        # ``save()`` is also a supported entry point in Django (admin, imports,
        # scripts, tests...). Run the business validation here so the exclusive
        # class/group rule cannot be bypassed simply by skipping ``full_clean()``.
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def level_name(self):
        return self.education_level.name

    @property
    def display_name(self):
        if self.name == "Reprise des soldes":  # classe technique d'une année reprise (sans requête)
            return self.name
        # Pour le secondaire/professionnel, le contexte réel (série/filière/
        # spécialité) fait partie du nom de classe. Les anciens niveaux
        # génériques restent internes pour compatibilité historique.
        if self.pedagogical_track_id and self.education_level.school_type in {
            School.SchoolType.HIGH_SCHOOL, School.SchoolType.VOCATIONAL
        }:
            track_name = self.pedagogical_track.name
            level_name = self.education_level.name
            code = self.education_level.code
            if code == "LYC-10" and track_name.lower().startswith("10ème"):
                base = track_name
            elif code == "LYC-11" and track_name.lower().startswith("11ème"):
                base = track_name
            elif code == "LYC-12" and track_name.lower().startswith("terminale"):
                base = track_name
            elif self.education_level.school_type == School.SchoolType.VOCATIONAL:
                short_level = level_name.replace("BT ", "BT") if code.startswith("BT-") else level_name.replace("CAP ", "CAP")
                short_track = track_name[3:].strip() if track_name.upper().startswith("BT ") else track_name[4:].strip() if track_name.upper().startswith("CAP ") else track_name
                base = f"{short_level} — {short_track}"
            else:
                base = f"{level_name} — {track_name}"
            return f"{base} {self.group}" if self.group else base
        if self.group:
            return f"{self.education_level.name} {self.group}"
        if self.name and self.name != "AUCUN":
            return self.name
        return self.education_level.name

    def __str__(self):
        label = self.display_name
        if self.pedagogical_track and self.education_level.school_type not in {
            School.SchoolType.HIGH_SCHOOL, School.SchoolType.VOCATIONAL
        }:
            return f"{label} — {self.pedagogical_track.name}"
        return label if not self.filiere else f"{label} — {self.filiere}"


class SubjectGroup(models.Model):
    """Groupe de matières utilisé pour les spécialités pluridisciplinaires (ex. LHG)."""

    code = models.CharField(max_length=30, unique=True, verbose_name="Code")
    name = models.CharField(max_length=100, verbose_name="Groupe")
    subjects = models.ManyToManyField(Subject, related_name="groups", blank=True, verbose_name="Matières")
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        ordering = ["name"]
        verbose_name = "Groupe de matières"
        verbose_name_plural = "Groupes de matières"

    def __str__(self):
        return f"{self.code} — {self.name}"


class TeacherSubject(models.Model):
    """Matières qu'un enseignant peut prendre en charge. Plusieurs matières sont possibles."""

    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="qualified_subjects", verbose_name="Enseignant")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="qualified_teachers", verbose_name="Matière")
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        ordering = ["teacher__last_name", "subject__name"]
        verbose_name = "Matière maîtrisée par l'enseignant"
        verbose_name_plural = "Matières maîtrisées par les enseignants"
        constraints = [
            models.UniqueConstraint(fields=["teacher", "subject"], name="unique_teacher_subject_qualification"),
        ]

    def __str__(self):
        return f"{self.teacher} — {self.subject}"


class ClassTeacher(models.Model):
    """Enseignant titulaire/principal d'une classe, particulièrement utile au 1er cycle."""

    classe = models.OneToOneField(Classe, on_delete=models.CASCADE, related_name="class_teacher", verbose_name="Classe")
    teacher = models.ForeignKey(Teacher, on_delete=models.PROTECT, related_name="titular_classes", verbose_name="Enseignant")

    class Meta:
        verbose_name = "Enseignant titulaire"
        verbose_name_plural = "Enseignants titulaires"

    def __str__(self):
        return f"{self.classe} — {self.teacher}"


class Teaching(models.Model):
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="teachings")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="teachings", null=True, blank=True)
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name="teachings")

    class Meta:
        verbose_name = "Enseignement"
        verbose_name_plural = "Enseignements"
        constraints = [
            models.UniqueConstraint(fields=["teacher", "subject", "classe"], name="unique_teaching"),
            models.UniqueConstraint(
                fields=["teacher", "classe"],
                condition=models.Q(subject__isnull=True),
                name="unique_generalist_class_teaching",
            ),
        ]

    def clean(self):
        if not self.teacher_id or not self.classe_id:
            return

        if not self.classe.programme_valide:
            raise ValidationError("Le programme pédagogique de cette année doit être validé avant les affectations.")

        if not self.teacher.is_active:
            raise ValidationError("Cet enseignant est inactif et ne peut pas recevoir d'affectation.")

        # Le profil de l'enseignant ne limite pas les affectations : tout
        # enseignant peut être affecté à tout niveau (KIS propose, l'école décide).
        # Un spécialiste ou un formateur métier peut aussi recevoir une
        # responsabilité de classe sans matière. Le profil décrit la
        # personne ; l'affectation décrit la mission confiée par l'école.
        if not self.subject_id:
            return


        if not self.classe.applicable_subject_links().filter(subject=self.subject, is_active=True).exists():
            raise ValidationError("Cette matière n'est pas référencée dans le programme actif de cette classe.")


    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        if self.subject_id:
            return f"{self.teacher} — {self.subject} — {self.classe}"
        return f"{self.teacher} — {self.classe}"


class Student(models.Model):
    SEX_CHOICES = [("M", "Garçon"), ("F", "Fille")]

    class Status(models.TextChoices):
        ACTIVE = "active", "Élève actif"
        INACTIVE = "inactive", "Élève inactif"

    class InactiveReason(models.TextChoices):
        ALUMNI = "alumni", "Ancien élève"
        TRANSFERRED = "transferred", "Transféré"
        REMOVED = "removed", "Radié"

    first_name = models.CharField(max_length=100, verbose_name="Prénom")
    last_name = models.CharField(max_length=100, verbose_name="Nom")
    sex = models.CharField(max_length=1, choices=SEX_CHOICES, null=True, blank=True, verbose_name="Sexe")
    date_of_birth = models.DateField(null=True, blank=True, verbose_name="Date de naissance")
    place_of_birth = models.CharField(max_length=100, null=True, blank=True, verbose_name="Lieu de naissance")
    matricule = models.CharField(max_length=50, unique=True, null=True, blank=True, verbose_name="Matricule")
    father_name = models.CharField(max_length=100, null=True, blank=True, verbose_name="Nom du père")
    mother_name = models.CharField(max_length=100, null=True, blank=True, verbose_name="Nom de la mère")
    father_phone = models.CharField(max_length=30, null=True, blank=True, verbose_name="Téléphone père")
    mother_phone = models.CharField(max_length=30, null=True, blank=True, verbose_name="Téléphone mère")
    whatsapp_phone = models.CharField(max_length=30, null=True, blank=True, verbose_name="WhatsApp")
    photo = models.ImageField(upload_to="students/", null=True, blank=True)
    recruitment_year = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Année de recrutement",
        help_text="Année scolaire d'arrivée dans l'établissement (2022 pour 2022-2023). Sert au matricule.",
    )
    contact_name = models.CharField(max_length=100, null=True, blank=True, verbose_name="Personne de contact")
    contact_phone = models.CharField(max_length=30, null=True, blank=True, verbose_name="Téléphone du contact")
    contact_relation = models.CharField(max_length=50, null=True, blank=True, verbose_name="Lien de parenté",
                                        help_text="Ex. Oncle, Tante, Tuteur, Grand-mère…")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, verbose_name="Statut")
    inactive_reason = models.CharField(
        max_length=20, choices=InactiveReason.choices, null=True, blank=True, verbose_name="Motif d'inactivité"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        verbose_name = "Élève"
        verbose_name_plural = "Élèves"

    def clean(self):
        if self.status == self.Status.ACTIVE and self.inactive_reason:
            raise ValidationError({"inactive_reason": "Un élève actif ne peut pas avoir de motif d'inactivité."})
        if self.status == self.Status.INACTIVE and not self.inactive_reason:
            raise ValidationError({"inactive_reason": "Le motif d'inactivité est obligatoire."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    # Personne à joindre pour les documents internes, la facture famille, le suivi
    # pédagogique et la vie scolaire : la personne de contact si elle est
    # renseignée, sinon le père (puis la mère à défaut).
    @property
    def responsible_name(self):
        return self.contact_name or self.father_name or self.mother_name or ""

    @property
    def responsible_phone(self):
        if self.contact_name or self.contact_phone:
            return self.contact_phone or ""
        return self.father_phone or self.mother_phone or self.whatsapp_phone or ""

    @property
    def responsible_relation(self):
        if self.contact_name:
            return self.contact_relation or "Contact"
        if self.father_name:
            return "Père"
        return "Mère" if self.mother_name else ""

    @property
    def responsible_label(self):
        name = self.responsible_name
        if not name:
            return ""
        relation = self.responsible_relation
        return f"{name} ({relation.lower()})" if relation else name

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Enrollment(models.Model):
    TYPE_CHOICES = [("regulier", "Régulier"), ("cl", "Candidat libre")]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name="enrollments")
    school_year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE, related_name="enrollments")
    student_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default="regulier", verbose_name="Type d'élève")
    enrollment_date = models.DateField(default=timezone.localdate, verbose_name="Date d'inscription")

    class Meta:
        ordering = ["student__last_name", "student__first_name"]
        verbose_name = "Inscription"
        verbose_name_plural = "Inscriptions"
        constraints = [
            models.UniqueConstraint(fields=["student", "school_year"], name="unique_student_year_enrollment"),
        ]

    def clean(self):
        if self.classe.school_year_id != self.school_year_id:
            raise ValidationError("La classe et l'inscription doivent appartenir à la même année scolaire.")
        if self.classe.school_id != self.school_year.school_id:
            raise ValidationError("La classe et l'année scolaire doivent appartenir au même établissement.")
        if self.student_type == "cl" and not self.classe.education_level.allows_free_candidate:
            raise ValidationError("Le statut candidat libre n'est autorisé que pour une classe d'examen configurée.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} — {self.classe}"


class SchoolYearTransition(models.Model):
    """Cadre de préparation d'un passage d'une année scolaire à la suivante.

    KIS ne décide pas du passage : les propositions sont préparées à partir
    des décisions fournies par l'établissement / l'autorité compétente, puis
    l'administrateur valide leur application dans l'année cible.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Préparation"
        VALIDATED = "VALIDATED", "Décisions validées"
        APPLIED = "APPLIED", "Inscriptions préparées"

    source_year = models.ForeignKey(
        SchoolYear, on_delete=models.PROTECT, related_name="outgoing_transitions", verbose_name="Année source"
    )
    target_year = models.ForeignKey(
        SchoolYear, on_delete=models.PROTECT, related_name="incoming_transitions", verbose_name="Année cible"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, verbose_name="État")
    validated_at = models.DateTimeField(null=True, blank=True, verbose_name="Décisions validées le")
    validated_by = models.ForeignKey(
        "administration.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="validated_transitions", verbose_name="Décisions validées par"
    )
    applied_at = models.DateTimeField(null=True, blank=True, verbose_name="Inscriptions préparées le")
    applied_by = models.ForeignKey(
        "administration.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="applied_transitions", verbose_name="Inscriptions préparées par"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-source_year__start_date"]
        constraints = [
            models.UniqueConstraint(fields=["source_year", "target_year"], name="unique_school_year_transition"),
        ]
        verbose_name = "Passage d'année"
        verbose_name_plural = "Passages d'année"

    def clean(self):
        if self.source_year.school_id != self.target_year.school_id:
            raise ValidationError("Les deux années doivent appartenir au même établissement.")
        if self.source_year_id == self.target_year_id:
            raise ValidationError("L'année source et l'année cible doivent être différentes.")
        if self.target_year.start_date <= self.source_year.start_date:
            raise ValidationError("L'année cible doit être postérieure à l'année source.")

    def validate_decisions(self, user=None):
        if not self.proposals.exists():
            raise ValidationError("Aucune proposition de passage n'a été préparée.")
        pending = self.proposals.filter(decision=PromotionProposal.Decision.PENDING).exists()
        if pending:
            raise ValidationError("Toutes les propositions doivent être traitées avant validation.")
        self.status = self.Status.VALIDATED
        self.validated_at = timezone.now()
        self.validated_by = user if getattr(user, "pk", None) else None
        self.save(update_fields=["status", "validated_at", "validated_by", "updated_at"])


class PromotionProposal(models.Model):
    """Proposition de passage d'un élève vers une inscription future.

    Une proposition n'est jamais une inscription définitive. Elle peut être
    corrigée ou refusée avant la validation de la transition.
    """

    class Decision(models.TextChoices):
        PENDING = "PENDING", "À traiter"
        ACCEPTED = "ACCEPTED", "Acceptée"
        REJECTED = "REJECTED", "Refusée"

    transition = models.ForeignKey(
        SchoolYearTransition, on_delete=models.CASCADE, related_name="proposals", verbose_name="Passage"
    )
    source_enrollment = models.ForeignKey(
        Enrollment, on_delete=models.PROTECT, related_name="promotion_proposals", verbose_name="Inscription source"
    )
    target_education_level = models.ForeignKey(
        EducationLevel, on_delete=models.PROTECT, related_name="promotion_targets", verbose_name="Niveau cible"
    )
    target_track = models.ForeignKey(
        PedagogicalTrack, on_delete=models.PROTECT, null=True, blank=True, related_name="promotion_targets", verbose_name="Parcours cible"
    )
    target_group = models.CharField(max_length=10, blank=True, default="", verbose_name="Groupe cible")
    student_type = models.CharField(
        max_length=10, choices=Enrollment.TYPE_CHOICES, default="regulier", verbose_name="Type d'inscription cible"
    )
    decision = models.CharField(max_length=10, choices=Decision.choices, default=Decision.PENDING, verbose_name="Décision")
    note = models.TextField(blank=True, verbose_name="Observation")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["source_enrollment__student__last_name", "source_enrollment__student__first_name"]
        constraints = [
            models.UniqueConstraint(fields=["transition", "source_enrollment"], name="unique_transition_source_enrollment"),
        ]
        verbose_name = "Proposition de passage"
        verbose_name_plural = "Propositions de passage"

    def clean(self):
        if self.source_enrollment.school_year_id != self.transition.source_year_id:
            raise ValidationError("L'inscription source ne correspond pas à l'année source.")
        if self.source_enrollment.classe.school_id != self.transition.source_year.school_id:
            raise ValidationError("L'élève n'appartient pas à l'établissement du passage.")
        if not SchoolYearLevel.objects.filter(
            school_year=self.transition.target_year,
            education_level=self.target_education_level,
            is_active=True,
        ).exists():
            raise ValidationError("Le niveau cible n'est pas ouvert dans l'année cible.")
        if self.target_track_id:
            if self.target_track.school_type != self.target_education_level.school_type:
                raise ValidationError("Le parcours cible et le niveau cible doivent appartenir au même secteur.")
            if not self.target_track.levels.filter(education_level=self.target_education_level, is_active=True).exists():
                raise ValidationError("Le parcours cible ne propose pas ce niveau.")
            if not self.transition.target_year.configured_tracks.filter(track=self.target_track, is_active=True).exists():
                raise ValidationError("Le parcours cible n'est pas ouvert pour l'année cible.")
        self.target_group = (self.target_group or "").strip().upper()
        if self.student_type == "cl" and not self.target_education_level.allows_free_candidate:
            raise ValidationError("Le candidat libre est réservé à un niveau d'examen configuré.")
        if self.transition.status == SchoolYearTransition.Status.APPLIED:
            raise ValidationError("Ce passage est déjà appliqué et ne peut plus être modifié.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Term(models.Model):
    name = models.CharField(max_length=50, verbose_name="Trimestre")
    school_year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE, related_name="terms")
    order = models.PositiveSmallIntegerField(default=1, verbose_name="Ordre")

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Trimestre"
        verbose_name_plural = "Trimestres"
        constraints = [
            models.UniqueConstraint(fields=["school_year", "name"], name="unique_term_per_year"),
        ]

    def __str__(self):
        return f"{self.name} ({self.school_year})"


class Evaluation(models.Model):
    """Évaluation propre à une classe et à une période.

    Une évaluation peut être ponctuelle (suivi pédagogique) ou une composition
    de période (résultat périodique utilisable pour le suivi annuel).
    """

    class Nature(models.TextChoices):
        PUNCTUAL = "punctual", "Évaluation ponctuelle"
        PERIODIC_COMPOSITION = "periodic_composition", "Composition de période"

    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name="evaluations", verbose_name="Classe")
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="evaluations", verbose_name="Période")
    name = models.CharField(max_length=100, verbose_name="Évaluation")
    nature = models.CharField(
        max_length=30, choices=Nature.choices, default=Nature.PUNCTUAL, verbose_name="Nature"
    )
    date = models.DateField(verbose_name="Date")
    subjects = models.ManyToManyField(
        Subject,
        through="EvaluationSubject",
        related_name="evaluations",
        blank=True,
        verbose_name="Matières",
    )

    class Meta:
        ordering = ["date", "classe__education_level__order", "classe__group", "name", "id"]
        verbose_name = "Évaluation"
        verbose_name_plural = "Évaluations"

    def clean(self):
        if self.classe_id and self.term_id and self.classe.school_year_id != self.term.school_year_id:
            raise ValidationError("La classe et la période doivent appartenir à la même année scolaire.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.classe.display_name} — {self.name} — {self.date:%d/%m/%Y}"


class EvaluationSubject(models.Model):
    """Matière effectivement retenue pour une évaluation donnée."""

    evaluation = models.ForeignKey(Evaluation, on_delete=models.CASCADE, related_name="subject_links", verbose_name="Évaluation")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="evaluation_links", verbose_name="Matière")
    order = models.PositiveSmallIntegerField(default=1, verbose_name="Ordre")

    class Meta:
        ordering = ["order", "subject__name", "id"]
        verbose_name = "Matière de l'évaluation"
        verbose_name_plural = "Matières de l'évaluation"
        constraints = [
            models.UniqueConstraint(fields=["evaluation", "subject"], name="unique_evaluation_subject"),
        ]

    def clean(self):
        if not self.evaluation_id or not self.subject_id:
            return
        if not self.evaluation.classe.applicable_subject_links().filter(subject=self.subject, is_active=True).exists():
            raise ValidationError("Cette matière n'est pas prévue dans le programme actif de la classe.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Grade(models.Model):
    """Notes d'évaluation saisies par l'administration.

    Pour F1, seule la composition officielle est utilisée (sur 10).
    Pour F2, lycée et centre professionnel, A est la moyenne de classe
    fournie à KIS et B la composition. Le champ devoir reste disponible pour
    le suivi interne mais n'entre pas dans le calcul officiel.
    """

    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="grades")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="grades")
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="grades")
    evaluation = models.ForeignKey(
        Evaluation, on_delete=models.CASCADE, related_name="grades",
        null=True, blank=True, verbose_name="Évaluation",
    )

    # Suivi enseignant, facultatif, non utilisé dans la moyenne officielle.
    devoir = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
        verbose_name="Devoir (suivi)",
    )

    # A : moyenne de classe fournie par l'administration pour F2 / secondaire.
    class_average = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
        verbose_name="Moyenne de classe (A)",
    )

    # B : composition officielle.
    composition = models.FloatField(
        null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(20)],
        verbose_name="Composition (B)",
    )

    class Meta:
        verbose_name = "Note"
        verbose_name_plural = "Notes"
        constraints = [
            models.UniqueConstraint(
                fields=["enrollment", "subject", "term"],
                condition=models.Q(evaluation__isnull=True),
                name="unique_grade_legacy_term",
            ),
            models.UniqueConstraint(
                fields=["enrollment", "subject", "evaluation"],
                condition=models.Q(evaluation__isnull=False),
                name="unique_grade_per_evaluation",
            ),
        ]

    @property
    def evaluation_mode(self):
        school_type = self.enrollment.classe.education_level.school_type
        if school_type == "fundamental_1":
            return "F1"
        if school_type == "fundamental_2":
            return "F2"
        return "SECONDARY"

    def clean(self):
        if self.term_id and self.enrollment_id and self.term.school_year_id != self.enrollment.school_year_id:
            raise ValidationError("Le trimestre et l'inscription doivent appartenir à la même année scolaire.")

        if self.evaluation_id:
            if self.evaluation.term_id != self.term_id:
                raise ValidationError("L'évaluation et la période de la note doivent correspondre.")
            if self.enrollment_id and self.evaluation.classe_id != self.enrollment.classe_id:
                raise ValidationError("L'élève doit appartenir à la classe de l'évaluation.")
            if self.subject_id and not self.evaluation.subject_links.filter(subject=self.subject).exists():
                raise ValidationError("Cette matière ne fait pas partie de l'évaluation.")

        if self.enrollment_id and self.subject_id not in self.enrollment.classe.programme_subject_ids():
            raise ValidationError("Cette matière n'est pas prévue pour le niveau/parcours de l'élève.")

        mode = self.evaluation_mode if self.enrollment_id else None

        if mode == "F1":
            if self.composition is not None and self.composition > 10:
                raise ValidationError({"composition": "En F1, la composition est notée sur 10."})
            if self.class_average is not None:
                raise ValidationError({"class_average": "La moyenne de classe A n'est pas utilisée en F1."})
        else:
            if self.class_average is None:
                raise ValidationError({"class_average": "La moyenne de classe A est requise pour ce niveau."})

    def save(self, *args, **kwargs):
        # Seules les notes du bulletin (sans évaluation) sont figées par le verrou.
        if self.evaluation_id is None and self.enrollment_id and self.term_id:
            BulletinLock.ensure_unlocked(self.enrollment.classe_id, self.term_id)
        return super().save(*args, **kwargs)

    @property
    def coefficient(self):
        link = self.enrollment.classe.applicable_subject_links().filter(subject=self.subject).first()
        return link.coefficient if link else self.subject.coefficient

    def moyenne(self):
        if self.composition is None:
            return 0

        if self.evaluation_mode == "F1":
            return self.composition

        if self.class_average is None:
            return 0

        return (self.class_average + (self.composition * 2)) / 3

    def total(self):
        # Les coefficients sont des Decimal depuis le référentiel terrain.
        # Convertir explicitement la moyenne (historiquement un float) évite
        # le mélange float/Decimal et conserve un calcul numérique exact.
        from decimal import Decimal
        return Decimal(str(self.moyenne())) * self.coefficient

    def __str__(self):
        return f"{self.enrollment} — {self.subject}"


class BulletinItem(models.Model):
    """Ligne d'un bulletin configurée par l'établissement pour une classe.

    Une ligne peut reprendre une matière déjà prévue au programme ou être un
    élément propre au bulletin (ex. Conduite, Dictée et questions). Pour les
    éléments propres au bulletin, la note finale est saisie directement.
    """
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name="bulletin_items", verbose_name="Classe")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, null=True, blank=True, related_name="bulletin_items", verbose_name="Matière")
    label = models.CharField(max_length=150, blank=True, default="", verbose_name="Libellé")
    coefficient = models.DecimalField(max_digits=5, decimal_places=2, default=1, verbose_name="Coefficient")
    max_score = models.DecimalField(max_digits=6, decimal_places=2, default=20, verbose_name="Barème")
    order = models.PositiveSmallIntegerField(default=1, verbose_name="Ordre")
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Élément du bulletin"
        verbose_name_plural = "Éléments du bulletin"
        constraints = [
            models.UniqueConstraint(fields=["classe", "subject"], condition=models.Q(subject__isnull=False), name="unique_bulletin_subject_per_class"),
        ]

    def clean(self):
        if not self.classe_id:
            return
        if self.subject_id:
            link = self.classe.applicable_subject_links().filter(subject_id=self.subject_id, is_active=True).first()
            if not link:
                raise ValidationError("Cette matière n'est pas prévue dans le programme actif de la classe.")
            self.label = ""
            self.max_score = 10 if self.classe.education_level.school_type == "fundamental_1" else 20
            if self.coefficient in (None, 0, 1) and link.coefficient is not None:
                self.coefficient = link.coefficient
        else:
            self.label = (self.label or "").strip()
            if not self.label:
                raise ValidationError({"label": "Le libellé de l'élément est obligatoire."})
            if self.max_score is None or self.max_score <= 0:
                raise ValidationError({"max_score": "Le barème doit être supérieur à 0."})

    @property
    def display_name(self):
        if self.subject_id:
            link = self.classe.applicable_subject_links().filter(subject_id=self.subject_id).first()
            return link.name if link else self.subject.name
        return self.label

    @property
    def is_custom(self):
        return self.subject_id is None

    def __str__(self):
        return f"{self.classe.display_name} — {self.display_name}"


class BulletinItemResult(models.Model):
    """Résultat saisi pour un élément personnalisé du bulletin.

    Pour Fondamentale 1, une seule note (``note``) est utilisée, comme pour
    les matières classiques de ce niveau. Pour F2/secondaire, un élément
    personnalisé (Conduite, Dictée…) suit désormais la même règle A/B que les
    matières classiques : ``class_average`` (A, moyenne de classe) et
    ``composition`` (B) sont saisies ensemble, et non une note unique — un
    élément ajouté au bulletin ne doit pas se comporter comme en F1 alors que
    la classe est en secondaire.
    """
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="bulletin_item_results")
    bulletin_item = models.ForeignKey(BulletinItem, on_delete=models.CASCADE, related_name="results")
    term = models.ForeignKey("Term", on_delete=models.CASCADE, related_name="bulletin_item_results")
    note = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True, verbose_name="Note (Fondamentale 1)")
    class_average = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True, verbose_name="Moyenne de classe (A)")
    composition = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True, verbose_name="Composition (B)")

    class Meta:
        verbose_name = "Résultat du bulletin"
        verbose_name_plural = "Résultats du bulletin"
        constraints = [
            models.UniqueConstraint(fields=["enrollment", "bulletin_item", "term"], name="unique_bulletin_item_result"),
        ]

    def _mode(self):
        return "F1" if self.bulletin_item.classe.education_level.school_type == "fundamental_1" else "SECONDARY"

    def clean(self):
        if not self.enrollment_id or not self.bulletin_item_id or not self.term_id:
            return
        if self.enrollment.classe_id != self.bulletin_item.classe_id:
            raise ValidationError("L'élément du bulletin doit appartenir à la classe de l'élève.")
        if self.enrollment.school_year_id != self.term.school_year_id:
            raise ValidationError("La période et l'inscription doivent appartenir à la même année scolaire.")
        if self.bulletin_item.subject_id:
            raise ValidationError("Un résultat direct ne peut être saisi que pour un élément personnalisé du bulletin.")
        max_score = self.bulletin_item.max_score
        if self._mode() == "F1":
            if self.class_average is not None or self.composition is not None:
                raise ValidationError(
                    "La moyenne de classe A et la composition B ne sont pas utilisées en Fondamentale 1."
                )
            if self.note is not None and (self.note < 0 or self.note > max_score):
                raise ValidationError({"note": f"La note doit être comprise entre 0 et {max_score}."})
        else:
            if self.note is not None:
                raise ValidationError(
                    "Ce niveau utilise la moyenne de classe A et la composition B, pas une note unique."
                )
            for field_name, value in (("class_average", self.class_average), ("composition", self.composition)):
                if value is not None and (value < 0 or value > max_score):
                    raise ValidationError({field_name: f"La note doit être comprise entre 0 et {max_score}."})

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.enrollment_id and self.term_id:
            BulletinLock.ensure_unlocked(self.enrollment.classe_id, self.term_id)
        return super().save(*args, **kwargs)

    def moyenne(self):
        """Moyenne à afficher, calculée comme Grade.moyenne() pour rester cohérente."""
        return self.moyenne_for_mode(self._mode())

    def moyenne_for_mode(self, mode):
        """Même calcul, le mode (F1/secondaire) étant déjà connu (calcul groupé)."""
        if mode == "F1":
            return float(self.note) if self.note is not None else None
        if self.composition is None or self.class_average is None:
            return None
        return (float(self.class_average) + float(self.composition) * 2) / 3


class Bulletin(models.Model):
    """Vue documentaire d'une période pour une inscription.

    Les notes ne sont pas copiées : elles restent dans Grade et sont lues
    au moment de générer le bulletin.
    """
    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name="bulletins",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name="bulletins",
    )
    observation_generale = models.TextField(blank=True)
    date_generation = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["enrollment", "term"],
                name="unique_bulletin_enrollment_term",
            )
        ]

    def clean(self):
        super().clean()
        if self.enrollment_id and self.term_id:
            if self.enrollment.school_year_id != self.term.school_year_id:
                raise ValidationError(
                    "Le bulletin et l'inscription doivent appartenir à la même année scolaire."
                )

    def grades(self):
        return Grade.objects.filter(
            enrollment=self.enrollment,
            term=self.term,
            evaluation__isnull=True,
        ).select_related("subject").order_by("subject__name")

    def configured_items(self):
        return self.enrollment.classe.bulletin_items.filter(is_active=True).select_related("subject").order_by("order", "id")

    def class_results(self):
        """Résultats groupés de la classe (calculés une fois, partagés entre bulletins)."""
        results = getattr(self, "_class_results", None)
        if results is None:
            from .services.class_results import ClassTermResults
            results = ClassTermResults(self.enrollment.classe, self.term)
            self._class_results = results
        return results

    def moyenne_generale(self):
        return self.class_results().average(self.enrollment_id)

    def display_mode(self):
        """Mode de présentation du bulletin."""
        school_type = self.enrollment.classe.education_level.school_type
        if school_type == "fundamental_1":
            return "F1"
        return "SECONDARY"

    def rang(self):
        """Rang de l'élève dans sa classe pour la période."""
        return self.class_results().rank(self.enrollment_id)

    def _rang_unitaire(self):
        """Ancien calcul élève par élève, conservé comme référence pour les tests."""
        from .utils import moyenne_generale
        enrollments = Enrollment.objects.filter(
            classe=self.enrollment.classe,
            school_year=self.enrollment.school_year,
        )
        scores = []
        for enrollment in enrollments:
            try:
                score = moyenne_generale(enrollment, self.term)
            except Exception:
                continue
            if score is not None:
                scores.append((enrollment.pk, score))
        scores.sort(key=lambda item: item[1], reverse=True)
        for position, (enrollment_id, _score) in enumerate(scores, start=1):
            if enrollment_id == self.enrollment_id:
                return position
        return None

    def lignes(self):
        """Données prêtes pour le rendu, selon le bulletin configuré."""
        return self.class_results().lines(self.enrollment_id)

    def _lignes_unitaires(self):
        """Ancien calcul ligne par ligne, conservé comme référence pour les tests."""
        result = []
        mode = self.display_mode()
        items = list(self.configured_items())
        contextual_links = {
            link.subject_id: link
            for link in self.enrollment.classe.applicable_subject_links()
        }

        if not items:
            # Compatibilité : avant le paramétrage, toutes les notes existantes
            # restent présentées comme auparavant.
            for grade in self.grades():
                moyenne = grade.moyenne()
                appreciation_scale = 10 if mode == "F1" else 20
                contextual_link = contextual_links.get(grade.subject_id)
                row = {
                    "subject": grade.subject,
                    "display_name": contextual_link.name if contextual_link else grade.subject.name,
                    "moyenne": moyenne,
                    "appreciation": appreciation_for(moyenne, appreciation_scale),
                }
                if mode == "F1":
                    row["composition"] = grade.composition
                else:
                    row["moyenne_de_classe"] = grade.class_average
                    row["note_de_composition"] = grade.composition
                    row["class_average"] = grade.class_average
                    row["composition"] = grade.composition
                    row["coefficient"] = grade.coefficient
                    row["moyenne_coeff"] = grade.total()
                    row["total"] = grade.total()
                result.append(row)
            return result

        for item in items:
            if item.subject_id:
                grade = self.grades().filter(subject_id=item.subject_id).first()
                moyenne = grade.moyenne() if grade else None
                row = {
                    "subject": item.subject,
                    "display_name": item.display_name,
                    "moyenne": moyenne,
                    "appreciation": appreciation_for(moyenne, 10 if mode == "F1" else 20) if moyenne is not None else "",
                    "bulletin_item": item,
                }
                if mode == "F1":
                    row["composition"] = grade.composition if grade else None
                else:
                    row["moyenne_de_classe"] = grade.class_average if grade else None
                    row["note_de_composition"] = grade.composition if grade else None
                    row["class_average"] = grade.class_average if grade else None
                    row["composition"] = grade.composition if grade else None
                    row["coefficient"] = item.coefficient
                    row["moyenne_coeff"] = (moyenne * float(item.coefficient)) if moyenne is not None else None
                    row["total"] = row["moyenne_coeff"]
                result.append(row)
            else:
                direct = BulletinItemResult.objects.filter(
                    enrollment=self.enrollment, bulletin_item=item, term=self.term
                ).first()
                moyenne = direct.moyenne() if direct else None
                row = {
                    "subject": None,
                    "display_name": item.display_name,
                    "moyenne": moyenne,
                    "appreciation": appreciation_for(moyenne, float(item.max_score)) if moyenne is not None else "",
                    "bulletin_item": item,
                    "is_custom": True,
                }
                if mode == "F1":
                    row["composition"] = moyenne
                else:
                    # Un élément personnalisé suit désormais la même règle A/B qu'une
                    # matière classique en secondaire (feedback terrain : il ne doit
                    # pas se comporter comme en F1 alors que la classe est secondaire).
                    row["moyenne_de_classe"] = float(direct.class_average) if direct and direct.class_average is not None else None
                    row["note_de_composition"] = float(direct.composition) if direct and direct.composition is not None else None
                    row["class_average"] = row["moyenne_de_classe"]
                    row["composition"] = row["note_de_composition"]
                    row["coefficient"] = item.coefficient
                    row["moyenne_coeff"] = (moyenne * float(item.coefficient)) if moyenne is not None else None
                    row["total"] = row["moyenne_coeff"]
                result.append(row)
        return result

class PassageDecision(models.Model):
    """Feuille de proposition de passage, gérée classe par classe.

    Pour la Fondamentale 1 et 2, la feuille peut être préparée et imprimée,
    puis renseignée après la décision du CAP avant validation du Directeur.
    Le secondaire suit la même attente de validation, sans document PDF pour
    le moment.
    """

    class Status(models.TextChoices):
        PREPARATION = "PREPARATION", "Préparation"
        CAP_DECIDED = "CAP_DECIDED", "Décision du CAP"
        DIRECTOR_VALIDATED = "DIRECTOR_VALIDATED", "Validée par le Directeur"

    class Decision(models.TextChoices):
        PENDING = "PENDING", "À décider"
        PASSANT = "PASSANT", "Passant"
        REDOUBLANT = "REDOUBLANT", "Redoublant"
        EXCLU = "EXCLU", "Exclu"

    source_year = models.ForeignKey(
        SchoolYear, on_delete=models.PROTECT, related_name="passage_decisions", verbose_name="Année scolaire"
    )
    classe = models.ForeignKey(
        Classe, on_delete=models.PROTECT, related_name="passage_decisions", verbose_name="Classe"
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PREPARATION, verbose_name="État")
    cap_decided_at = models.DateTimeField(null=True, blank=True, verbose_name="Décision du CAP le")
    cap_decided_by = models.ForeignKey(
        "administration.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="cap_decisions_entered", verbose_name="Décision du CAP saisie par"
    )
    director_validated_at = models.DateTimeField(null=True, blank=True, verbose_name="Validée par le Directeur le")
    director_validated_by = models.ForeignKey(
        "administration.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="validated_passage_decisions", verbose_name="Validée par le Directeur"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["classe__education_level__order", "classe__group", "classe__name"]
        constraints = [
            models.UniqueConstraint(fields=["source_year", "classe"], name="unique_passage_decision_class_year"),
        ]
        verbose_name = "Décision de passage"
        verbose_name_plural = "Décisions de passage"

    def clean(self):
        if self.classe.school_year_id != self.source_year_id:
            raise ValidationError("La classe et l'année de la proposition doivent correspondre.")
        if self.classe.school_id != self.source_year.school_id:
            raise ValidationError("La classe et l'établissement doivent correspondre.")

    @property
    def is_fundamental(self):
        return self.classe.education_level.school_type in {"fundamental_1", "fundamental_2"}

    def mark_cap_decided(self, user=None):
        if self.status == self.Status.DIRECTOR_VALIDATED:
            raise ValidationError("Cette décision est déjà validée par le Directeur.")
        if not self.lines.filter(cap_decision__in=[self.Decision.PASSANT, self.Decision.REDOUBLANT, self.Decision.EXCLU]).exists():
            raise ValidationError("Aucune décision du CAP n'a été renseignée.")
        if self.lines.filter(cap_decision=self.Decision.PENDING).exists():
            raise ValidationError("Toutes les décisions doivent être renseignées avant validation du CAP.")
        self.status = self.Status.CAP_DECIDED
        self.cap_decided_at = timezone.now()
        self.cap_decided_by = user if getattr(user, "pk", None) else None
        self.save(update_fields=["status", "cap_decided_at", "cap_decided_by", "updated_at"])

    def validate_by_director(self, user=None):
        if self.status != self.Status.CAP_DECIDED:
            raise ValidationError("La décision du CAP doit être enregistrée avant la validation du Directeur.")
        if self.lines.filter(director_decision=self.Decision.PENDING).exists():
            raise ValidationError("Toutes les décisions doivent être renseignées.")
        self.status = self.Status.DIRECTOR_VALIDATED
        self.director_validated_at = timezone.now()
        self.director_validated_by = user if getattr(user, "pk", None) else None
        self.save(update_fields=["status", "director_validated_at", "director_validated_by", "updated_at"])


class PassageDecisionLine(models.Model):
    """Ligne élève de la feuille de proposition de passage."""

    passage = models.ForeignKey(PassageDecision, on_delete=models.CASCADE, related_name="lines", verbose_name="Proposition")
    enrollment = models.OneToOneField(
        Enrollment, on_delete=models.PROTECT, related_name="passage_decision_line", verbose_name="Inscription"
    )
    proposal_decision = models.CharField(
        max_length=12, choices=PassageDecision.Decision.choices, default=PassageDecision.Decision.PENDING,
        verbose_name="Proposition du conseil"
    )
    cap_decision = models.CharField(
        max_length=12, choices=PassageDecision.Decision.choices, default=PassageDecision.Decision.PENDING,
        verbose_name="Décision du CAP"
    )
    director_decision = models.CharField(
        max_length=12, choices=PassageDecision.Decision.choices, default=PassageDecision.Decision.PENDING,
        verbose_name="Décision du Directeur"
    )
    observation = models.CharField(max_length=255, blank=True, verbose_name="Observation")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["enrollment__student__last_name", "enrollment__student__first_name"]
        constraints = [
            models.UniqueConstraint(fields=["passage", "enrollment"], name="unique_passage_line_enrollment"),
        ]
        verbose_name = "Ligne de décision de passage"
        verbose_name_plural = "Lignes de décision de passage"

    def clean(self):
        if self.enrollment.school_year_id != self.passage.source_year_id:
            raise ValidationError("L'inscription ne correspond pas à l'année de la proposition.")
        if self.enrollment.classe_id != self.passage.classe_id:
            raise ValidationError("L'élève ne correspond pas à la classe de la proposition.")
        if self.passage.status == PassageDecision.Status.DIRECTOR_VALIDATED:
            raise ValidationError("Cette proposition est déjà validée par le Directeur.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class MobileGradePackage(models.Model):
    """Paquet de saisie envoyé à un enseignant pour l'application mobile.

    Le contenu exact transmis est conservé : à l'import, seules les classes,
    matières et inscriptions de ce paquet sont acceptées.
    """

    uid = models.CharField(max_length=36, unique=True, verbose_name="Identifiant")
    # Vide pour un paquet « par classe » (saisie par le secrétariat ou la direction).
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, null=True, blank=True, related_name="mobile_packages", verbose_name="Enseignant")
    label = models.CharField(max_length=150, blank=True, default="", verbose_name="Libellé")
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="mobile_packages", verbose_name="Période")
    content = models.JSONField(verbose_name="Contenu")
    created_by = models.ForeignKey(
        "administration.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="mobile_packages_created", verbose_name="Créé par",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Paquet de saisie mobile"
        verbose_name_plural = "Paquets de saisie mobile"

    @property
    def holder(self):
        """Pour qui est le paquet : l'enseignant, ou le libellé d'un paquet par classe."""
        return self.teacher.full_name if self.teacher_id else (self.label or "Paquet par classe")

    def __str__(self):
        return f"{self.holder} — {self.term}"


class MobileGradeSubmission(models.Model):
    """Fichier de notes renvoyé par un enseignant, en attente ou appliqué."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "À valider"
        APPLIED = "APPLIED", "Appliqué"
        CANCELLED = "CANCELLED", "Abandonné"

    package = models.ForeignKey(MobileGradePackage, on_delete=models.CASCADE, related_name="submissions", verbose_name="Paquet")
    content = models.JSONField(verbose_name="Contenu reçu")
    filename = models.CharField(max_length=255, blank=True, verbose_name="Fichier")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, verbose_name="État")
    imported_by = models.ForeignKey(
        "administration.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="mobile_submissions_imported", verbose_name="Chargé par",
    )
    imported_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True, blank=True, verbose_name="Appliqué le")
    applied_count = models.PositiveIntegerField(default=0, verbose_name="Notes enregistrées")

    class Meta:
        ordering = ["-imported_at"]
        verbose_name = "Dépôt de notes mobile"
        verbose_name_plural = "Dépôts de notes mobile"

    def __str__(self):
        return f"{self.package} — {self.get_status_display()}"


class BulletinLock(models.Model):
    """Bulletins d'une classe verrouillés pour une période.

    Une fois verrouillés (en général après impression et remise aux parents),
    plus aucune note du bulletin de cette classe et de cette période ne peut
    être modifiée : ni à l'écran, ni par un fichier de la saisie mobile.
    Seul un déverrouillage explicite, tracé, rouvre la saisie.
    """

    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name="bulletin_locks", verbose_name="Classe")
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="bulletin_locks", verbose_name="Période")
    locked_at = models.DateTimeField(auto_now_add=True, verbose_name="Verrouillé le")
    locked_by = models.ForeignKey(
        "administration.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="bulletin_locks", verbose_name="Verrouillé par",
    )

    class Meta:
        constraints = [models.UniqueConstraint(fields=["classe", "term"], name="unique_bulletin_lock")]
        verbose_name = "Verrou des bulletins"
        verbose_name_plural = "Verrous des bulletins"

    def __str__(self):
        return f"{self.classe} — {self.term}"

    MESSAGE = "Les bulletins de {classe} pour {term} sont verrouillés : les notes ne peuvent plus être modifiées."

    @classmethod
    def get_for(cls, classe_id, term_id):
        return cls.objects.filter(classe_id=classe_id, term_id=term_id).select_related("classe", "term", "locked_by").first()

    @classmethod
    def ensure_unlocked(cls, classe_id, term_id):
        lock = cls.get_for(classe_id, term_id)
        if lock:
            raise ValidationError(cls.MESSAGE.format(classe=lock.classe.display_name, term=lock.term.name))
