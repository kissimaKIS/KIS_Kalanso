"""Envoi assisté par WhatsApp (retours V8-6).

KIS ne envoie rien lui-même : il prépare le message et le numéro, puis un clic
ouvre WhatsApp (application ou WhatsApp Web) avec le texte déjà écrit ; la
personne n'a plus qu'à appuyer sur « Envoyer ». Un PDF (reçu, bulletin) est
téléchargé au même moment, à joindre dans la conversation.

Lien utilisé : https://wa.me/<numéro international sans +>?text=<message>
"""
import re
from urllib.parse import quote

DEFAULT_COUNTRY_CODE = "223"   # Mali


def normalize_phone(phone, country_code=DEFAULT_COUNTRY_CODE):
    """« 76 41 36 30 », « +223 76413630 », « 0022376413630 » → « 22376413630 » ; '' si inutilisable."""
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 8:                       # numéro local malien
        digits = country_code + digits
    return digits if len(digits) >= 10 else ""


def wa_url(phone, text):
    number = normalize_phone(phone)
    if not number:
        return ""
    return f"https://wa.me/{number}?text={quote(text or '')}"


def family_phone(student):
    """Numéro WhatsApp du parent : le numéro WhatsApp s'il est renseigné, sinon la personne de contact (à défaut le père)."""
    for phone in (getattr(student, "whatsapp_phone", ""), student.responsible_phone, student.mother_phone):
        if normalize_phone(phone):
            return phone
    return ""


def money(value, currency="FCFA"):
    return f"{value:,.0f} {currency}".replace(",", " ")


# ---------------------------------------------------------------- messages
def announcement_text(announcement, school):
    return f"*{school.name}*\n\n*{announcement.title}*\n\n{announcement.message}"


def receipt_text(payments, receipt_number, school):
    student_names = sorted({str(p.invoice.enrollment.student) for p in payments})
    lines = [f"*{school.name}*", "", f"Bonjour, nous accusons réception de votre versement (reçu n° {receipt_number}) :"]
    for p in payments:
        lines.append(f"• {p.invoice.enrollment.student.first_name} — {p.invoice.label} : {money(p.amount, school.currency)}"
                     + (f" (reste {money(p.invoice.reste, school.currency)})" if p.invoice.reste else " (soldé)"))
    total = sum(p.amount for p in payments)
    lines += ["", f"Total versé : *{money(total, school.currency)}*", "Le reçu est joint à ce message. Merci."]
    if len(student_names) == 1:
        lines[2] = f"Bonjour, nous accusons réception de votre versement pour {student_names[0]} (reçu n° {receipt_number}) :"
    return "\n".join(lines)


def balance_text(student, invoices, school):
    due = [i for i in invoices if i.reste > 0]
    lines = [f"*{school.name}*", "", f"Bonjour, voici la situation des frais de {student} :"]
    for i in due:
        lines.append(f"• {i.label} ({i.enrollment.school_year.name}) : reste {money(i.reste, school.currency)}")
    lines += ["", f"Reste à payer : *{money(sum(i.reste for i in due), school.currency)}*", "Merci de passer à la caisse de l'établissement."]
    return "\n".join(lines)


def bulletin_text(enrollment, term, school):
    return (f"*{school.name}*\n\nBonjour, voici le bulletin de {enrollment.student} "
            f"({enrollment.classe.display_name}) pour {term.name}. Le bulletin est joint à ce message.")


def discipline_text(incident, school):
    e = incident.enrollment
    text = (f"*{school.name}*\n\nBonjour, nous vous informons d'un fait concernant {e.student} "
            f"({e.classe.display_name}) le {incident.date:%d/%m/%Y} — {incident.get_incident_type_display()} :\n{incident.description}")
    if incident.action:
        text += f"\nSuite donnée : {incident.action}"
    return text
