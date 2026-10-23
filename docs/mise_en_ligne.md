# Mettre Frip'Lux en ligne sur Render

Adresse finale : `https://friplux.onrender.com` (HTTPS automatique). Coût : environ 13 $/mois
(application 7 $ + base de données 6 $), région Francfort.

Durée : environ 1 heure la première fois. Faites-le à un moment calme (pas pendant les ventes).

---

## Étape 0 — Sur votre PC (Git Bash)

```bash
cd "/c/Users/bmd tech/Documents/friplux"
git am -3 "/c/Users/bmd tech/Downloads/friplux_mise_en_ligne.patch"
pip install -r requirements.txt        # installe gunicorn et whitenoise
python manage.py runserver 0.0.0.0:8000   # vérifier que tout marche encore comme avant
```
Puis envoyez le code sur GitHub (Render l'installe depuis GitHub) :
```bash
git push
```
`git status` ne doit jamais lister `.env`.

## Étape 1 — Créer l'application et la base sur Render

1. Render → **New** (en haut) → **Blueprint**.
2. Choisissez le dépôt GitHub **friplux** (si absent : « Configure account » et autorisez ce dépôt).
3. Nom du Blueprint : `friplux`. Render lit le fichier `render.yaml` et affiche :
   **friplux** (web service) et **friplux-db** (PostgreSQL), région Frankfurt.
4. Remplissez les deux champs demandés :
   - `FRIPLUX_ADRESSE` : l'adresse imprimée sur les factures (ex. `Marché Colobane, Dakar`)
   - `FRIPLUX_TELEPHONE` : le téléphone imprimé sur les factures
5. **Apply**. Render crée la base puis installe l'application (3 à 5 minutes).

À ce stade, la base est **vide** : c'est normal. Dans les journaux de déploiement, la ligne
« Base Frip'Lux encore vide : transférez vos données » est attendue.

## Étape 2 — Transférer vos données (lots, QR codes, utilisateurs, ventes…)

### 2a. Copier votre base actuelle (sur le PC, Git Bash)

Trouvez le numéro de version de PostgreSQL installé :
```bash
ls "/c/Program Files/PostgreSQL/"
```
(par exemple `17`). Remplacez `17` ci-dessous si besoin :
```bash
cd "/c/Users/bmd tech/Documents"
"/c/Program Files/PostgreSQL/17/bin/pg_dump" --format=custom --no-owner --no-privileges \
  -h localhost -U friplux_user -d friplux_db -f friplux.dump
```
Le mot de passe de `friplux_user` est demandé (celui de votre `.env`). Le fichier `friplux.dump` est créé.

### 2b. Récupérer l'adresse de la base Render

Render → **friplux-db** → bouton **Connect** → onglet **External** → copiez
**External Database URL** (elle commence par `postgresql://` et contient le mot de passe :
ne la partagez pas).

### 2c. Envoyer la copie dans la base Render

```bash
"/c/Program Files/PostgreSQL/17/bin/pg_restore" --clean --if-exists --no-owner --no-privileges \
  --dbname="COLLEZ_ICI_L_EXTERNAL_DATABASE_URL" friplux.dump
```
Les guillemets autour de l'adresse sont indispensables. Quelques avertissements « does not exist »
peuvent apparaître : ils sont sans gravité.

### 2d. Relancer l'application

Render → **friplux** → **Manual Deploy** → **Deploy latest commit**. La ligne « Base prête. »
doit apparaître dans les journaux. Si une ligne « Scripts SQL à appliquer » apparaît, ouvrez
Render → friplux → **Shell** et tapez les commandes indiquées.

## Étape 3 — Vérifier

1. `https://friplux.onrender.com/sante/` doit afficher **ok**.
2. `https://friplux.onrender.com/` : connectez-vous avec votre compte habituel.
3. Sur un téléphone, en 4G : ouvrez la même adresse. **La caméra en direct fonctionne** (HTTPS).
   Astuce : menu du navigateur → « Ajouter à l'écran d'accueil » : Frip'Lux s'ouvre comme une appli.
4. Faites une vente test : l'envoi WhatsApp du PDF se fait en un geste, et le QR code de la facture
   s'ouvre sur n'importe quel téléphone.

À partir de là, **tout le monde utilise l'adresse en ligne**. Votre base sur le PC devient une copie
de test : ne l'utilisez plus pour de vraies ventes.

## Étape 4 — Sauvegarde nocturne (indispensable)

Chaque nuit à 2 h, GitHub copie la base Render, la chiffre et la garde 30 jours.

1. GitHub → dépôt **friplux** → **Settings** → **Secrets and variables** → **Actions** →
   **New repository secret**, deux fois :
   - Nom `RENDER_DATABASE_URL` → valeur : l'**External Database URL** (étape 2b)
   - Nom `SAUVEGARDE_MOT_DE_PASSE` → valeur : un **long mot de passe** (au moins 16 caractères).
     **Notez-le en lieu sûr** (et donnez-le à Paco sous enveloppe) : sans lui, les sauvegardes sont illisibles.
2. GitHub → onglet **Actions** → **Sauvegarde nocturne** → **Run workflow** : la première sauvegarde
   se lance. Elle doit finir en vert ✓ en 1 à 2 minutes.
3. Les sauvegardes se trouvent dans Actions → une exécution → en bas « Artifacts ».
4. GitHub vous envoie un e-mail si une sauvegarde échoue.

À savoir : GitHub met en pause les tâches automatiques d'un dépôt sans aucune activité pendant
60 jours (il prévient par e-mail). Il suffit alors de cliquer « Enable workflow ».

### Restaurer une sauvegarde (en cas de problème grave)

1. Téléchargez l'artifact voulu (fichier `.zip`), extrayez `friplux-AAAA-MM-JJ.dump.gpg`.
2. Déchiffrez (Git Bash) :
   ```bash
   gpg --output friplux.dump --decrypt friplux-AAAA-MM-JJ.dump.gpg
   ```
   (le mot de passe `SAUVEGARDE_MOT_DE_PASSE` est demandé)
3. Restaurez comme à l'étape 2c. **Attention : cela remplace toutes les données actuelles.**

Pour une erreur récente (moins de 3 jours), Render peut aussi revenir à une heure précise :
friplux-db → **Recovery**.

## Ensuite : les mises à jour

1. Sur le PC : `git am -3 "…/nouveau.patch"`, vérification avec `runserver`.
2. `git push` → Render met l'application à jour **tout seul** (2 à 4 minutes, sans coupure).
3. Si le correctif contient un script SQL : Render → friplux → **Shell** :
   ```bash
   python manage.py appliquer_sql sql/0XX_nom_du_script.sql
   ```

## Plus tard : votre propre adresse (ex. friplux.sn)

Render → friplux → **Settings** → **Custom Domains** → ajoutez le domaine et suivez les indications
(une ligne à ajouter chez le vendeur du domaine). Le HTTPS est automatique. Ajoutez ensuite, dans
Render → friplux → **Environment**, `FRIPLUX_ADRESSE_PUBLIQUE=https://friplux.sn`, pour que les
QR codes des factures utilisent cette adresse.
