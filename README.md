# Akaine

A step-by-step English guide for setting up your own Akaine-compatible 7.0
server. It is written for readers who have never rented a server, configured a
domain, used Cloudflare, or built an Android application before.

The guide and its source code are kept together here. Client files and game
content are supplied separately through the private resource kit when the
walkthrough reaches that step.

## What you will build

By the end of the guide you will have:

- a Linux server running on Amazon Lightsail;
- a domain protected by Cloudflare;
- a private-server API reachable over HTTPS;
- a private resource store for bundles and song files;
- an Android client configured for your domain;
- a Discord bot for accounts and score tools;
- a backup and recovery routine.

## Before you start

Set aside one uninterrupted afternoon for the first setup. You need:

- a Windows 10 or Windows 11 computer with at least 30 GB free;
- an Android phone or a computer capable of running an Android emulator;
- a payment card accepted by AWS and your domain registrar;
- an email address you control and can protect with two-factor authentication;
- the private Akaine resource kit and its expected SHA-256 value.

For a new setup, the first six months can be almost free. New AWS customers can
receive up to USD 200 in credits for up to six months, which can cover the
Lightsail server used by this guide. Eligible Vietnamese citizens aged 18–23
can register one `.id.vn` domain free for two years through participating `.vn`
registrars such as iNET. If you are not eligible, promotional domains can start
at roughly 40,000 VND, although the renewal price may be higher.

Cloudflare DNS, CDN and SSL use the Free plan. R2 includes 10 GB of Standard
storage each month, and extra storage costs USD 0.015 per GB-month. For this
project, the R2 bill will normally remain below USD 1 per month unless you store
many duplicate releases or receive unusually heavy traffic.

When the AWS credits expire, you can keep the same Lightsail server as a paid
service, move to a cheaper VPS, or migrate to another provider after you are
more comfortable managing Linux.

## Start the guide

1. [See how the system works](docs/guide/01-architecture.md).
2. [Create the cloud server and connect a domain](docs/guide/02-cloud-domain.md).
3. [Prepare your Windows computer](docs/guide/03-workstation.md).
4. [Get and verify the private resource kit](docs/guide/04-private-resources.md).
5. [Configure R2, protected downloads and caching](docs/guide/05-cloudflare-content.md).

Start with chapter one and continue in order. Every later chapter assumes the
previous chapter's checks have passed.

## Private resources

The APK input, game assets and content bundles are distributed separately.
Obtain them privately from the project owner or another authorized provider.
The kit includes a manifest so you can verify every file before using it.

## License and ownership

Akaine-owned source contributions are published under the MIT License.
Third-party code keeps its original license. The MIT License does not grant
permission to redistribute commercial game clients, music, charts, artwork or
other material owned by someone else. Attribution for included third-party
components is recorded in [Third-party notices](THIRD_PARTY_NOTICES.md).
