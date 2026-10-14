"""Licence locale de KIS Kalanso.

La période pilote est intégrée au produit. À son terme, l'application exige
une licence commerciale signée et liée à la machine locale.

La clé publique est embarquée dans le produit. La clé privée de signature
n'est jamais distribuée avec KIS Kalanso.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from datetime import date
from pathlib import Path

LICENSE_START = date(2026, 9, 1)
LICENSE_END = date(2027, 9, 30)
LICENSE_LABEL = "Période pilote 2026-2027"
REMINDER_DAYS = (60, 30, 15, 7, 1)
PRODUCT_CODE = "KIS-KALANSO"
LICENSE_FILE_NAME = "license.json"

# RSA-2048 / SHA-256 PKCS#1 v1.5. La clé privée reste chez KIS Solutions.
PUBLIC_EXPONENT = 65537
PUBLIC_MODULUS = int(
    "22532702743924744830621837458813068949510901399298028258817879847721746527838384451507100038252941305583315370932307581613252392633140861416128375393498836984034004973629810273184874789888119946262134947417405404004032219487492681343300616080469978751653771543830764045792417125884592971715102663576448072702144436292286340376832382530301335738733470297630622556360698755786781029035614251660017481811011891828131550199544996365196943963428519385575724045292916625668541372966679591844299094186673590586274215082410197127227055207413694898950578215240984439544960438515714710158481263044169420010695578983851739101223"
)


def machine_id() -> str:
    """Retourne un identifiant stable et non réversible affichable à l'utilisateur."""
    raw = f"{uuid.getnode():012x}".encode("ascii")
    return hashlib.sha256(raw).hexdigest()[:16].upper()


def _license_path() -> Path:
    """Emplacement persistant, adapté à Windows et aux installations portables."""
    if os.name == "nt":
        root = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
        return Path(root) / "KIS Kalanso" / LICENSE_FILE_NAME
    root = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(root) / "kis-kalanso" / LICENSE_FILE_NAME


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _canonical_payload(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _digest_info(digest: bytes) -> bytes:
    return bytes.fromhex("3031300d060960864801650304020105000420") + digest


def _verify_signature(message: bytes, signature: bytes) -> bool:
    key_size = (PUBLIC_MODULUS.bit_length() + 7) // 8
    if len(signature) != key_size:
        return False
    recovered = pow(int.from_bytes(signature, "big"), PUBLIC_EXPONENT, PUBLIC_MODULUS).to_bytes(key_size, "big")
    digest_info = _digest_info(hashlib.sha256(message).digest())
    expected = b"\x00\x01" + b"\xff" * (key_size - len(digest_info) - 3) + b"\x00" + digest_info
    return recovered == expected


def parse_license_key(key: str) -> dict:
    """Valide la signature et retourne la charge utile de la licence."""
    try:
        prefix, payload_part, signature_part = key.strip().split(".", 2)
        if prefix != "KALANSO1":
            raise ValueError("Format de licence inconnu.")
        payload = json.loads(_unb64(payload_part).decode("utf-8"))
        signature = _unb64(signature_part)
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError, base64.binascii.Error) as exc:
        raise ValueError("Clé de licence invalide.") from exc

    if not isinstance(payload, dict) or payload.get("product") != PRODUCT_CODE:
        raise ValueError("Cette licence n'est pas destinée à KIS Kalanso.")
    if not _verify_signature(_canonical_payload(payload), signature):
        raise ValueError("Signature de licence invalide.")
    return payload


def validate_license_key(key: str, on_date: date | None = None, expected_machine: str | None = None) -> dict:
    current = on_date or date.today()
    payload = parse_license_key(key)
    if payload.get("machine_id") != (expected_machine or machine_id()):
        raise ValueError("Cette licence n'est pas liée à cet ordinateur.")
    try:
        issued = date.fromisoformat(payload["issued"])
        expires = date.fromisoformat(payload["expires"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Dates de licence invalides.") from exc
    if expires < issued:
        raise ValueError("Période de licence invalide.")
    if current < issued:
        raise ValueError("Cette licence n'est pas encore active.")
    if current > expires:
        raise ValueError("Cette licence a expiré.")
    return payload


def load_commercial_license(on_date: date | None = None) -> dict | None:
    path = _license_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        key = str(data.get("key", ""))
        return validate_license_key(key, on_date=on_date)
    except (OSError, ValueError, json.JSONDecodeError, TypeError):
        return None


def activate_license(key: str, on_date: date | None = None) -> dict:
    payload = validate_license_key(key, on_date=on_date)
    path = _license_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"key": key.strip(), "payload": payload}, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return payload


def license_status(on_date: date | None = None) -> str:
    current = on_date or date.today()
    if current <= LICENSE_END and current >= LICENSE_START:
        return "pilot"
    if current < LICENSE_START:
        return "pre_activation"
    # Après la période pilote, la source de vérité devient le portail central
    # KIS Core. L'ancien format local reste lisible uniquement pour préserver
    # la compatibilité avec les installations de développement existantes.
    try:
        from .central_license import load_central_license
        if load_central_license(on_date=current):
            return "commercial"
    except Exception:
        pass
    if load_commercial_license(on_date=current):
        return "commercial"
    return "expired"


def license_is_active(on_date: date | None = None) -> bool:
    # Avant le début du pilote, l'application reste utilisable (cas d'installation
    # préparée avant la date de lancement). Le verrou ne s'applique qu'après le
    # pilote lorsqu'aucune licence commerciale valide n'est présente.
    return license_status(on_date) != "expired"


def current_license_label(on_date: date | None = None) -> str:
    status = license_status(on_date)
    if status == "pilot":
        return LICENSE_LABEL
    if status == "commercial":
        try:
            from .central_license import load_central_license
            payload = load_central_license(on_date=on_date)
            if payload:
                return str(payload.get("label") or payload.get("product_label") or "Licence KIS Kalanso")
        except Exception:
            pass
        payload = load_commercial_license(on_date=on_date)
        return str(payload.get("label") or "Licence KIS Kalanso") if payload else "Licence KIS Kalanso"
    return "Licence KIS Kalanso — activation automatique requise"


def license_notice(on_date: date | None = None) -> dict | None:
    current = on_date or date.today()
    status = license_status(current)
    if status == "expired":
        return {"level": "danger", "code": "expired", "message": "La période pilote est terminée. Une activation KIS automatique est maintenant requise pour continuer."}
    if status == "pre_activation":
        return None
    if status == "pilot":
        days_left = (LICENSE_END - current).days
        if days_left in REMINDER_DAYS:
            return {"level": "warning", "code": f"j_minus_{days_left}", "message": f"La période pilote arrive à expiration dans {days_left} jour{'s' if days_left != 1 else ''}."}
        return None
    payload = load_commercial_license(on_date=current)
    if payload:
        expires = date.fromisoformat(payload["expires"])
        days_left = (expires - current).days
        if days_left in REMINDER_DAYS:
            return {"level": "warning", "code": f"commercial_j_minus_{days_left}", "message": f"Votre licence KIS Kalanso arrive à expiration dans {days_left} jour{'s' if days_left != 1 else ''}."}
    return None
