# OhLibre

- Ce dépôt privé récupère les épisodes OHdio accessibles sans authentification. Ne pas contourner les restrictions d'accès. L'ancien projet et le crontab servent uniquement de référence.
- Configurer les émissions (`6056`, `12879`, `3858`, `302`, `3855`, `52`) et le chemin hôte dans Docker Compose. Un clone doit fonctionner avec `docker compose up`.
- Garder séparés le fournisseur OHdio, le calendrier en `America/Toronto` et la publication audio avec FFmpeg.
- Vérifier les émissions programmées toutes les cinq minutes après la fin du segment attendu; pour les balados sans horaire, vérifier quatre fois par jour.
- Publier le premier segment disponible, puis remplacer atomiquement le même fichier par la version fusionnée dans l'ordre de diffusion. Persister les identifiants des épisodes et segments; ignorer les rediffusions détectables.
- Tester les six émissions sur les PR, sur `main` et avant les releases. Tous les jobs utilisent le runner auto-hébergé Linux x64 avec les labels `self-hosted`, `Linux` et `X64`. Docker Engine, Docker Compose et FFmpeg (dont ffprobe) doivent être accessibles au compte du runner; construire et tester les archives amd64 et arm64 après fusion, sans créer de conteneur sur les PR.
- Joindre l'image Docker et le Compose aux releases du dépôt privé. Publier les mêmes images uniquement dans le paquet GHCR privé du projet, via `GITHUB_TOKEN`. Ne jamais rendre le paquet public ni publier sur Docker Hub. Documenter toute étape externe requise dans une issue assignée à `oturcot`.
- Ne pas ajouter de serveur ou de fonctionnalité hors périmètre sans approbation. Vérifier le contrat OHdio sur les pages publiques et garder les tests déterministes indépendants du réseau.
