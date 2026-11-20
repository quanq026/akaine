# Install the 7.3.1 game server

This chapter runs the Akaine 7.3.1 API on Linux. Prepare [the bundle and R2 content](05-cloudflare-content.md) before setup. A fresh installation starts with an empty player database. To connect from the game, use an Akaine 7.3.1 APK built for your server hostname.

## 1. Prepare the Linux instance

The commands in this section run in the Lightsail SSH terminal. Sign in as
`ubuntu` using the key and static IP from chapter 2. Copy one block at a time.

```bash
set -e
sudo apt update
sudo apt install -y git nginx python3-venv nano

if ! id akaine >/dev/null 2>&1; then
  sudo useradd --system --user-group --home-dir /srv/akaine --shell /usr/sbin/nologin akaine
fi
sudo install -d -o akaine -g akaine -m 0750 /srv/akaine
```

`akaine` is a service account, separate from your SSH login. The server will
run under this account and write only to its own project directory. If an apt
command fails, stop here and resolve that error before cloning anything.

## 2. Install the public source and Python packages

Still in the Linux terminal. `set -e` stops the block on its first failed
command:

```bash
set -e
sudo -u akaine git clone https://github.com/quanq026/akaine.git /srv/akaine/repo
sudo -u akaine python3 -m venv /srv/akaine/repo/.venv
sudo -u akaine /srv/akaine/repo/.venv/bin/python -m pip install -r /srv/akaine/repo/server/requirements.txt
sudo install -d -o akaine -g akaine /srv/akaine/repo/server/log
sudo install -d -o akaine -g akaine /srv/akaine/repo/server/database/backup

sudo -u akaine /srv/akaine/repo/.venv/bin/python -c 'import flask, cryptography, waitress; print("Server packages ready")'
sudo -u akaine /srv/akaine/repo/.venv/bin/python -m compileall -q /srv/akaine/repo/server
```

The project has a `server/` directory inside the Git checkout. The Python
virtual environment lives at `/srv/akaine/repo/.venv`; the service template
uses that interpreter. The dependency file also prepares the optional Discord
bot in chapter 5b. The package check prints `Server packages ready`; successful
source compilation normally prints nothing.
These commands target a new, empty `/srv/akaine/repo`. If a repository already
exists there, inspect it rather than cloning over it.

## 3. Supply the verified content files

The public checkout does not contain the playable songlist or bundle bytes.
From the verified private kit, locate:

```text
server songlist              -> database/songs/songlist
server song metadata         -> database/song_metadata.json
matching native packlist      -> database/client_catalogs/7.3.1/packlist
7.3.1 full-root manifest      -> database/bundle/<alias>.json
bundle parts                  -> R2 bundle/<alias>_0.cb ...
```

The manifest and parts must have the same alias. Chapter 5 uploads the parts
to R2; this server needs only the manifest. If the kit lacks one of these files
or its verification fails, stop here and obtain the matching content set.

Open a new Windows PowerShell window. The following commands ask for the
actual file locations and upload them to your `ubuntu` account:

```powershell
$sshKey = Get-Item (Read-Host "Full path to the Lightsail SSH private key")
$serverIp = Read-Host "Lightsail static IPv4 address"
$songlist = Get-Item (Read-Host "Full path to the verified server songlist")
$songMetadata = Get-Item (Read-Host "Full path to the verified song_metadata.json")
$bundleManifest = Get-Item (Read-Host "Full path to the verified 7.3.1 bundle manifest")
$packlist = Get-Item (Read-Host "Full path to the matching native packlist")

ssh -i $sshKey.FullName "ubuntu@$serverIp" "install -d -m 700 /home/ubuntu/akaine-intake"
if ($LASTEXITCODE -ne 0) { throw "Could not create the private intake folder." }

scp -i $sshKey.FullName $songlist.FullName "ubuntu@${serverIp}:/home/ubuntu/akaine-intake/songlist"
if ($LASTEXITCODE -ne 0) { throw "Songlist upload failed." }
scp -i $sshKey.FullName $songMetadata.FullName "ubuntu@${serverIp}:/home/ubuntu/akaine-intake/song_metadata.json"
if ($LASTEXITCODE -ne 0) { throw "Song metadata upload failed." }
scp -i $sshKey.FullName $bundleManifest.FullName "ubuntu@${serverIp}:/home/ubuntu/akaine-intake/$($bundleManifest.Name)"
if ($LASTEXITCODE -ne 0) { throw "Bundle manifest upload failed." }

scp -i $sshKey.FullName $packlist.FullName "ubuntu@${serverIp}:/home/ubuntu/akaine-intake/packlist"
if ($LASTEXITCODE -ne 0) { throw "Packlist upload failed." }

"Bundle manifest name: $($bundleManifest.Name)"
"Packlist SHA256: $((Get-FileHash -Algorithm SHA256 $packlist.FullName).Hash.ToLowerInvariant())"
```

Return to the Linux SSH terminal and enter the manifest filename that
PowerShell printed:

```bash
set -e
read -r -p 'Bundle manifest filename: ' manifest_name
case "$manifest_name" in
  *[!A-Za-z0-9._-]*|'') echo 'Invalid filename' >&2; false ;;
esac
test -f "/home/ubuntu/akaine-intake/$manifest_name"

sudo install -d -o akaine -g akaine /srv/akaine/repo/server/database/client_catalogs/7.3.1
sudo install -o akaine -g akaine -m 0644 /home/ubuntu/akaine-intake/packlist /srv/akaine/repo/server/database/client_catalogs/7.3.1/packlist
sudo install -o akaine -g akaine -m 0644 /home/ubuntu/akaine-intake/songlist /srv/akaine/repo/server/database/songs/songlist
sudo install -o akaine -g akaine -m 0644 /home/ubuntu/akaine-intake/song_metadata.json /srv/akaine/repo/server/database/song_metadata.json
sudo install -o akaine -g akaine -m 0644 "/home/ubuntu/akaine-intake/$manifest_name" "/srv/akaine/repo/server/database/bundle/$manifest_name"
sudo -u akaine /srv/akaine/repo/.venv/bin/python - "$manifest_name" <<'PY'
import json, sys
from pathlib import Path
root = Path('/srv/akaine/repo/server/database')
manifest = root / 'bundle' / sys.argv[1]
data = json.loads(manifest.read_text())
assert data['applicationVersionNumber'] == '7.3.1'
assert data['previousVersionNumber'] is None
assert data['totalPartitions'] > 0
json.loads((root / 'songs/songlist').read_text(encoding='utf-8-sig'))
json.loads((root / 'song_metadata.json').read_text())
assert json.loads((root / 'client_catalogs/7.3.1/packlist').read_text())['packs']
print('7.3.1 content files ready')
PY
```

The server reads the songlist for unlock and download decisions, metadata for
download filenames and checksums, and the manifest for bundle versions and
part URLs. Installing only the bundle manifest will not make song downloads
work. The last command must print `7.3.1 content files ready`.

## 4. Configure the 7.3.1 server

Copy the sample and enter your settings in your private `config.py`.

```bash
sudo -u akaine cp /srv/akaine/repo/server/config.7.3.1.example.py /srv/akaine/repo/server/config.py
sudo chmod 0600 /srv/akaine/repo/server/config.py
sudo -u akaine nano /srv/akaine/repo/server/config.py
```

Set your admin name, password and secret key. Set the R2 bundle URL and your server HTTPS song download URL. The sample uses local port 18080. Replace `7.3.1.1` in both the target and epoch with the manifest’s `versionNumber`. Copy the SHA-256 for each of these four files into its matching config field.

```bash
cd /srv/akaine/repo/server
sha256sum database/songs/songlist database/song_metadata.json database/client_catalogs/7.3.1/packlist database/bundle/*.json
```

The sample serves individual songs from the server. For Worker-based song delivery, see [Cloudflare and R2 setup](05-cloudflare-content.md). Verify the configuration before starting.

```bash
cd /srv/akaine/repo/server
sudo -u akaine /srv/akaine/repo/.venv/bin/python -c 'import main; main.validate_runtime_config(); print("Server configuration ready")'
sudo -u akaine /srv/akaine/repo/.venv/bin/python tools/check_dynamic_pack_catalog.py
```

## 5. Start the service and check its local HTTP response

In the Linux terminal:

```bash
set -e
sudo install -o root -g root -m 0644 /srv/akaine/repo/server/arcaea-server.service /etc/systemd/system/arcaea-server.service
sudo systemctl daemon-reload
sudo systemctl enable --now arcaea-server.service
sudo systemctl is-active arcaea-server.service
curl --fail --silent --show-error http://127.0.0.1:18080/
```

The service must say `active` and the final command must return `Hello World!`.
If it does not, inspect `sudo journalctl -u arcaea-server.service -n 80 --no-pager`.
Missing content, invalid JSON, empty credentials and permission problems should
be fixed at their source. The service must be healthy locally before nginx is
configured.

## 6. Put nginx and HTTPS in front of the service

Keep the `api` DNS record **DNS only** until a certificate works. In the Linux
terminal, enter only the registered domain, without `api.` or `https://`:

```bash
set -e
read -r -p 'Registered domain: ' domain
case "$domain" in
  *[!A-Za-z0-9.-]*|'') echo 'Invalid domain' >&2; false ;;
esac

sudo install -o root -g root -m 0644 /srv/akaine/repo/server/nginx/akaine.conf.example /etc/nginx/sites-available/akaine
sudo sed -i "s/api.example.com/api.$domain/" /etc/nginx/sites-available/akaine
if [ ! -e /etc/nginx/sites-enabled/akaine ]; then
  sudo ln -s /etc/nginx/sites-available/akaine /etc/nginx/sites-enabled/akaine
fi
sudo nginx -t
sudo systemctl reload nginx
curl --fail --silent --show-error -H "Host: api.$domain" http://127.0.0.1/
```

The last command must return `Hello World!`. Obtain and install a certificate
with Certbot while DNS still points directly to this server:

```bash
set -e
sudo apt install -y snapd
sudo snap install --classic certbot
sudo /snap/bin/certbot --nginx -d "api.$domain"
sudo /snap/bin/certbot renew --dry-run
curl --fail --silent --show-error "https://api.$domain/"
```

Answer Certbot's email and terms prompts. The final command must return
`Hello World!` over HTTPS. In Cloudflare, change the `api` DNS record to
**Proxied** and choose **SSL/TLS → Overview → Full (strict)** only after the
certificate works. Leave `link` as DNS only.

Cloudflare's [Full (strict) requirements](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/)
include a valid certificate on the origin. Certbot's
[nginx instructions](https://certbot.eff.org/instructions?os=snap&ws=nginx)
describe the certificate and renewal commands.

## 7. Verify the bundle API through the public hostname

In Windows PowerShell, set `$apiHost` to your own hostname:

```powershell
$apiHost = Read-Host "Game API hostname without https://"
$bundleUrl = "https://$apiHost/game/content_bundle"
$response = Invoke-WebRequest -Uri $bundleUrl -Headers @{
  AppVersion = '7.3.1'
  ContentBundle = '0.0.0'
  DeviceId = 'guide-server-check'
}
$body = $response.Content | ConvertFrom-Json

if ($response.StatusCode -ne 200 -or -not $body.success) {
  throw "The content-bundle API did not respond successfully."
}
if ($response.Headers['Cache-Control'] -notmatch 'no-store') {
  throw "The content-bundle decision is missing no-store."
}
if (@($body.value.orderedResults).Count -ne 1) {
  throw "A fresh 7.3.1 client did not receive one bundle."
}

$body.value.orderedResults | Select-Object contentBundleVersion, appVersion, bundleSize

$targetVersion = $body.value.orderedResults[0].contentBundleVersion
$currentResponse = Invoke-RestMethod -Uri $bundleUrl -Headers @{
  AppVersion = '7.3.1'
  ContentBundle = $targetVersion
  DeviceId = 'guide-server-check'
}
if (@($currentResponse.value.orderedResults).Count -ne 0) {
  throw "A client already on the target bundle received another update."
}
"Current-version bundle check passed: $targetVersion"
```

The second request proves that a client already on the target version does
not download it again. The API hostname must never show a Cloudflare cache
`HIT` for this route. The bundle parts and song objects still need the
separate R2/CDN and client checks in chapters 5, 7 and 9.

## Create an account and check access

For Discord, follow [the bot chapter](05b-discord-bot.md) and run `/create`. For a server without the bot, create a test account in the Linux terminal. Enter the password when prompted.

```bash
cd /srv/akaine/repo/server
sudo -u akaine /srv/akaine/repo/.venv/bin/python tools/create_user_cli.py TestPlayer
```

New accounts receive the packs, single songs, characters and unlocks defined in your database. Sign in and choose **Cloud Sync → Download**. To check existing accounts after adding content, preview the repair.

```bash
sudo -u akaine /srv/akaine/repo/.venv/bin/python tools/create_user_cli.py --repair-existing all --dry-run
```

Read `expected_content` for the number of grants available in your database. The fields `inserted`, `raised_null_or_zero_to_one` and `full_characters_added` show what would be filled. Back up SQLite as shown in [chapter 5c](05c-backup-recovery.md) before removing `--dry-run` to apply. Replace `all` with a `user_id` to check one account.

## Updating PTT on an existing server

Skip this step on a fresh install. The server calculates PTT from Best 50, counting the top ten twice. The first command previews the change and the second saves a private SQLite backup before applying it.

```bash
cd /srv/akaine/repo/server
sudo -u akaine /srv/akaine/repo/.venv/bin/python -m tools.recompute_ptt database/arcaea_database.db
sudo -u akaine /srv/akaine/repo/.venv/bin/python -m tools.recompute_ptt database/arcaea_database.db --backup /srv/akaine/pre-b50.db
```

The script prints how many accounts changed. Use a fresh backup filename if you run it again after new scores arrive.

## Connect a client

To sign in from the game, use an Akaine 7.3.1 APK configured for your server hostname. If you do not have that APK yet, use the HTTP checks above to verify the server.

Next: [Run the optional Discord bot](05b-discord-bot.md), then
[back up the server](05c-backup-recovery.md).
