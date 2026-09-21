# How Akaine works

Akaine consists of an Android client, a Python server, a database and a content
store. This chapter explains how those pieces communicate. The same names
appear throughout the setup instructions.

## The five main parts

### 1. Android client

This is the game application installed on a phone or emulator. It displays the
menus, plays music and charts, and sends login or score requests to your
server. The client must be configured to use your domain instead of somebody
else's server.

### 2. Game server

The game server is a Python application on a Linux computer in the cloud. It
handles accounts, login, owned songs, partners, saves, scores, World Mode and
content-download URLs.

This guide uses Amazon Lightsail, which provides a Linux computer billed by the
month. You administer it remotely over SSH.

### 3. Database

The server stores accounts, scores and player progress in SQLite files on the
same machine. No separate database service is required.

The database is private. It must never be uploaded to GitHub or shared with a
resource kit because it may contain player information.

### 4. Cloudflare and R2

Cloudflare provides two services here:

- **DNS** connects names such as `api.example.com` to your server's IP address.
- **R2 object storage** stores large files such as bundles and song resources
  without placing them in Git.

It also handles HTTPS proxying and caches public files near players.

### 5. Discord bot

Lygus Bot is optional. It creates and links accounts, displays profiles and
recent plays, and renders B30 images. It runs on the server and reads the same
game database.

## What happens when a player logs in

1. The Android client sends an HTTPS request to `api.example.com`.
2. DNS tells the client how to reach Cloudflare.
3. Cloudflare forwards the request to the fixed IP address of your Lightsail
   server.
4. nginx receives the encrypted web request and passes it to the Python game
   server running privately on the same machine.
5. The Python server checks the SQLite database and sends a response.
6. Cloudflare returns that response to the Android client.

```text
Android client
      |
      | HTTPS request to api.example.com
      v
Cloudflare DNS and HTTPS proxy
      |
      v
Lightsail fixed IP
      |
      v
nginx -> Python game server -> SQLite database
```

## What happens when a song is downloaded

For large files, the game server returns a download URL instead of transferring
the file itself. The client then downloads from the R2-backed asset host.
Protected charts use short-lived signed URLs, so unauthenticated visitors cannot
list or download the private store.

```text
Client asks game server for a song
      |
Game server checks the account and creates download URLs
      |
Client downloads approved files from assets.example.com / R2
```

## Link Play is different

Normal API requests use HTTPS. Link Play uses direct TCP and UDP connections
for real-time rooms. Cloudflare's free HTTP proxy does not carry those game
ports, so `link.example.com` points directly to the Lightsail fixed IP and uses
the **DNS only** setting.

## Where the files come from

GitHub contains the server, Discord bot, build tools and documentation. The
private resource kit contains files that cannot be stored in the public source
repository.

You create your own AWS, Cloudflare and Discord credentials during setup. Keep
them with your player database, logs and signing key on systems you control.
None of those files belongs in GitHub or a shared resource kit.

## Before continuing

The SQLite database on Lightsail stores player data. Cloudflare connects the
domain to the server, and R2 stores bundles and song files. Link Play connects
directly to Lightsail for its TCP and UDP traffic.

Next: [Create the cloud server and connect a domain](02-cloud-domain.md).
