# Set up Akaine 7.0.255 from scratch

This walkthrough builds an Akaine server and Android client for Arcaea
`7.0.255` (`1209852`). It starts with the basics and uses the same example names
in each chapter. Read it in order: later commands assume that the earlier
checks have passed. Do not use its APK hashes or patches with another client
version.

## Example used in the guide

Replace these examples with your own values when instructed:

| Item | Example |
| --- | --- |
| Domain | `example.com` |
| Game API | `api.example.com` |
| Link Play host | `link.example.com` |
| Asset host | `assets.example.com` |
| Lightsail instance | `akaine-server` |
| Lightsail region | Singapore (`ap-southeast-1`) |

Do not literally register `example.com`; it is reserved for documentation.

## How to use this guide if you are new

Keep this page open and complete one chapter at a time. Do not copy every
command in the guide into one terminal at once. Each command belongs to one of
three places:

- **PowerShell** means a Windows PowerShell window on your computer;
- **server shell** means the Linux terminal after connecting to Lightsail with
  SSH;
- **Cloudflare/AWS dashboard** means clicking the named controls in a web
  browser, not typing the labels into a terminal.

When a command asks a question, type only the requested value. Text such as
`example.com`, `ACCOUNT_ID` and `MANIFEST-FILENAME` is a placeholder until the
step explicitly tells you to replace it. Keep the same PowerShell window while
a chapter uses variables beginning with `$`. If you close it, files remain on
disk, but you must rerun that chapter's variable-setting block.

Every verification is a stop gate. If the displayed value differs, the command
returns a non-zero exit code, or a required file is missing, remain on that
step. Save the first error before retrying. A file created by a failed command
is not evidence that the step succeeded.

## Part 1: foundation

1. [Understand how Akaine works](01-architecture.md).
2. [Create AWS, Lightsail, Cloudflare and DNS](02-cloud-domain.md).
3. [Prepare your Windows computer](03-workstation.md).
4. [Get and verify the private resource kit](04-private-resources.md).
5. [Configure R2, protected downloads and caching](05-cloudflare-content.md).

Part 1 leaves you with secured cloud accounts, a Lightsail server with a fixed
IP address, Cloudflare DNS and the required tools on your Windows computer.

## Part 2: Android client

6. [Build, sign and test the Android client](06-build-android-client.md).

Chapter 6 builds and tests the Android client from the verified upstream XAPK
and the patch source in this repository.

## Part 3: content releases

7. [Build, verify and release a content bundle](07-build-release-content-bundle.md).

Chapter 7 starts from a verified 7.0.255 full-root bundle, applies a controlled
overlay, tests it on staging and promotes the same immutable bytes to
production.

## Part 4: lessons from operation

8. [Lessons and failures from building Akaine 7.0.255](08-lessons-and-failures.md).

Chapter 8 explains incidents that shaped the checks used throughout the guide:
misrouted API calls, bundle boot loops, selector gates, download contracts,
emulator false positives, CDN diagnosis and release rollback.

## Part 5: extend the catalogue

9. [Add a fan chart and place it in a pack](09-add-fan-chart.md).

Chapter 9 explains how one fan chart moves through pack/song catalogues,
selector assets, AKFC encryption, protected R2 delivery, server metadata,
chart constants, staging and final runtime checks.
