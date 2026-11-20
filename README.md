# OhLibre

OhLibre télécharge les épisodes publics d'OHdio dans une bibliothèque locale.
Il ne fournit pas de serveur de balados.

## Avec Docker Compose

Dans [`docker-compose.yml`](docker-compose.yml), remplace
`your-dockerhub-username` par le compte Docker Hub qui publie OhLibre.
Modifie `volumes.source` pour choisir le dossier de ta bibliothèque et
`OHDIO_SHOWS` pour choisir les numéros d'émissions.

```sh
docker compose up -d
docker compose logs -f ohdio
```

Le dossier par défaut est `./podcasts`. Conserve son sous-dossier caché
`.ohdio` : il permet la déduplication et la reprise.

## Avec Docker

Remplace le nom du compte et le chemin hôte par tes valeurs :

```sh
docker run -d --name ohlibre --restart unless-stopped \
  -e OHDIO_SHOWS=6056,12879,3858,302,3855,52 \
  -e OHDIO_OUTPUT=/podcasts \
  --mount type=bind,source=/chemin/vers/podcasts,target=/podcasts \
  your-dockerhub-username/ohlibre:latest
docker logs -f ohlibre
```

Crée le dossier hôte avant la commande. `latest` correspond à la dernière
version stable; utilise `beta` pour la dernière version de `main`.
Ne lance pas deux conteneurs sur la même bibliothèque.
