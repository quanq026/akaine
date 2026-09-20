# How Akaine works

Before buying anything, it helps to understand what you are building. Akaine
is not one program. It is a small group of services that cooperate with an
Android client.

You do not need to memorize this chapter. Its purpose is to make the names in
later chapters feel familiar.

## The five main parts

### 1. Android client

This is the game application installed on a phone or emulator. It displays the
menus, plays music and charts, and sends login or score requests to your
server. The client must be configured to use your domain instead of somebody
else's server.

### 2. Game server

The game server is a Python application running on a Linux computer in the
cloud. It handles accounts, login, owned songs, partners, saves, scores, world
mode and the URLs used to download content.

The guide uses an Amazon Lightsail virtual server. A virtual server is simply
a Linux computer rented by the month. You connect to it remotely using SSH.

### 3. Database

The server stores accounts, scores and player progress in SQLite database
files. SQLite keeps the database in files on the server rather than requiring
a separate database company or service.

The database is private. It must never be uploaded to GitHub or shared with a
resource kit because it may contain player information.

### 4. Cloudflare and R2

Cloudflare has two jobs in this setup:

- **DNS** connects names such as `api.example.com` to your server's IP address.
- **R2 object storage** stores large files such as bundles and song resources
  without placing them in Git.

Cloudflare can also proxy HTTPS traffic and cache public files close to users.

### 5. Discord bot

Lygus Bot is an optional companion service. It can create or link accounts,
show profiles and recent plays, and generate B30 images. It runs beside the
game server and uses the same game database.

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

The game server does not need to send every large file itself. It returns a
download URL. The client downloads the file from the asset host, which is
backed by Cloudflare R2. Protected chart files use short-lived signed URLs so a
random visitor cannot simply list and download the entire private store.

```text
Client asks game server for a song
      |
Game server checks the account and creates download URLs
      |
Client downloads approved files from assets.example.com / R2
```

## Link Play is different

Normal API requests use HTTPS. Link Play also needs direct TCP and UDP traffic
for real-time rooms. The free Cloudflare proxy does not carry these arbitrary
game ports, so `link.example.com` points directly to the Lightsail fixed IP and
is marked **DNS only** in Cloudflare.

## Where the files come from

GitHub provides the server source, Discord bot, build tools and this guide.
The private resource kit supplies the larger client and content files that are
not part of the source repository.

During setup, you will create your own AWS, Cloudflare and Discord credentials.
Those credentials belong only to your installation. Your player database,
server logs and release signing key also stay on systems you control; they are
never shared as part of the guide or resource kit.

## Before you continue

Keep this picture in mind: the SQLite database on Lightsail stores player
scores, Cloudflare DNS connects your domain to the server, and R2 holds the
large song and bundle files. Link Play points directly to Lightsail because its
TCP and UDP traffic does not travel through the normal free HTTPS proxy.

Next: [Create the cloud server and connect a domain](02-cloud-domain.md).
