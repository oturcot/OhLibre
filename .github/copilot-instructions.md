# Instructions OhLibre

Suivre aussi les instructions de [AGENTS.md](../AGENTS.md).

## Périmètre et comportement

- Télécharger uniquement les épisodes publics d'OHdio, sans authentification
  ni contournement des restrictions. Ne pas ajouter de serveur de balados.
- Séparer le fournisseur OHdio (`ohdio.py`), les horaires et le service
  (`downloader.py`), et la bibliothèque audio (`library.py`).
- Lire les identifiants dans `OHDIO_SHOWS` et écrire dans `OHDIO_OUTPUT`.
  Les utilisateurs peuvent configurer le dossier hôte directement dans
  `docker-compose.yml`. Conserver `.ohdio`, qui contient l'index et les
  segments en attente; ne pas déplacer les fichiers existants.
- Utiliser `America/Toronto`, y compris pour les journaux du conteneur.
  Les horaires ci-dessous indiquent la première vérification :

  | Identifiant | Émission | Horaire |
  | --- | --- | --- |
  | `6056` | Moteur de recherche | Lun.–jeu. 20 h |
  | `12879` | Moteur en herbe | Ven. 19 h 30; épisode complet seulement |
  | `3858` | Midi info | Lun.–ven. 12 h 10, après la première partie |
  | `302` | À la une | Lun.–ven. 5 h 30 |
  | `3855` | Aujourd'hui l'histoire | Lun.–jeu. 18 h 55 |
  | `52` | Les années lumière | Dim. 13 h 06, après la première partie |

- Accepter d'autres identifiants issus des URL `/ohdio/balados/<numéro>/…`.
  Sans horaire connu, vérifier au démarrage puis à 0 h, 6 h, 12 h et 18 h;
  commencer au premier démarrage avec l'épisode le plus récent.
- Pour les émissions programmées, revérifier toutes les cinq minutes jusqu'à
  l'épisode complet, une rediffusion reconnue ou minuit. Au démarrage, vérifier
  le dernier créneau passé, sans rattraper tous les créneaux manqués.
- Publier le premier segment sous `AAAA-MM-JJ_titre de l'épisode.mp3`.
  Nettoyer le nom de fichier sans modifier le titre ID3. Assembler les segments
  avec FFmpeg dans l'ordre annoncé et remplacer atomiquement le même fichier.
  Les serveurs doivent rescanner le fichier pour voir sa nouvelle durée.
- Vérifier le titre des nouveaux épisodes toutes les 15 minutes pendant six
  heures, y compris après un redémarrage; mettre à jour le fichier et son titre
  ID3 sans retélécharger les segments. Les anciens épisodes déjà indexés ne
  sont pas surveillés.
- Ignorer les rediffusions signalées ou réutilisant un identifiant audio déjà
  publié. Une rediffusion non signalée avec de nouveaux identifiants ne peut
  pas être reconnue par ce mécanisme.

## Tests et CI

- Avec Python 3.13+ et FFmpeg (dont `ffprobe`) :
  `python3 -m unittest discover -s tests -v`. Ajouter `OHDIO_LIVE_TEST=1`
  pour tester les six émissions et décoder des extraits réseau sans les garder.
  Les tests hors réseau utilisent des sons générés.
- Les PR autorisées exécutent les tests applicatifs et réseau sans construire
  d'image ni créer de conteneur. Pour une PR externe, le propriétaire doit
  approuver le commit courant; un nouveau commit exige une nouvelle approbation.
- Après fusion et avant les releases, construire, recharger et tester les images
  amd64 et arm64 ainsi que le montage hôte. Tous les jobs utilisent le runner
  auto-hébergé Linux x64; Docker Engine, Docker Compose, FFmpeg et `ffprobe`
  doivent être accessibles au compte du runner. QEMU fournit l'émulation ARM64.
- Conserver le statut requis `CI / gated tests` et les protections de branches.
  Les archives des images testées sont conservées sept jours sur le runner,
  dans `RUNNER_WORKSPACE/.ohlibre-image-archives`, puis supprimées lors d'un
  prochain empaquetage. Les jobs doivent partager cet espace persistant;
  `flock` et `sha256sum` doivent être disponibles sur le runner.

## Publication

- Un commit testé sur `main` produit une prérelease et le tag Docker Hub
  `beta`. Le répartiteur s'exécute après la CI, chaque heure ou manuellement;
  il ignore les commits antérieurs à la migration Docker Hub ou sans les deux
  archives conservées. Les anciens artefacts GitHub restent utilisables jusqu'à
  leur expiration. Une erreur est réessayée après une heure.
- La fusion de `main` vers `stable` reteste et publie `latest` et `X.Y.Z`.
  `.github/NEXT_VERSION` définit la prochaine ligne `X.Y`; les bêtas ajoutent
  `-beta.N`. Le workflow Release sur `stable` permet aussi une publication
  manuelle patch, minor, major ou custom.
- Publier les images testées sur Docker Hub public avec les secrets
  `DOCKERHUB_USERNAME` et `DOCKERHUB_TOKEN`. Le dépôt `ohlibre` doit être public
  dans ce compte. Vérifier l'accès anonyme; ne pas publier les archives d'image
  dans les releases GitHub. Les releases contiennent le Compose et sa somme
  de contrôle. L'image reçoit le numéro de release sans reconstruire le code;
  le journal indique `développement` pour une image construite localement.
- `RELEASE_BOT_TOKEN` doit permettre l'écriture du contenu, des PR, des Actions
  et des workflows. Les brouillons incomplets sont repris; une release publiée
  ne voit pas ses fichiers remplacés. Promouvoir les workflows sur `stable`
  avant d'utiliser les promotions automatiques.
- Surveiller le digest de `python:3.13-slim` et les actions GitHub. Seules les
  PR de dépendances automatiques peuvent être fusionnées automatiquement et
  proposées à `stable`; les PR manuelles restent soumises à révision.
