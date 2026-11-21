# OhLibre

OhLibre télécharge les épisodes publics d'OHdio dans une bibliothèque locale.
Il ne fournit pas de serveur de balados. [Audiobookshelf](https://github.com/advplyr/audiobookshelf)
offre un bon serveur de balados pour accéder à cette bibliothèque.

## Avec Docker Compose

Dans [`docker-compose.yml`](docker-compose.yml), modifie `volumes.source`
pour choisir le dossier de ta bibliothèque et `OHDIO_SHOWS` pour choisir
les numéros d'émissions. Le Compose utilise `oturcot/ohlibre:latest`.

```sh
docker compose up -d
docker compose logs -f ohdio
```

Les journaux indiquent le nom de l'émission. Pour un balado sans horaire connu,
ce nom peut être inconnu jusqu'à la première récupération d'épisodes.

Le dossier par défaut est `./podcasts`. Conserve son sous-dossier caché
`.ohdio` : il permet la déduplication et la reprise.

## Avec Docker

Remplace le chemin hôte par le chemin de ta bibliothèque :

```sh
docker run -d --name ohlibre --restart unless-stopped \
  -e OHDIO_SHOWS=6056,12879,3858,302,3855,52 \
  -e OHDIO_OUTPUT=/podcasts \
  --mount type=bind,source=/chemin/vers/podcasts,target=/podcasts \
  oturcot/ohlibre:latest
docker logs -f ohlibre
```

Crée le dossier hôte avant la commande. `latest` correspond à la dernière
version stable; utilise `beta` pour la dernière version de `main`.
Ne lance pas deux conteneurs sur la même bibliothèque.
