# Charbon TEST — bot autonome (MVP)

**Statut : code de test uniquement. Ni déployé ni activé.**

Service Python distinct du site Charbon, destiné **exclusivement** au canal privé
Charbon TEST (`-1003912244927`). Le canal officiel n'est jamais configuré ni
accessible depuis ce service. N'ajoutez pas le bot à d'autres canaux.

## Fonctions

- **09:00 Europe/Paris** : génère un texte quotidien via l'API OpenAI, dans un ton
  « grand frère », adapté au jour de la semaine, puis l'envoie en privé au
  propriétaire avec boutons **Approuver / Modifier / Refuser**.
- **10:00 Europe/Paris** : publie **une seule fois** dans Charbon TEST si et
  seulement si le propriétaire a approuvé avant 10 h **et** `ENABLE_PUBLISH=true`.
  Sinon, aucune publication. Pas de rattrapage tardif après interruption.
- Modifier : le propriétaire envoie un nouveau texte qui lui est de nouveau
  présenté pour validation ; refuser : aucune publication.
- Les boutons expirent à 10 h, les validations anciennes/dupliquées sont rejetées.
- **Assistant IA privé** : fonctionnalité préparée, **désactivée par défaut**.
  Quand autorisée après test, les membres discutent avec un assistant clairement
  identifié IA ; limite de 12 requêtes/jour/personne et un message/20 secondes.
  Pas d'IA dans le groupe et pas de conversation financière (redirigée vers t_fx).
- Aucun historique de messages privés n'est enregistré ; seuls les IDs Telegram et
  compteurs journaliers des usages sont stockés. Fixer une politique de purge
  et une notice de confidentialité avant d'ouvrir l'assistant à la communauté.

Les images/vidéos sont **hors MVP** : elles seront intégrées après validation de
l'identité visuelle et vérification des coûts et des droits des contenus.

## Conditions de sécurité avant tout démarrage

1. **Ne jamais laisser Make et ce service écouter le même bot simultanément.**
   Le `Watch Updates` de Make utilise un webhook et Telegram n'autorise pas en
   parallèle la récupération par polling. Le service **refuse de démarrer** si
   un webhook est présent et `ALLOW_WEBHOOK_TAKEOVER=false`.
2. Un administrateur devra autoriser explicitement la bascule après avoir
   **désactivé les scénarios Make** du bot. La bascule retire alors le webhook
   Make du bot de test, pas du canal officiel. Prévoir un retour arrière.
3. Remplir `TELEGRAM_BOT_TOKEN`, `OWNER_TELEGRAM_ID` et `OPENAI_API_KEY` dans
   un stockage de secrets, **jamais** sur GitHub ni dans la conversation.
4. La base SQLite doit utiliser un **volume persistant**, un **seul conteneur** et
   une sauvegarde sécurisée. Une panne pendant l'envoi peut marquer `failed` :
   ne pas tenter de nouveau automatiquement avant vérification visuelle du canal.
5. `ENABLE_PUBLISH=false`, `ENABLE_ASSISTANT=false` par défaut. Ne jamais activer
   sans avoir testé les trois boutons, l'interdiction des approbations étrangères,
   les expirations, le passage à l'heure d'été/hiver et les doublons.

## Lancer en environnement de test (après autorisation de migrer depuis Make)

```sh
cp .env.example .env
# Saisir les secrets uniquement dans le fichier local non versionné.
docker compose up --build -d
```

Une fois le bot privé démarré, le propriétaire peut envoyer `/start`, `/preview`
(crée un brouillon textuel TEST sans consommer d'API) et `/status`. `/generate`
demande un brouillon généré par l'IA. Un seul brouillon par jour est autorisé.
**Ne pas lancer `docker compose up` tant que Make contrôle le webhook.**

## Tests avant déploiement

```sh
python -m unittest discover -s tests -v
python -m compileall -q bot.py storage.py config.py content.py
```

Ces tests sont des tests locaux de logique, **pas** des tests réels de Telegram.
Vérifier manuellement en environnement TEST :
- messages privés reçus, restriction d'ID propriétaire ;
- boutons approuver / modifier / refuser et clics en double ;
- bouton vieux d'un jour et clic à 10 h 01 ;
- aucun post si absence d'approbation ;
- un seul post après approbation ;
- arrêt du serveur, rétablissement et absence de republication ;
- timezone `Europe/Paris` hiver/été et horaires ;
- assurance que la destination est exclusivement CHARBON TEST ;
- assistant désactivé tant que conditions d'usage/confidentialité non validées.

## Infrastructure et coûts

Un conteneur Python « always-on » sur un serveur Linux avec volume persistant.
Coûts **à confirmer** selon hébergeur et usage : serveur, appels API OpenAI,
images/vidéos éventuelles. Aucune licence Make requise après bascule.

## Déploiement

**Ne pas fusionner ce dossier au site Charbon ni l'activer sans accord**.
Il s'agit d'une proposition en branche GitHub, pour revue et tests.
