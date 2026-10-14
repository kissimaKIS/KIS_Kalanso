# KIS Kalanso — MVP 1.0.0

KIS Kalanso est livré comme application Django locale pour la gestion scolaire.

## Période pilote

La période pilote intégrée au MVP couvre le **01/09/2026 au 30/09/2027 inclus**.
Pendant cette période, aucune activation commerciale n'est demandée.

## Licence après le pilote

À partir du **01/10/2027**, KIS Kalanso utilise le portail central de licences KIS Core hébergé sur PythonAnywhere. L'utilisateur ne copie pas de clé manuellement.

Les quatre éditions commerciales sont :

1. **KIS Kalanso Fondamental**
2. **KIS Kalanso Lycée ou Centre** — un seul des deux secteurs est choisi dans la configuration de l'établissement
3. **KIS Kalanso Lycée & Centre**
4. **KIS Kalanso Complexe**

Le logiciel envoie automatiquement l'identité de l'établissement, son téléphone et son édition au portail central. Tant que le paiement n'est pas confirmé, l'application attend et vérifie automatiquement l'état. Dès que le portail retourne une licence active, la clé est enregistrée localement et vérifiée pour l'ordinateur.

La clé privée de signature n'est jamais distribuée avec KIS Kalanso.
## Sauvegarde et restauration

Menu **Administration → Sauvegardes** (Administrateur, Promoteur, Gérant, Directeur).

- **Automatique** : à chaque ouverture de l'application, puis toutes les 24 h tant qu'elle reste ouverte, et avant toute mise à jour de la base. Les 30 dernières sauvegardes automatiques sont conservées.
- **Manuelle** : bouton « Sauvegarder maintenant ». Jamais effacée automatiquement.
- **Copie externe** : un dossier sur clé USB ou disque externe peut être indiqué ; chaque sauvegarde y est copiée quand il est branché.
- **Restauration** : depuis la liste ou depuis un fichier `.zip`, après avoir tapé `RESTAURER`. L'état actuel est d'abord sauvegardé (« Avant restauration »).

Une sauvegarde est un fichier `kalanso_AAAAMMJJ_HHMMSS_<type>.zip` contenant la base (copie cohérente par l'API SQLite, compatible mode WAL) et le dossier `media`. Emplacement : `<dossier de données>\sauvegardes`.

## Installation locale

```text
python -m venv .venv
.venv\\Scripts\\pip install -r requirements.txt
.venv\\Scripts\\python.exe manage.py migrate
.venv\\Scripts\\python.exe manage.py runserver
```

Ou utiliser `run_kalanso.bat` après installation des dépendances.

## Nettoyage MVP

Les journaux de développement, notes FIX, fichiers temporaires, bases de données locales et données utilisateur ne font pas partie de la livraison MVP.

## Rôles et contrôle d'accès (recette V3)

| Rôle | Accès |
|---|---|
| Administrateur, Promoteur, Gérant | Tout |
| Directeur | Tout sauf le budget |
| Comptable | Finance hors budget (frais, facturation, encaissements, impayés, salaires) |
| Directeur des études | Scolarité, pédagogie, vie scolaire |
| Secrétaire | Scolarité, encaissements et reçus, impression des bulletins, communication |
| Professeur | Saisie de ses notes et suivi de ses affectations, sans finances |
| Élève, Parent | Aucun espace pour l'instant |

- La matrice est définie dans `administration/permissions/access.py` ; chaque page est rattachée à une permission dans `administration/permissions/url_rules.py`, appliquée par `RoleAccessMiddleware`. Une page non déclarée est réservée aux profils complets.
- Menus, onglets et cartes du tableau de bord suivent les mêmes permissions (`{% if "finance.manage" in kis_perms %}`).
- Un utilisateur ne peut attribuer que des rôles inclus dans ses propres droits, et ne peut pas modifier un compte plus puissant que le sien.
- Créer un enseignant (formulaire ou import Excel) ne crée plus de compte. Le compte Professeur se crée dans Administration → Utilisateurs et se rattache à la fiche enseignant ; il ne voit que les classes et matières de ses affectations.

## Mode application

Le lanceur ouvre KIS Kalanso dans une fenêtre d'application Chrome ou Edge (`--app`), sans barre d'adresse ni onglets, avec un profil navigateur dédié. Fermer la fenêtre arrête le serveur local. Sans Chrome ni Edge, le navigateur par défaut est utilisé.

## Tests

```text
pip install pytest pytest-django
python -m pytest
```

## Performances (complexe de plusieurs milliers d'élèves)

- Listes paginées (50 lignes) : élèves, enseignants, factures, encaissements, impayés, budget, discipline ; historique des présences paginé par date, avec synthèse par classe tant qu'aucune classe n'est choisie.
- Agrégations financières (facturation, impayés, journal budget) faites en SQL, plus en Python.
- Bulletins : moyennes et rangs d'une classe calculés en une fois (`pedagogie/services/class_results.py`) au lieu d'un recalcul complet de la classe pour chaque élève.
- `Classe.objects` charge toujours niveau et parcours (libellés sans requêtes supplémentaires).
- SQLite en mode WAL, connexions persistantes, verrou d'écriture immédiat ; index sur les dates de présence et de paiement.
- Démarrage : PyInstaller en mode dossier (onedir) sans UPX, serveur Waitress, `migrate` lancé seulement si une migration manque, pandas/ReportLab importés à la demande, fenêtre ouverte dès que le serveur répond.
- Mesure : `tools/bench_seed.py <nb_eleves>` génère une base de test, `tools/bench_pages.py` chronomètre chaque page (temps, requêtes SQL, taille). Ne jamais les lancer sur une vraie base.
- `tests/test_performance.py` vérifie que le nombre de requêtes des listes ne dépend pas du nombre d'élèves.

### Construction de l'installateur (changement)

PyInstaller produit désormais un dossier `dist\KIS_Kalanso_Alpha\` (exe + `_internal`) et non plus un exe unique ; `KIS_Kalanso_Setup.iss` installe tout ce dossier. Installer d'abord les nouvelles dépendances : `pip install -r requirements.txt` (ajout de `waitress` et `whitenoise`).
