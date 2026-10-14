from django import template
register = template.Library()

@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(int(key))
    except (AttributeError, TypeError, ValueError):
        return None


@register.filter
def components_json(fee):
    """Postes d'un frais en JSON (pour le formulaire d'inscription) ; vide s'il n'est pas détaillé."""
    import json
    rows = [{"name": c.name, "amount": int(c.amount)} for c in fee.components.all()]
    return json.dumps(rows) if rows else ""


@register.simple_tag
def wa_link(phone, text):
    """Lien WhatsApp (wa.me) avec message prérempli ; vide si le numéro est inutilisable."""
    from common.whatsapp import wa_url
    return wa_url(phone, text)
