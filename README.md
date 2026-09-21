# Akaine

Akaine is an English setup guide and public source repository for an
Akaine-compatible 7.0 server. It starts from an empty Windows computer and a
new cloud account, so you do not need previous Linux, Cloudflare or Android
build experience.

The repository contains the guide, server and build tools. The APK input and
game content are supplied separately when the guide needs them.

## What you will build

Following the chapters gives you:

- a Linux server running on Amazon Lightsail;
- a domain protected by Cloudflare;
- a private-server API reachable over HTTPS;
- a private resource store for bundles and song files;
- an Android client configured for your domain;
- a Discord bot for accounts and score tools;
- a backup and recovery routine.

## Before you start

The first setup usually takes an uninterrupted afternoon. You need:

- a Windows 10 or Windows 11 computer with at least 30 GB free;
- an Android phone or a computer capable of running an Android emulator;
- a payment card accepted by AWS and your domain registrar;
- an email address you control and can protect with two-factor authentication;
- the private Akaine resource kit and its expected SHA-256 value.

New AWS customers may receive up to USD 200 in credits for six months, enough
to cover the Lightsail server during the initial setup period. Vietnamese
citizens aged 18 to 23 may also qualify for one free `.id.vn` domain for two
years through participating `.vn` registrars such as iNET. Promotional domains
can start at roughly 40,000 VND, but check the renewal price before buying.

Cloudflare DNS, CDN and SSL use the Free plan. R2 includes 10 GB of Standard
storage each month, and extra storage costs USD 0.015 per GB-month. For a small
installation, the R2 bill is usually below USD 1 per month unless you keep many
duplicate releases or serve unusually heavy traffic.

When the AWS credits expire, you can pay for the same Lightsail server or move
the installation to another VPS provider.

## Start the guide

1. [See how the system works](docs/guide/01-architecture.md).
2. [Create the cloud server and connect a domain](docs/guide/02-cloud-domain.md).
3. [Prepare your Windows computer](docs/guide/03-workstation.md).
4. [Get and verify the private resource kit](docs/guide/04-private-resources.md).
5. [Configure R2, protected downloads and caching](docs/guide/05-cloudflare-content.md).
6. [Build, sign and test the Android client](docs/guide/06-build-android-client.md).

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
