"""Pages Sauvegarde & restauration (Administration)."""
import tempfile
from pathlib import Path

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.http import FileResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from . import backup

CONFIRM_WORD = "RESTAURER"


@login_required
def backup_home(request):
    return render(request, "common/backup.html", {
        "backups": backup.list_backups(),
        "last_auto": backup.last_backup(backup.AUTO),
        "copy_dir": backup.copy_dir() or "",
        "backup_folder": backup.backup_dir(),
        "confirm_word": CONFIRM_WORD,
        "auto_keep": backup.AUTO_KEEP,
    })


@login_required
@require_POST
def backup_create(request):
    try:
        path = backup.create_backup(backup.MANUAL)
    except Exception as exc:
        messages.error(request, f"Sauvegarde impossible : {exc}")
    else:
        extra = " Une copie a aussi été déposée dans le dossier externe." if backup.copy_dir() else ""
        messages.success(request, f"Sauvegarde créée : {path.name}.{extra}")
    return redirect("backup_home")


@login_required
def backup_download(request, name):
    try:
        path = backup.resolve(name)
    except backup.BackupError as exc:
        messages.error(request, str(exc))
        return redirect("backup_home")
    return FileResponse(open(path, "rb"), as_attachment=True, filename=path.name)


def _confirmed(request):
    if (request.POST.get("confirm") or "").strip().upper() != CONFIRM_WORD:
        messages.error(request, f"Restauration annulée : tapez {CONFIRM_WORD} pour confirmer.")
        return False
    return True


def _restore(request, path):
    try:
        safety = backup.restore_backup(path)
    except backup.BackupError as exc:
        messages.error(request, str(exc))
        return redirect("backup_home")
    # Les comptes et sessions viennent maintenant de la sauvegarde : on se
    # reconnecte avec un compte qui existait à cette date.
    logout(request)
    messages.success(
        request,
        f"Restauration terminée. Les données d'avant ont été gardées dans {safety.name}. Reconnectez-vous.",
    )
    return redirect("login")


@login_required
@require_POST
def backup_restore(request, name):
    if not _confirmed(request):
        return redirect("backup_home")
    try:
        path = backup.resolve(name)
    except backup.BackupError as exc:
        messages.error(request, str(exc))
        return redirect("backup_home")
    return _restore(request, path)


@login_required
@require_POST
def backup_restore_upload(request):
    upload = request.FILES.get("archive")
    if not upload:
        messages.error(request, "Choisissez un fichier de sauvegarde (.zip).")
        return redirect("backup_home")
    if not _confirmed(request):
        return redirect("backup_home")
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "import.zip"
        with open(target, "wb") as out:
            for chunk in upload.chunks():
                out.write(chunk)
        return _restore(request, target)


@login_required
@require_POST
def backup_settings(request):
    try:
        backup.set_copy_dir(request.POST.get("copy_dir"))
    except backup.BackupError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Dossier de copie enregistré." if backup.copy_dir() else "Copie externe désactivée.")
    return redirect("backup_home")
