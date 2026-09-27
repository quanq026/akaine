# Install the 7.0.255 game server

This chapter turns the empty Lightsail instance from chapter 2 into a running
game API. It uses the public server source and the content files verified in
chapter 4. Complete the R2 and Worker setup in chapter 5 first. The new
database starts without a game account. Chapter 5b explains how the optional
Discord bot creates one; the game also has its normal registration endpoint.

The public Android patch in chapter 6 contains the release's fixed API hosts.
For a different domain, its native routes must also be patched and verified for
that host. Running this chapter at `api.example.com` proves the server works;
it does not make the published AkaineXD APK connect to `api.example.com`.

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
sudo -u akaine /srv/akaine/repo/.venv/bin/python -m pip install -r /srv/akaine/repo/requirements-dev.txt
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
7.0.255 full-root manifest   -> database/bundle/<alias>.json
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
$bundleManifest = Get-Item (Read-Host "Full path to the verified 7.0.255 bundle manifest")

ssh -i $sshKey.FullName "ubuntu@$serverIp" "install -d -m 700 /home/ubuntu/akaine-intake"
if ($LASTEXITCODE -ne 0) { throw "Could not create the private intake folder." }

scp -i $sshKey.FullName $songlist.FullName "ubuntu@${serverIp}:/home/ubuntu/akaine-intake/songlist"
if ($LASTEXITCODE -ne 0) { throw "Songlist upload failed." }
scp -i $sshKey.FullName $songMetadata.FullName "ubuntu@${serverIp}:/home/ubuntu/akaine-intake/song_metadata.json"
if ($LASTEXITCODE -ne 0) { throw "Song metadata upload failed." }
scp -i $sshKey.FullName $bundleManifest.FullName "ubuntu@${serverIp}:/home/ubuntu/akaine-intake/$($bundleManifest.Name)"
if ($LASTEXITCODE -ne 0) { throw "Bundle manifest upload failed." }

"Bundle manifest name: $($bundleManifest.Name)"
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

sudo install -o akaine -g akaine -m 0644 /home/ubuntu/akaine-intake/songlist /srv/akaine/repo/server/database/songs/songlist
sudo install -o akaine -g akaine -m 0644 /home/ubuntu/akaine-intake/song_metadata.json /srv/akaine/repo/server/database/song_metadata.json
sudo install -o akaine -g akaine -m 0644 "/home/ubuntu/akaine-intake/$manifest_name" "/srv/akaine/repo/server/database/bundle/$manifest_name"
sudo -u akaine /srv/akaine/repo/.venv/bin/python - "$manifest_name" <<'PY'
import json, sys
from pathlib import Path
root = Path('/srv/akaine/repo/server/database')
manifest = root / 'bundle' / sys.argv[1]
data = json.loads(manifest.read_text())
assert data['applicationVersionNumber'] == '7.0.255'
assert data['previousVersionNumber'] is None
assert data['totalPartitions'] > 0
json.loads((root / 'songs/songlist').read_text(encoding='utf-8-sig'))
json.loads((root / 'song_metadata.json').read_text())
print('7.0.255 content files ready')
PY
```

The server reads the songlist for unlock and download decisions, metadata for
download filenames and checksums, and the manifest for bundle versions and
part URLs. Installing only the bundle manifest will not make song downloads
work. The last command must print `7.0.255 content files ready`.

## 4. Configure the 7.0.255 server

Copy the version-specific example. Keep credentials in the ignored `config.py`,
inside its `class Config`:

```bash
sudo -u akaine cp /srv/akaine/repo/server/config.7.0.255.example.py /srv/akaine/repo/server/config.py
sudo chmod 0600 /srv/akaine/repo/server/config.py
sudo -u akaine nano /srv/akaine/repo/server/config.py
```

Generate three distinct values in your password manager and set `USERNAME`,
`PASSWORD` and `SECRET_KEY` in the editor. Set every `assets.example.com` URL
to your real R2 custom domain. For protected songs, add the exact song IDs
from the private R2 `asset-manifest.json` to `ASSET_SIGNING_SONG_IDS` and keep
existing IDs when editing this list. The template disables Link Play for the
first server test. `chmod` limits the private configuration to its owner before
you enter credentials.

The template sets `GAME_API_PREFIX = '/'`, matching the current release's
root paths such as `/auth/login` and `/game/content_bundle`. It allows only
`7.0.255`, listens on `127.0.0.1:18080` behind nginx, and selects the newest
full-root bundle for an older client. The older `config.example.py` is an
upstream reference for other client versions; do not copy it for this setup.

Check the edited file without printing your secrets:

```bash
cd /srv/akaine/repo/server
sudo -u akaine /srv/akaine/repo/.venv/bin/python - <<'PY'
from config import Config
assert Config.GAME_API_PREFIX == '/'
assert Config.ALLOW_APPVERSION == ['7.0.255']
assert Config.USERNAME and Config.PASSWORD and Config.SECRET_KEY
assert 'example.com' not in Config.BUNDLE_DOWNLOAD_LINK_PREFIX
assert 'example.com' not in Config.ASSET_SIGNED_PREFIX
print('7.0.255 server configuration ready')
PY
```

If this prints a traceback, correct `config.py` and rerun the check. No server
restart is needed because it has not started yet.

## 5. Give the server the same Worker signing secret

Use the secret file created in chapter 5. In Windows PowerShell, send the value
over SSH standard input; the command does not display it:

```powershell
$secretFile = Get-Item (Read-Host "Full path to the signing-secret file from chapter 5")
$secretValue = (Get-Content -LiteralPath $secretFile.FullName -Raw).Trim()
if ([Convert]::FromBase64String($secretValue).Length -ne 32) {
  throw "The signing secret is not 32 bytes."
}

("ASSET_SIGNING_SECRET=" + $secretValue) |
  ssh -i $sshKey.FullName "ubuntu@$serverIp" "umask 077; cat > /home/ubuntu/akaine-intake/asset-signing.env"
if ($LASTEXITCODE -ne 0) { throw "Signing-secret transfer failed." }
```

In the Linux terminal:

```bash
set -e
sudo install -o akaine -g akaine -m 0600 /home/ubuntu/akaine-intake/asset-signing.env /srv/akaine/repo/server/.asset-signing.env
sudo stat -c '%a %U %G %n' /srv/akaine/repo/server/.asset-signing.env
```

The result must begin `600 akaine akaine`. The systemd service reads this
environment file; the public `config.py` template intentionally contains no
signing secret. Never print the environment file.

## 6. Start the service and check its local HTTP response

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

## 7. Put nginx and HTTPS in front of the service

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

## 8. Verify the bundle API through the public hostname

In Windows PowerShell, set `$apiHost` to your own hostname:

```powershell
$apiHost = Read-Host "Game API hostname without https://"
$bundleUrl = "https://$apiHost/game/content_bundle"
$response = Invoke-WebRequest -Uri $bundleUrl -Headers @{
  AppVersion = '7.0.255'
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
  throw "A fresh 7.0.255 client did not receive one bundle."
}

$body.value.orderedResults | Select-Object contentBundleVersion, appVersion, bundleSize

$targetVersion = $body.value.orderedResults[0].contentBundleVersion
$currentResponse = Invoke-RestMethod -Uri $bundleUrl -Headers @{
  AppVersion = '7.0.255'
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

## Client host checkpoint

The native plan in this public repository embeds the published Akaine API
hosts. A server on your own hostname passes the HTTP tests above, but that APK
will keep calling its embedded hosts. Before testing a client against your
server, inspect its native route destinations and build a version-guarded route
patch for your hostname, including the encrypted shared API base. Chapter 6
explains why login alone does not prove all routes changed. This repository
does not yet provide a general host-replacement command; stop at server
verification until that patch has been built and tested.

Next: [Run the optional Discord bot](05b-discord-bot.md), then
[back up the server](05c-backup-recovery.md).
