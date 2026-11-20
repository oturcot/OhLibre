# Radio-Canada Podcast

Télécharge dans une bibliothèque locale les épisodes disponibles sur les pages
publiques d'OHdio. Aucune application Radio-Canada ni connexion à un compte n'est
nécessaire. Le conteneur ne lance pas de serveur de balados : configure ton
serveur existant pour lire le dossier de stockage.

## Démarrer depuis le dépôt

Dans le dossier du projet :

```sh
docker compose up -d
docker compose logs -f ohdio
```

Le dossier de stockage par défaut est **`./podcasts`**, à côté de
[`compose.yml`](./compose.yml). Pour le modifier, change `volumes.source` dans
le Compose ou crée un fichier `.env` avec `PODCAST_DIR=/chemin/vers/Podcasts`.
Le conteneur y accède sous `/podcasts`. Il crée un sous-dossier par numéro
d'émission; configure le serveur pour lire les MP3, pas le dossier caché
`.ohdio`. Conserve ce dossier caché lors des migrations : il contient l'index
des épisodes et les segments en attente.

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

Le fichier `<date>-<identifiant>.mp3` est visible dès le premier segment.
FFmpeg assemble les segments dans l'ordre annoncé par OHdio et remplace ce
même fichier sans exposer de fichier en cours d'écriture. Le serveur doit
rescanner le fichier pour voir sa nouvelle durée; un fichier déjà téléchargé
sur un appareil n'est pas remplacé automatiquement. Les heures ID3 des
émissions connues reprennent celles de l'ancien crontab, lorsqu'il les définit.
Les rediffusions signalées par OHdio ou qui réutilisent un identifiant audio
déjà publié sont ignorées; une rediffusion non signalée avec de nouveaux
identifiants ne peut pas être reconnue par ce mécanisme.

## Tester

Avec Python 3.13+ et FFmpeg (dont `ffprobe`) :

```sh
python3 -m unittest discover -s tests -v
OHDIO_LIVE_TEST=1 python3 -m unittest discover -s tests -v
```

Les tests hors réseau utilisent des sons générés. Les tests réseau vérifient
les six émissions et décodent un court extrait de leurs segments sans
conserver l'audio. GitHub Actions exécute ces tests sur les PR, après
fusion vers `main` ou `stable`, et avant les releases. Les PR construisent
et rechargent aussi les deux archives Docker, sans les publier en release.
Tous ces jobs utilisent des runners GitHub hébergés.

## Installer depuis une release privée

Les commits sur `main` qui passent les tests produisent une bêta. Une
release stable est créée après les tests sur un tag `X.Y.Z`, ou depuis
**Actions → Release → Run workflow** sur `main` ou `stable`, avec une version
`X.Y.Z`. Les releases du dépôt privé sont publiées via le `GITHUB_TOKEN`
fourni par GitHub Actions. Les mêmes images sont
également publiées dans le paquet GHCR privé décrit ci-dessous.

Depuis la même release, télécharge `compose.yml`, `SHA256SUMS` et l'archive
correspondant à ta machine : `radio-canada-podcast-linux-amd64.tar.gz` pour
Intel/AMD, ou `radio-canada-podcast-linux-arm64.tar.gz` pour ARM (dont les
Mac Apple Silicon). Place les fichiers dans le même dossier, puis :

```sh
# Exemple pour ARM : remplace arm64 par amd64 sur une machine Intel/AMD.
grep -E ' (radio-canada-podcast-linux-arm64.tar.gz|compose.yml)$' SHA256SUMS | shasum -c
docker image load -i radio-canada-podcast-linux-arm64.tar.gz
docker compose up -d
```

Le Compose de la release utilise uniquement l'image chargée localement.

## Mettre à jour depuis GHCR privé

GitHub Actions publie `ghcr.io/oturcot/radio-canada-podcast` sans secret
supplémentaire côté CI. Utilise `latest` pour les stables, `beta` pour les
bêtas de `main`, ou un numéro de version pour rester sur cette version.
`latest` n'existe pas avant la première release stable. Le paquet doit rester
privé. Le Compose GHCR ne contient aucun identifiant.

Sur l'hôte Docker, crée un [jeton GitHub classique `read:packages`](https://github.com/settings/tokens/new?scopes=read:packages)
pour un compte avec accès au paquet. Pour le saisir sans l'afficher dans Bash :

```bash
read -rs -p "Jeton GitHub Packages : " token; printf '\n'
printf '%s' "$token" | docker login ghcr.io -u TON_UTILISATEUR_GITHUB --password-stdin
unset token
```

Utilise le magasin d'identifiants de Docker. Enregistre l'asset
`docker-compose.ghcr.yml` de la release sous `docker-compose.yml` dans un
dossier de déploiement séparé du clone. Pour garder la bibliothèque existante,
indique son chemin hôte absolu dans le `.env` du déploiement, sans démarrer deux
conteneurs sur le même dossier. Pour suivre les bêtas avant la première stable,
ajoute `OHDIO_TAG=beta` à ce `.env`.

```sh
docker compose up -d
```

Compose ne surveille pas le registre quand le conteneur tourne. Pour les
mises à jour périodiques, fais exécuter la commande suivante par `cron` ou
`systemd` dans le dossier du Compose, sous le même compte que `docker login` :

```sh
docker compose pull && docker compose up -d --pull never
```
