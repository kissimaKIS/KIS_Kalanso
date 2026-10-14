"""Réglage du réseau local (V8-9) : ce poste seul, ou serveur de l'école."""
import sys
import threading

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from common import network


def _qr_svg(text, size=150):
    """QR code en SVG (ReportLab, déjà fourni avec KIS) pour ouvrir l'adresse depuis un téléphone."""
    from reportlab.graphics import renderSVG
    from reportlab.graphics.barcode import qr
    from reportlab.graphics.shapes import Drawing

    widget = qr.QrCodeWidget(text)
    x1, y1, x2, y2 = widget.getBounds()
    drawing = Drawing(size, size, transform=[size / (x2 - x1), 0, 0, size / (y2 - y1), 0, 0])
    drawing.add(widget)
    svg = renderSVG.drawToString(drawing)
    return svg[svg.index("<svg"):]


@login_required
def network_settings(request):
    config = network.load_config()
    if request.method == "POST":
        mode = request.POST.get("mode", "local")
        try:
            network.save_config(mode, request.POST.get("port") or network.DEFAULT_PORT)
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Réglage enregistré. Fermez puis rouvrez KIS Kalanso sur ce poste pour l'appliquer."
                             if mode == "server" else "Réglage enregistré : au prochain démarrage, KIS Kalanso ne sera accessible que sur ce poste.")
        return redirect("network_settings")
    port = config["port"]
    addresses = [{"ip": ip, "url": f"http://{ip}:{port}/", "qr": _qr_svg(f"http://{ip}:{port}/"),
                  "reachable": network.answers_on(ip, port) if network.is_server(config) else None}
                 for ip in network.lan_addresses()]
    return render(request, "common/network.html", {
        "config": config, "addresses": addresses, "port": port,
        "frozen": getattr(sys, "frozen", False),
    })


@login_required
def network_shortcut(request):
    """Raccourci Windows (.url) à copier sur les autres postes : il ouvre KIS sur le serveur."""
    ip = request.GET.get("ip", "")
    if ip not in network.lan_addresses():
        return HttpResponse("Adresse inconnue.", status=400)
    url = f"http://{ip}:{network.load_config()['port']}/"
    response = HttpResponse(f"[InternetShortcut]\r\nURL={url}\r\n", content_type="application/octet-stream")
    response["Content-Disposition"] = 'attachment; filename="KIS Kalanso.url"'
    return response


@login_required
@require_POST
def network_stop(request):
    """Arrête KIS Kalanso sur le serveur (en mode serveur, fermer la fenêtre ne l'arrête pas)."""
    if not getattr(sys, "frozen", False):
        messages.info(request, "Arrêt disponible uniquement dans l'application installée.")
        return redirect("network_settings")

    def stop():
        import os
        import time
        time.sleep(1.5)
        try:
            from django.conf import settings
            from common.db_guard import checkpoint_on_exit
            checkpoint_on_exit(settings.DATABASES["default"]["NAME"])
        finally:
            os._exit(0)

    threading.Thread(target=stop, daemon=True).start()
    return HttpResponse("<p style='font-family:sans-serif;padding:30px'>KIS Kalanso s'arrête sur ce poste. "
                        "Les autres postes n'y ont plus accès. Vous pouvez fermer cette fenêtre.</p>")
