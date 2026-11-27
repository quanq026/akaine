# Run the Discord bot

The bot is optional. It creates and links game accounts, shows recent scores,
renders B30 and lists all players in a paginated ranking. Complete the game
server installation in chapter 5a first; the bot reads the same SQLite
database.

## Create the Discord application

1. Open the [Discord Developer Portal](https://discord.com/developers/applications)
   and create an application for your server.
2. Open its **Bot** settings and create or reset the bot token. Save the token
   in your password manager; Discord may show it only once.
3. In the application's installation settings, allow installation to your
   server with the `bot` and `applications.commands` scopes. Grant only the
   permissions needed to view channels, send messages and embed links.
4. Use the installation link to add it to your test Discord server.

Discord's [application-command documentation](https://docs.discord.com/developers/docs/interactions/slash-commands)
explains why the `applications.commands` scope is needed. The token is a
password for the bot, not the application's public ID.

## Configure the bot on Lightsail

In the Linux SSH terminal, copy the environment example:

```bash
sudo install -o akaine -g akaine -m 0600 /srv/akaine/repo/server/.env.example /srv/akaine/repo/server/.lygus.env
sudo -u akaine nano /srv/akaine/repo/server/.lygus.env
```

Put the bot token after `LYGUS_BOT_TOKEN=`. Check that every path starts with
`/srv/akaine/repo/server`; the example already uses this layout. Replace
`api.example.com` with your own API hostname. Save and exit the editor.

Check that the token field is non-empty without displaying it:

```bash
sudo -u akaine /srv/akaine/repo/.venv/bin/python - <<'PY'
from pathlib import Path
path = Path('/srv/akaine/repo/server/.lygus.env')
rows = dict(line.split('=', 1) for line in path.read_text().splitlines()
            if line and not line.startswith('#') and '=' in line)
assert rows.get('LYGUS_BOT_TOKEN'), 'Bot token is empty'
assert Path(rows['LYGUS_GAME_DB']).is_file(), 'Game database is missing'
print('Discord bot environment ready')
PY
```

The game server must have started at least once so its database exists.

The supported path settings are `LYGUS_SERVER_ROOT`, `LYGUS_GAME_DB`,
`LYGUS_MAPPING_DB` and `LYGUS_LOG_PATH`; `LYGUS_B30_GENERATOR` is optional and
defaults to `tools/b30_generator.py` below the server root. The current bot does
not use `LYGUS_CREATE_CLI`; remove that obsolete setting from an older private
environment file. No account-creation subprocess or password command-line
argument is required.

If you are importing an existing SQLite database that uses WAL, Discord account creation will stop. Use the account command in chapter 5a or have an administrator review the database before changing its journal mode. A fresh setup from chapter 5a does not need that change.

## Start and verify

```bash
set -e
sudo install -o root -g root -m 0644 /srv/akaine/repo/server/lygus-bot.service /etc/systemd/system/lygus-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now lygus-bot.service
sudo systemctl is-active lygus-bot.service
```

The service should report `active`. Open Discord and confirm the bot is online. If commands are missing, wait for synchronization and try `/help`.

### Create your first account

1. Complete [the content setup in chapter 5a](05a-install-game-server.md#3-supply-the-verified-content-files). The bot grants items from the catalogue installed on your server. This guide uses 7.3.1 content.
2. In Discord, run `/create` and enter a username and password in the private dialog. Save the details the bot returns and try `/profile` for your new account.
3. Sign in to the game, choose **Cloud Sync → Download**, then check a pack and a character from your content set. If either is missing, review the content setup. See [how to check account access](05a-install-game-server.md#create-an-account-and-check-access) for an administrator preview.

Use `/link` if you already have an account, `/account` to manage linked Discord users and choose your default account (`⭐ Set Default`), `/default` to quickly view/switch which linked account commands use automatically, or `/dev_key` to issue your own personal read-only Bearer API key (`60 req / 60s`, public profiles only; no assets or account endpoints) (up to 3 Discord links per Akaine account with primary ownership control, 5-attempt `/link` lockout, and DM alerts on new links). `/profile`, `/recent` (alias `/rs`), `/score`, `/compare`, `/top`, `/whatif`, `/progress`, `/b30`, `/b30n` (Chieri vertical card), and `/b30n2` (16:10 widescreen) accept an Akaine username or the `discord_profile` option; `/song`, `/random`, `/lb`, and `/ranking` inspect charts and server leaderboards (five players per page). Score cards and `/b30n` images render with Pillow using your local `assets/jackets/`, `assets/char/`, and optional Apache-2.0 theme assets (`assets/card_theme/` from `SkyDynamic/nonebot-plugin-arcaeabot`).

If the service is not active, inspect only its recent status and logs:

```bash
sudo systemctl status lygus-bot.service --no-pager
sudo journalctl -u lygus-bot.service -n 60 --no-pager
```

Do not paste the token or unredacted account logs into a public issue.

Next: [Back up and restore the server](05c-backup-recovery.md).
