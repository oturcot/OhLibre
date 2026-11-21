# OhLibre

OhLibre télécharge les épisodes publics d'OHdio dans une bibliothèque locale.
Il ne fournit pas de serveur de balados.

## Avec Docker Compose

Dans [`docker-compose.yml`](docker-compose.yml), modifie `volumes.source`
pour choisir le dossier de ta bibliothèque et `OHDIO_SHOWS` pour choisir
les numéros d'émissions. Le Compose utilise `oturcot/ohlibre:latest`.

```sh
docker compose up -d
docker compose logs -f ohdio
```

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

## Contributions et sécurité du runner

Les tests des PR du propriétaire et de Dependabot sont automatiques. Pour une
PR externe, le propriétaire examine les changements, y compris les workflows,
approuve la révision du commit courant et approuve les exécutions Actions en
attente. Un nouveau commit doit être examiné et approuvé à nouveau.
Les PR exécutent les tests applicatifs et réseau; les images sont construites
et testées après fusion, pas sur les PR.

Avant de rendre le dépôt public, désactive temporairement Actions ou le runner.
Après le changement de visibilité, configure ces protections avant de le
réactiver :

1. Dans **Settings → Actions → General**, choisis **Require approval for all
   external contributors**. Un filtre dans un workflow ne suffit pas : une PR
   peut modifier ce workflow. Limite l'accès en écriture au propriétaire et aux
   automatisations de confiance; les collaborateurs ne sont pas couverts par
   cette règle d'approbation des forks.
2. Dans **Settings → Branches**, protège `main` et `stable` : exige une PR,
   les vérifications réussies et le statut **CI / gated tests**; impose aussi
   ces règles aux administrateurs et exige une branche à jour. Ne choisis pas
   un job ignoré comme seule vérification obligatoire.
3. Vérifie que le runner et son compte ne donnent accès qu'aux ressources
   nécessaires. Une approbation autorise réellement le code proposé à s'exécuter
   sur ce serveur; elle ne l'isole pas. Les issues externes ne sont plus
   assignées automatiquement afin de ne pas lancer de job à leur ouverture.

Ces réglages GitHub ne sont pas appliqués par les fichiers du dépôt. Les
anciennes exécutions en attente et les permissions des collaborateurs doivent
aussi être vérifiées avant de réactiver le runner.
