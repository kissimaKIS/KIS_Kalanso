# Saisie mobile des notes — format des fichiers (version 1)

Contrat entre **KIS Kalanso** (poste de l'établissement) et l'application Android
**KIS Kalanso Notes**. Les deux fichiers sont du JSON en UTF-8.

Périmètre : notes officielles du bulletin, pour le **fondamental** (1er et 2nd cycle),
le **lycée** et le **centre professionnel**. Deux modes de saisie :

- `"mode": "single"` — Fondamentale 1 : une seule note par élève (`note`), sur 10 pour
  une matière, ou sur le barème de la ligne pour une ligne personnalisée ;
- `"mode": "ab"` — Fondamentale 2, lycée, centre : A = moyenne de classe (`class_average`)
  et B = composition (`composition`), sur 20 (ou le barème de la ligne).

Deux sortes de paquets (`"scope"`) :

- `"teacher"` — par enseignant : ses classes et ses matières ;
- `"classes"` — par classe : toutes les lignes du bulletin des classes choisies,
  Conduite comprise (saisie par le secrétariat ou la direction). `"teacher"` vaut alors `null`.

`"label"` donne le nom à afficher (nom de l'enseignant ou du paquet).

## 1. Paquet de saisie (Kalanso → téléphone)

Créé dans *Pédagogie → Saisie mobile*, par enseignant ou par classe(s), pour une période :
`paquet_<Libellé>_<Période>.json`.

```json
{
  "format": "kis-kalanso-paquet",
  "version": 1,
  "package_id": "8f0c…-uuid",
  "package_signature": "8f0c…-uuid:AbCdEf…",
  "generated_at": "2026-11-02T09:15:00+00:00",
  "school": {"name": "Lycée …", "code": "LT"},
  "school_year": "2026-2027",
  "term": {"id": 4, "name": "Trimestre 1"},
  "scope": "teacher",
  "teacher": {"id": 7, "name": "Awa Diarra", "employee_number": "T001"},
  "label": "Awa Diarra",
  "sheets": [
    {
      "sheet_id": "12-34",
      "kind": "subject",
      "mode": "ab",
      "classe": {"id": 12, "name": "10ème année A"},
      "subject": {"id": 34, "name": "Mathématiques"},
      "scale": 20,
      "fields": [
        {"key": "class_average", "label": "Moyenne de classe (A)"},
        {"key": "composition", "label": "Composition (B)"}
      ],
      "rule": "Saisir les deux notes A et B ensemble, ou laisser les deux vides.",
      "students": [
        {"enrollment_id": 501, "matricule": "L0", "last_name": "Coulibaly",
         "first_name": "Awa", "class_average": 11.0, "composition": null}
      ]
    }
  ]
}
```

- `students[].class_average` / `composition` (mode `ab`) ou `students[].note`
  (mode `single`) : notes déjà connues de Kalanso (`null` si absentes).
  L'application les affiche pré-remplies.
- `kind` : `"subject"` pour une matière, `"item"` pour une ligne personnalisée du
  bulletin (Conduite…). Une feuille `item` a `"subject": {"id": null, "name": "Conduite"}`,
  `"item": {"id": 56, "name": "Conduite"}` et un `sheet_id` de la forme `"12-i56"`.
  Les lignes personnalisées ne sont envoyées qu'à l'enseignant affecté à toute la
  classe (affectation sans matière), comme pour la saisie à l'écran.
- `scale` : barème de la feuille (10 ou 20 pour une matière selon le mode, barème de la ligne pour un `item`).
- Les classes dont les bulletins sont verrouillés pour la période ne sont pas envoyées.
- L'application ne doit **jamais** modifier ce fichier.

## 2. Fichier de notes (téléphone → Kalanso)

Produit par le bouton « Envoyer » et partagé (WhatsApp, Bluetooth, câble).
Nom conseillé : `notes_<classe>_<matière>_<période>.json` ou un seul fichier pour tout le paquet.

```json
{
  "format": "kis-kalanso-notes",
  "version": 1,
  "package_id": "8f0c…-uuid",
  "package_signature": "8f0c…-uuid:AbCdEf…",
  "submitted_at": "2026-11-20T10:00:00",
  "app_version": "1.0.0",
  "sheets": [
    {
      "sheet_id": "12-34",
      "grades": [
        {"enrollment_id": 501, "class_average": 12.5, "composition": 14}
      ]
    },
    {
      "sheet_id": "15-40",
      "grades": [
        {"enrollment_id": 702, "note": 7.5}
      ]
    }
  ]
}
```

Règles :
- `package_id` et `package_signature` sont recopiés **tels quels** depuis le paquet.
- `sheets` peut contenir une partie seulement des feuilles du paquet.
- Une note est un nombre de 0 à `scale` (la virgule « 12,5 » est acceptée) ou `null`.
- Mode `ab` : A et B sont saisis ensemble ; une ligne avec les deux à `null` ne change
  rien (elle n'efface pas une note existante). Mode `single` : `note`, ou `null`.
- Champs inconnus : ignorés par Kalanso (ajouts possibles sans changer de version).

## 3. Contrôles à l'import dans Kalanso

Refus du fichier entier : format ou version inconnus, signature invalide, paquet
inconnu de cette installation, année scolaire clôturée.

Refus d'une feuille : feuille absente du paquet, classe/matière/ligne supprimée,
enseignant plus affecté (paquet par enseignant uniquement), **bulletins verrouillés** pour la classe et la période.

Refus d'une ligne : élève absent du paquet ou retiré de la classe, note hors
barème, A sans B (ou l'inverse) en mode `ab`.

Rien n'est enregistré avant que l'utilisateur (Directeur des études, Directeur,
Administrateur…) ait vu l'aperçu et cliqué « Enregistrer ». Un nouvel envoi du
même paquet remplace les notes des élèves concernés.
