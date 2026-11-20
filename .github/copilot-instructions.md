# Radio-Canada Podcast

Suivre les instructions du projet dans [AGENTS.md](../AGENTS.md).
Exécuter les tests OHdio dans Docker sur le runner auto-hébergé Linux x64.
Les PR valident les archives sans publier de release; les workflows de
publication joignent les images aux releases du dépôt privé et publient
les mêmes images dans GHCR privé, jamais sur Docker Hub.
