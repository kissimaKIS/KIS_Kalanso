"""Client local du portail central de licences KIS Core.

Le serveur PythonAnywhere reste la source de vérité. KIS Kalanso n'embarque
aucune clé privée et ne demande plus à l'utilisateur de copier une clé.
Après l'enregistrement initial, l'application peut interroger le serveur
périodiquement jusqu'à ce que le paiement soit confirmé côté portail.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import date, datetime
from pathlib import Path
from urllib import error, request

API_URL = os.getenv("KIS_LICENSE_API_URL", "https://kissima.pythonanywhere.com/api/v1/activate/")
SECRET = "KIS_SECRET_2026"

EDITION_TO_PRODUCT = {
    "1": "KIS Kalanso Fondamental",
    "2": "KIS Kalanso Lycée ou Centre",
    "3": "KIS Kalanso Lycée & Centre",
    "4": "KIS Kalanso Complexe",
}

DAYS_MAPPING = {"30_DAYS": 30, "90_DAYS": 90, "180_DAYS": 180, "360_DAYS": 360, "PERMANENT": 99999}


def machine_id() -> str:
    return str(uuid.getnode())


def school_edition(school) -> tuple[str, str]:
    code = str(getattr(school, "license_level", "") or "")
    product = EDITION_TO_PRODUCT.get(code)
    if not product:
        raise ValueError("Le périmètre de licence de l'établissement n'est pas encore configuré.")
    return code, product


def _path() -> Path:
    root = os.getenv("APPDATA") if os.name == "nt" else os.getenv("XDG_CONFIG_HOME")
    if not root:
        root = str(Path.home() / ("AppData/Roaming" if os.name == "nt" else ".config"))
    return Path(root) / "KIS Kalanso" / "license-central.json"


def _signature(machine: str, days: int, expiry: str) -> str:
    return hashlib.sha256((machine + SECRET + str(days) + expiry).encode()).hexdigest()[:8].upper()


def _validate_key(key: str, machine: str | None = None) -> dict:
    parts = str(key or "").split("-")
    if len(parts) != 5 or parts[0] != "KIS":
        raise ValueError("Clé de licence reçue dans un format invalide.")
    try:
        days = int(parts[3])
        expiry = parts[4]
        datetime.strptime(expiry, "%Y%m%d")
    except (ValueError, TypeError):
        raise ValueError("Clé de licence reçue avec des paramètres invalides.")
    expected = _signature(machine or machine_id(), days, expiry)
    if parts[1] + parts[2] != expected:
        raise ValueError("La clé retournée par le serveur n'est pas valide pour cet ordinateur.")
    return {"days": days, "expires": datetime.strptime(expiry, "%Y%m%d").date().isoformat()}


def save_central_license(key: str, product: str, subscription_type: str, expires_at=None) -> dict:
    payload = _validate_key(key)
    payload.update({
        "key": key.strip(),
        "product": product,
        "product_label": product,
        "subscription_type": subscription_type,
        "label": product,
        "saved_at": date.today().isoformat(),
    })
    if expires_at:
        payload["expires"] = str(expires_at)[:10]
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def load_central_license(on_date: date | None = None) -> dict | None:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        key = data["key"]
        parsed = _validate_key(key)
        expires = date.fromisoformat(str(data.get("expires") or parsed["expires"])[:10])
        current = on_date or date.today()
        if current > expires:
            return None
        if data.get("product") not in EDITION_TO_PRODUCT.values():
            return None
        return {**data, "expires": expires.isoformat()}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _post(payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(API_URL, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        try:
            data = json.loads(exc.read().decode("utf-8"))
        except Exception:
            data = {}
        return {"status": "error", "message": data.get("detail") or "Le serveur de licences a refusé la demande."}
    except error.URLError:
        return {"status": "error", "message": "Connexion impossible avec le serveur central KIS."}
    except TimeoutError:
        return {"status": "error", "message": "Le serveur central KIS met trop de temps à répondre."}
    except Exception as exc:
        return {"status": "error", "message": f"Anomalie de connexion : {exc}"}


def request_activation(school) -> dict:
    _, product = school_edition(school)
    payload = {
        "machine_id": machine_id(),
        "nom": str(getattr(school, "name", "")).strip(),
        "telephone": str(getattr(school, "phone", "")).strip(),
        "produit": product,
    }
    email = str(getattr(school, "email", "") or "").strip()
    if email:
        payload["email"] = email
    if not payload["nom"] or not payload["telephone"]:
        return {"status": "error", "message": "Le nom et le téléphone de l'établissement doivent être renseignés avant l'activation."}

    result = _post(payload)
    if result.get("status") == "success":
        try:
            saved = save_central_license(
                result["licence"], product,
                result.get("subscription_type", "30_DAYS"),
                result.get("expires_at"),
            )
            return {"status": "success", "message": "Licence activée automatiquement.", "license": saved}
        except (KeyError, ValueError) as exc:
            return {"status": "error", "message": str(exc)}
    if result.get("status") == "pending":
        return {"status": "pending", "message": "Paiement en attente de confirmation. KIS Kalanso vérifiera automatiquement l'activation."}
    return {"status": "error", "message": result.get("message") or "Impossible de joindre le service de licence."}
