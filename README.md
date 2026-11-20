# OhLibre

Télécharge dans une bibliothèque locale les épisodes disponibles sur les pages
publiques d'OHdio. Aucune application Radio-Canada ni connexion à un compte n'est
nécessaire. Le conteneur ne lance pas de serveur de balados : configure ton
serveur existant pour lire le dossier de stockage.

## Démarrer depuis le dépôt

Remplace `your-dockerhub-username` dans le Compose par le nom du compte Docker
Hub qui publie l'image, puis lance la version stable dans le dossier du projet :

```sh
docker compose up -d
docker compose logs -f ohdio
```

Ce Compose utilise `your-dockerhub-username/ohlibre:latest` et ne
construit pas d'image locale. Pour tester une modification du code, construis
l'image avec `docker build -t ohlibre:local .`.

Le dossier de stockage par défaut est **`./podcasts`**, à côté de
[`docker-compose.yml`](./docker-compose.yml), détecté sans option `-f`.
Pour le modifier, change `volumes.source` dans le Compose ou crée un fichier
`.env` avec `PODCAST_DIR=/chemin/vers/Podcasts`. Le conteneur y accède sous
`/podcasts`. Il crée un sous-dossier portant le nom de l'émission; configure le
serveur pour lire les MP3, pas le dossier caché `.ohdio`. Conserve ce dossier
caché : il contient l'index des épisodes et les segments en attente. Les
fichiers existants ne sont ni copiés ni déplacés.

| ID dans `OHDIO_SHOWS` | Émission | Première vérification (heure de Toronto) |
| --- | --- | --- |
| `6056` | Moteur de recherche | Lun.–jeu. 20 h |
| `12879` | Moteur en herbe | Ven. 19 h 30 (épisode complet, sans les extraits) |
| `3858` | Midi info | Lun.–ven. 12 h 10, après la première partie |
| `302` | À la une | Lun.–ven. 5 h 30 |
| `3855` | Aujourd'hui l'histoire | Lun.–jeu. 18 h 55, après la diffusion en primeur |
| `52` | Les années lumière | Dim. 13 h 06, après la première partie |

Ajoute les autres balados dans `OHDIO_SHOWS` par leur numéro dans l'adresse
`/ohdio/balados/<numéro>/…`. Sans horaire connu, le conteneur les vérifie au
démarrage puis à 0 h, 6 h, 12 h et 18 h. Au premier démarrage, il commence
avec l'épisode le plus récent, sans importer les archives.

Pour les émissions avec horaire, la vérification reprend toutes les cinq
minutes jusqu'à ce que l'épisode soit complet, jusqu'à une rediffusion reconnue,
ou au plus tard à minuit. Au démarrage, le conteneur vérifie aussi le dernier
créneau passé. Il ne fait pas de rattrapage systématique de tous les créneaux
manqués pendant un arrêt prolongé.

Le fichier `AAAA-MM-JJ_titre de l'épisode.mp3` est visible dès le premier
segment. Les caractères incompatibles avec les noms de fichiers sont retirés
du nom; le titre dans les métadonnées reste celui d'OHdio. Pour chaque nouvel
épisode publié, le conteneur vérifie son titre toutes les 15 minutes pendant
six heures, même après un redémarrage. Si OHdio le modifie, le fichier et son
titre ID3 sont mis à jour sans retélécharger les segments. Aucun indicateur
fiable de titre définitif n'étant disponible, le suivi continue pendant les six
heures même après un changement. Les anciens épisodes déjà indexés avant cette
fonction ne sont pas surveillés.
FFmpeg assemble les segments dans l'ordre annoncé par OHdio et remplace ce
même fichier sans exposer de fichier en cours d'écriture. Le serveur doit
rescanner le fichier pour voir sa nouvelle durée; un fichier déjà téléchargé
sur un appareil n'est pas remplacé automatiquement. Les heures ID3 des
émissions connues reprennent celles de l'ancien crontab, lorsqu'il les définit.
Les rediffusions signalées par OHdio ou qui réutilisent un identifiant audio
déjà publié sont ignorées; une rediffusion non signalée avec de nouveaux
identifiants ne peut pas être reconnue par ce mécanisme.

## Monter un dossier hôte existant

Copie [`.env.example`](./.env.example) en `.env` à côté du Compose si tu
veux stocker les épisodes ailleurs. Indique le chemin sur la machine qui
exécute Docker, par exemple :

```dotenv
PODCAST_DIR="/mnt/media/Mes balados"
```

Le dossier est monté en lecture et écriture sous `/podcasts`. Il reste
sur l'hôte lorsque le conteneur est recréé; ne supprime pas le sous-dossier
caché `.ohdio`, qui sert à la déduplication et à la reprise.

## Tester

`docker compose logs -f ohdio` affiche les vérifications, téléchargements,
publications et erreurs du script. Leurs horodatages suivent l'heure de
Montréal (`America/Toronto`), y compris le passage entre l'heure normale et
l'heure avancée.

Avec Python 3.13+ et FFmpeg (dont `ffprobe`) :

```sh
python3 -m unittest discover -s tests -v
OHDIO_LIVE_TEST=1 python3 -m unittest discover -s tests -v
```

Les tests hors réseau utilisent des sons générés. Les tests réseau vérifient
les six émissions et décodent un court extrait de leurs segments sans
conserver l'audio. GitHub Actions exécute ces tests sur les PR autorisées,
après fusion vers `main` ou `stable`, et avant les releases. Sur les PR,
les tests Python et réseau s'exécutent sur le runner auto-hébergé sans construire
d'image ni lancer de conteneur. Après fusion, les archives amd64 et arm64
sont construites, rechargées et testées séparément sur le runner
auto-hébergé Linux x64 (`self-hosted`, `Linux`, `X64`), qui doit fournir Docker
Engine, Docker Compose et FFmpeg (dont `ffprobe`) au compte du runner;
QEMU fournit l'émulation ARM64.
Pour les PR d'autres personnes, une approbation
du propriétaire sur le commit courant démarre les tests; une nouvelle
modification nécessite une nouvelle approbation.

## Publication

Chaque commit sur `main` dont la CI réussit produit une prérelease numérotée
et l'image `beta`. Le répartiteur reprend les publications après la CI,
chaque heure ou via **Actions → Publish main beta**. Il ne publie que les
deux images testées conservées par la CI pendant 7 jours; un commit sans
ces archives est ignoré avec un avertissement. Relancer avec succès sa CI
actuelle peut le rendre admissible. Les anciens workflows sans archives ne
peuvent pas être récupérés ainsi. Les versions sont réservées avant publication;
une erreur est réessayée après une heure.

Pour une stable, ouvre une PR de `main` vers `stable`, puis fusionne-la après
révision et CI. La fusion déclenche de nouveaux tests et publie `latest` et
`X.Y.Z`. [`.github/NEXT_VERSION`](.github/NEXT_VERSION) définit la prochaine
ligne `X.Y` : la version stable augmente `Z` si la ligne est inchangée, sinon
commence à zéro. Les bêtas utilisent la prochaine version stable et un suffixe
`-beta.N`. Pour une release indépendante d'une promotion, lance **Actions →
Release → Run workflow** sur `stable` et choisis patch, minor, major ou une
version custom supérieure à la dernière stable. La première release manuelle
patch est `0.1.0`. Pour `minor` et `major`, `NEXT_VERSION` doit indiquer la
nouvelle ligne, respectivement `X.Y.0` ou `X.0.0`.

L'image de base officielle `python:3.13-slim` utilise une variante allégée et
reste sur Python 3.13. Un contrôle quotidien détecte les changements de son
digest et ouvre une PR; Dependabot suit aussi les actions GitHub. Après les
tests, les PR automatiques sont fusionnées dans `main`, puis leurs seuls
changements de dépendances sont proposés à `stable`, retestés et publiés en
nouvelle version patch. Les PR manuelles ne sont jamais fusionnées
automatiquement.

Les images publiées proviennent des archives testées : à la publication, leur
configuration reçoit le numéro de release, sans reconstruire l'application.
Au démarrage, le journal indique cette version; une image construite
localement indique `développement`.
Le workflow reprend les brouillons incomplets; une release déjà
publiée ne voit pas ses fichiers remplacés. Les releases sont finalisées
après publication sur Docker Hub. Configurer `RELEASE_BOT_TOKEN` avec accès
en écriture au contenu, aux PR, aux Actions et aux workflows, ainsi que les
secrets `DOCKERHUB_USERNAME` et `DOCKERHUB_TOKEN` pour Docker Hub.
Créer le dépôt Docker Hub `ohlibre` dans ce compte et le rendre public : la
publication vérifie l'accès anonyme. Les images ne sont plus jointes aux
releases GitHub; seuls le Compose et sa somme de contrôle y sont conservés.
Les anciens commits antérieurs à la migration Docker Hub ne sont pas repris
par le répartiteur. Protéger `main` et `stable` en exigeant une
révision et le statut `CI / gated tests`, avec une dérogation pour le bot
utilisé pour les PR de dépendances; le workflow ne fusionne automatiquement
que ces PR. Les règles GitHub du dépôt doivent prendre
en charge ces protections. Lors de la première installation, promouvoir ce
workflow sur `stable` avant de compter sur les promotions automatiques.

## Mettre à jour depuis Docker Hub

Utilise `latest` pour les stables, `beta` pour les bêtas de `main`, ou un
numéro de version pour rester sur cette version. `latest` n'existe pas avant
la première release stable. Le Compose joint à la release contient le nom du
compte Docker Hub; pour suivre les bêtas, ajoute `OHDIO_TAG=beta` dans `.env`.
Conserve le même dossier hôte sans démarrer deux conteneurs sur ce dossier.

```sh
docker compose up -d
```

Compose ne surveille pas le registre quand le conteneur tourne. Pour les
mises à jour périodiques, fais exécuter la commande suivante par `cron` ou
`systemd` dans le dossier du Compose :

```sh
docker compose pull && docker compose up -d --pull never
```