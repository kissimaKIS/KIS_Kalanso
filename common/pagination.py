"""Pagination commune des listes de KIS Kalanso.

Une liste ne doit jamais afficher toutes les lignes d'un complexe scolaire
(des milliers d'élèves, de factures ou de présences) : le navigateur et le
serveur passeraient leur temps à construire des pages de plusieurs Mo.
"""
from django.core.paginator import Paginator

DEFAULT_PER_PAGE = 50


def paginate(request, object_list, per_page=DEFAULT_PER_PAGE, param="page"):
    """Retourne la page demandée (``?page=``) ; une page invalide donne la dernière/première."""
    paginator = Paginator(object_list, per_page)
    return paginator.get_page(request.GET.get(param))
