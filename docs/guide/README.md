# Set up Akaine from scratch

This walkthrough assumes you have never managed a cloud server. It explains
what each service does before asking you to configure it, and it uses the same
example names throughout.

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

## Part 1 — foundation

1. [Understand how Akaine works](01-architecture.md).
2. [Create AWS, Lightsail, Cloudflare and DNS](02-cloud-domain.md).
3. [Prepare your Windows computer](03-workstation.md).
4. [Get and verify the private resource kit](04-private-resources.md).
5. [Configure R2, protected downloads and caching](05-cloudflare-content.md).

At the end of Part 1 you should have a protected cloud account, a Lightsail
server with a fixed IP address, a domain managed by Cloudflare, and a local
computer with all required tools installed.

## Part 2 — Android client

6. [Build, sign and test the Android client](06-build-android-client.md).

This chapter produces and tests an Android client from the verified private
inputs.
