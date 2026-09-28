# Back up and restore the game server

Use this chapter after the game server runs. It protects player data and the
configuration needed to start the same release again. The commands use the
`/srv/akaine/repo/server` layout from chapter 5a.

## What the backup contains

The archive contains the server's `database/` directory, private `config.py`,
the signing-secret environment file and the optional bot environment file.
It does not contain the Git source, the APK or R2 objects. Record the Git
commit and bundle alias alongside the archive. Keep a verified copy of the
R2 content or the private resource kit so the CDN objects can be restored.
Place `/srv/akaine/backups` on private storage and watch its size; each archive
contains a complete copy of the databases and catalogue files.

## Make a consistent local archive

In the Linux SSH terminal, stop writers while copying SQLite databases:

```bash
set -e
sudo systemctl stop lygus-bot.service 2>/dev/null || true
sudo systemctl stop arcaea-server.service

stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup="/srv/akaine/backups/server-$stamp.tar.gz"
sudo install -d -o root -g root -m 0700 /srv/akaine/backups
cd /srv/akaine/repo/server
files='database config.py .asset-signing.env'
if [ -f .lygus.env ]; then files="$files .lygus.env"; fi
sudo tar -czf "$backup" $files
sudo chmod 0600 "$backup"
sudo tar -tzf "$backup" >/dev/null
sudo sha256sum "$backup"
git -C /srv/akaine/repo rev-parse HEAD

sudo systemctl start arcaea-server.service
if [ -f .lygus.env ]; then sudo systemctl start lygus-bot.service; fi
curl --fail --silent --show-error http://127.0.0.1:18080/
printf 'Backup: %s\n' "$backup"
```

The last HTTP check must return `Hello World!`. Write down the archive path,
SHA-256 and Git commit. If `tar` fails, keep the services stopped until you
understand whether the database files are intact; do not label a partial
archive as a backup.

Copy the archive off the server. The following temporary copy is readable
only by your SSH user:

```bash
sudo install -d -o ubuntu -g ubuntu -m 0700 /home/ubuntu/akaine-intake
sudo install -o ubuntu -g ubuntu -m 0600 "$backup" "/home/ubuntu/akaine-intake/$(basename "$backup")"
```

In Windows PowerShell, use the private folder chosen in chapter 3:

```powershell
$sshKey = Get-Item (Read-Host "Full path to the Lightsail SSH private key")
$serverIp = Read-Host "Lightsail static IPv4 address"
$privateRoot = [Environment]::GetEnvironmentVariable("AKAINE_PRIVATE_ROOT", "User")
$backupName = Read-Host "Backup filename printed by the server"
$localBackup = Join-Path $privateRoot $backupName

scp -i $sshKey.FullName "ubuntu@${serverIp}:/home/ubuntu/akaine-intake/$backupName" $localBackup
if ($LASTEXITCODE -ne 0) { throw "Off-server backup transfer failed." }
Get-FileHash -Algorithm SHA256 $localBackup
```

Compare the complete hash with the Linux output. Store the archive on a
private disk or encrypted backup service. It contains player data and secrets.

## Restore after a failed change

Restoration replaces the current database and private configuration. Use a
backup you created yourself, verify its SHA-256, and retain a separate copy of
the current state before restoring. In the Linux terminal, set the exact
archive path you verified:

```bash
read -r -p 'Full path to the verified backup archive: ' backup
test -f "$backup"
sudo /srv/akaine/repo/.venv/bin/python - "$backup" <<'PY'
import sys, tarfile
from pathlib import PurePosixPath

with tarfile.open(sys.argv[1], 'r:gz') as archive:
    required_files = {'config.py', '.asset-signing.env'}
    seen_files = set()
    database_directory = False
    for entry in archive:
        path = PurePosixPath(entry.name)
        normalized = path.as_posix()
        if (entry.name.startswith('/') or '..' in path.parts or
                not path.parts or not (entry.isfile() or entry.isdir())):
            raise SystemExit(f'Unexpected archive entry: {entry.name}')
        if path.parts[0] == 'database':
            if normalized == 'database':
                if not entry.isdir():
                    raise SystemExit('The database archive entry is not a directory')
                database_directory = True
        elif normalized in required_files | {'.lygus.env'}:
            if not entry.isfile():
                raise SystemExit(f'Expected a regular file: {entry.name}')
            seen_files.add(normalized)
        else:
            raise SystemExit(f'Unexpected archive entry: {entry.name}')
    if not database_directory or not required_files <= seen_files:
        raise SystemExit('Backup is missing a required entry')
print('Backup entries verified')
PY
```

Only continue if this prints `Backup entries verified`. It checks every
archive entry, including file types and paths, before anything is overwritten.
Then stop both services and restore:

```bash
set -e
sudo systemctl stop lygus-bot.service 2>/dev/null || true
sudo systemctl stop arcaea-server.service
sudo tar --no-same-owner --no-same-permissions -C /srv/akaine/repo/server -xzf "$backup"
sudo chown -R akaine:akaine /srv/akaine/repo/server/database
sudo chown akaine:akaine /srv/akaine/repo/server/config.py /srv/akaine/repo/server/.asset-signing.env
sudo chmod 0600 /srv/akaine/repo/server/config.py /srv/akaine/repo/server/.asset-signing.env
if [ -f /srv/akaine/repo/server/.lygus.env ]; then
  sudo chown akaine:akaine /srv/akaine/repo/server/.lygus.env
  sudo chmod 0600 /srv/akaine/repo/server/.lygus.env
fi

sudo -u akaine /srv/akaine/repo/.venv/bin/python - <<'PY'
import sqlite3
from pathlib import Path
root = Path('/srv/akaine/repo/server/database')
for path in sorted(root.glob('*.db')):
    with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as db:
        assert db.execute('PRAGMA quick_check').fetchone()[0] == 'ok', path
    print(path.name, 'ok')
PY

sudo systemctl start arcaea-server.service
if [ -f /srv/akaine/repo/server/.lygus.env ]; then sudo systemctl start lygus-bot.service; fi
curl --fail --silent --show-error http://127.0.0.1:18080/
```

The SQLite checks must say `ok` and the HTTP check must return `Hello World!`.
The archive cannot repair missing R2 objects. Restore those from the verified
resource kit or another bucket backup, then repeat the CDN checks in chapter 5.

Next: [Build the Android client](06-build-android-client.md).
