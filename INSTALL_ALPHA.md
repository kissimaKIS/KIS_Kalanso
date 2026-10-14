# KIS Kalanso — MVP Alpha 1.0.0

## Base validée
J65 FIX98 — 366/366 tests OK.

## Installation Windows

1. Installer Python 3.12.
2. Ouvrir PowerShell dans ce dossier.
3. Créer l'environnement :
   `python -m venv .venv`
4. Installer les dépendances :
   `.venv\Scripts\python.exe -m pip install -r requirements.txt`
5. Initialiser la base :
   `.venv\Scripts\python.exe manage.py migrate`
6. Lancer KIS Kalanso :
   `.venv\Scripts\python.exe manage.py runserver`

Ou lancer `run_kalanso.bat` après installation des dépendances.

## Licence MVP Alpha
La période pilote intégrée couvre le 01/09/2026 au 30/09/2027 inclus.
L'activation commerciale n'est pas demandée pendant cette période.
À partir du 01/10/2027, l'application utilise le portail central de licences et l'activation est automatique, sans saisie manuelle de clé.

Le périmètre commercial correspond à la catégorie d'établissement configurée lors de la première configuration.

## Sécurité
Aucune clé privée de signature n'est distribuée dans ce package.
Les outils internes de génération de licences ne font pas partie de la livraison Alpha.

## Données
Ne pas inclure de base de données de développement ni de données utilisateur dans le package initial.
