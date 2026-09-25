# Telegram Community Manager

Outil privé de migration et de gestion de communauté Telegram.

## État actuel

V0.1 initialisée sur une branche dédiée. Le mode `DRY_RUN` est activé par défaut. Aucune invitation réelle n'est envoyée par ce socle initial.

## Sécurité

Ne jamais committer `TELEGRAM_API_HASH`, `TELEGRAM_BOT_TOKEN`, le numéro de téléphone, les fichiers `.session` ou un fichier `.env` réel. Copier `.env.example` vers `.env` uniquement dans l'environnement d'exécution.

## Configuration attendue

- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_PHONE`
- `TELEGRAM_BOT_TOKEN` (pour les fonctions bot)
- `TARGET_GROUP`
- `ADMIN_TELEGRAM_ID`
- `DRY_RUN=true` par défaut

## Fonctionnalités déjà posées

- configuration sécurisée par variables d'environnement;
- endpoint `/health`;
- endpoint `/config/status` sans exposition des valeurs secrètes;
- import et normalisation TXT/CSV/XLSX;
- déduplication des usernames;
- premiers tests unitaires;
- exclusions Git pour secrets, sessions et données locales.

## Suite

Base SQL persistante, dry-run Telegram réel, résolution des comptes, vérification d'appartenance, queue persistante, gestion `FloodWait`, liens d'invitation, bot d'administration, tableau de bord et exports.
