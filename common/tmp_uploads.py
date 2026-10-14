"""Fichiers déposés en attente de confirmation (prévisualisation d'un import)."""
import time
import uuid
from pathlib import Path

from django.conf import settings


def _dir():
    path = Path(settings.KIS_DATA_DIR) / "tmp_imports"
    path.mkdir(parents=True, exist_ok=True)
    for old in path.glob("*"):
        try:
            if time.time() - old.stat().st_mtime > 86400:
                old.unlink()
        except OSError:
            pass
    return path


def save(uploaded, suffix=".xlsx"):
    token = uuid.uuid4().hex
    with (_dir() / f"{token}{suffix}").open("wb") as fh:
        for chunk in uploaded.chunks():
            fh.write(chunk)
    return token


def path(token, suffix=".xlsx"):
    p = _dir() / f"{Path(str(token)).name}{suffix}"
    return p if p.exists() else None


def remove(token, suffix=".xlsx"):
    p = path(token, suffix)
    if p:
        try:
            p.unlink()
        except OSError:
            pass
