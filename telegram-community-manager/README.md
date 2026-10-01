# Telegram Community Manager

Outil privé de migration et de gestion de communauté Telegram.

## État actuel

Le cœur de migration est maintenant opérationnel en mode sécurisé :

- import TXT / CSV / XLSX et normalisation des `@usernames`;
- campagnes persistantes en SQLite via SQLAlchemy;
- déduplication;
- préflight du groupe cible;
- résolution ciblée des usernames;
- vérification d'appartenance;
- classification persistante par utilisateur;
- dry-run réel, activé par défaut;
- reprise après interruption;
- arrêt immédiat sur `FloodWait`;
- invitation directe uniquement lorsque Telegram l'autorise;
- fallback par lien d'invitation;
- pause / reprise;
- authentification admin de l'API;
- OTP et 2FA saisis uniquement en local;
- tests automatiques sous Python 3.12 et 3.13.

Le projet ne cherche pas à contourner les limites, réglages de confidentialité ou protections anti-spam de Telegram.

## Sécurité

Ne jamais committer :

- `TELEGRAM_API_HASH`;
- `TELEGRAM_BOT_TOKEN`;
- le numéro de téléphone;
- `ADMIN_API_KEY`;
- les fichiers `.session`;
- un fichier `.env` réel;
- les exports contenant des données de membres.

Les sessions Telegram sont sensibles : une session valide peut permettre l'accès au compte. Elles restent dans `SESSION_DIR`, hors Git.

## Installation locale

Depuis le dossier `telegram-community-manager` :

```bash
python -m venv .venv
```

Windows PowerShell :

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Créer ensuite une clé admin forte et la placer dans `.env` :

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Configurer au minimum :

```env
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_PHONE=
ADMIN_API_KEY=
DRY_RUN=true
DATABASE_URL=sqlite:///data/telegram.db
SESSION_DIR=data/sessions
BIND_HOST=127.0.0.1
```

## Authentification Telegram

L'OTP et le mot de passe 2FA ne passent pas par le dashboard.

Exécuter :

```powershell
python scripts/auth_telegram.py
```

Le script crée localement la session `community-manager.session` dans `SESSION_DIR`.

## Démarrage API

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Les routes d'administration utilisent :

```text
Authorization: Bearer <ADMIN_API_KEY>
```

## Pipeline de campagne

1. `POST /campaigns` crée une campagne et définit le groupe cible.
2. `POST /campaigns/{id}/import` importe une liste JSON de usernames.
3. `POST /campaigns/{id}/import-file` accepte TXT, CSV ou XLSX.
4. `POST /campaigns/{id}/preflight` vérifie la session, la cible et les droits d'invitation.
5. `POST /campaigns/{id}/run` avec `{"live": false}` résout et classe les comptes sans invitation réelle.
6. Les utilisateurs éligibles passent à `READY_DIRECT_INVITE`.
7. Les comptes déjà présents, invalides, bots, supprimés ou bloqués par la confidentialité reçoivent un statut dédié.
8. `POST /campaigns/{id}/invite-link` génère le lien de fallback lorsque nécessaire.
9. Un `FloodWait` arrête immédiatement le batch et enregistre la date de reprise.

## Activation des invitations réelles

Deux verrous indépendants sont obligatoires.

D'abord, changer explicitement :

```env
DRY_RUN=false
```

Ensuite appeler :

```text
POST /campaigns/{id}/activate-live
```

avec :

```json
{"confirmation": "ENABLE_LIVE_INVITES"}
```

Enfin seulement :

```json
POST /campaigns/{id}/run
{"live": true, "limit": 25}
```

Sans ces deux conditions, aucune invitation réelle n'est envoyée.

## États membres

Les principaux états persistés sont :

`IMPORTED`, `RESOLVED`, `INVALID`, `BOT_ACCOUNT`, `ALREADY_MEMBER`,
`READY_DIRECT_INVITE`, `DIRECT_INVITED`, `PRIVACY_RESTRICTED`,
`NOT_MUTUAL_CONTACT`, `TOO_MANY_CHANNELS`, `DELETED_ACCOUNT`,
`FLOOD_WAIT`, `LINK_REQUIRED`, `FAILED_TEMPORARY`, `FAILED_FINAL`.

## Validation

La CI installe les dépendances épinglées et exécute `pytest -q` sous Python 3.12 et 3.13.

Les invitations Telegram réelles ne sont jamais testées automatiquement avec des secrets de production. La validation d'intégration live doit être faite séparément avec le compte et le groupe de l'administrateur.
