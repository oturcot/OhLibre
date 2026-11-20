# Radio-Canada Podcast

Suivre les instructions du projet dans [AGENTS.md](../AGENTS.md).
Exécuter les tests applicatifs OHdio sur les PR, sans créer de conteneur.
Valider les archives après fusion sur le runner auto-hébergé Linux x64; les workflows de
publication joignent les images aux releases du dépôt privé et publient
les mêmes images dans GHCR privé, jamais sur Docker Hub.
