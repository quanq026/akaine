# Publish a prepared 7.3.1 bundle

[Tiếng Việt](vi/07-build-release-content-bundle.md)

1. Obtain a 7.3.1 full bundle with its JSON manifest and every `.cb` part. Check that `applicationVersionNumber` is `7.3.1`, `previousVersionNumber` is `null`, and the manifest has catalogue tags for songlist, packlist and unlocks.
2. Upload the parts to [R2](05-cloudflare-content.md) under their exact names. Give each release a separate prefix so you can roll back.
3. Follow [the server chapter](05a-install-game-server.md) to install the manifest and configure its SHA-256 and R2 URL. Verify that a fresh client receives the bundle and an up-to-date client receives no update.

The public workflow publishes a prepared bundle. A public builder from raw 7.3.1 assets is still pending.
