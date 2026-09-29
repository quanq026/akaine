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

## Start and verify

```bash
set -e
sudo install -o root -g root -m 0644 /srv/akaine/repo/server/lygus-bot.service /etc/systemd/system/lygus-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now lygus-bot.service
sudo systemctl is-active lygus-bot.service
```

The service must say `active`. Open Discord and confirm the bot is online.
Its slash commands are synchronized when it starts; they may take time to
appear. Test `/help` and `/ranking`, then create or link a test account and
request `/profile`. Ranking pages contain five players and the Previous/Next
buttons can only be controlled by the Discord user who opened the ranking.
`/profile` and `/recent` accept either an Akaine username or a Discord user in
the `discord_profile` option. A pasted `<@mention>` in the username option is
also recognized. Successful profile and recent-play results are posted to the
channel for everyone to see; another player's private profile remains hidden.
For a new account, follow the bot's note to use **Cloud Sync → Download** in
the game.

If the service is not active, inspect only its recent status and logs:

```bash
sudo systemctl status lygus-bot.service --no-pager
sudo journalctl -u lygus-bot.service -n 60 --no-pager
```

Do not paste the token or unredacted account logs into a public issue.

Next: [Back up and restore the server](05c-backup-recovery.md).
