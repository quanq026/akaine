# Prepare the Arcaea 7.3.1 client

[Tiếng Việt](vi/06-build-android-client.md)

1. [Download the ARM64 XAPK from APKPure](https://d.apkpure.net/b/XAPK/moe.low.arc?versionCode=1210500&nc=arm64-v8a&sv=24). Choose **7.3.1 (1210500)**.
2. Prepare Python, Java 17 and APKEditor 1.4.9 using [the workstation guide](03-workstation.md).
3. Open PowerShell in the repo and run the command below. Paste the file paths when asked.

```powershell
$source = Read-Host "Path to the downloaded ARM64 XAPK"
$editor = Read-Host "Path to APKEditor-1.4.9.jar"
$java = (Get-Command java.exe).Source
$output = Join-Path $env:USERPROFILE ("Akaine-7.3.1-input-" + (Get-Date -Format yyyyMMdd-HHmmss))
python -m akaine_build.android --source $source --java $java --apkeditor $editor --output $output
```

When you see `Verified original APK`, the output folder contains the hash-verified stock `merged.apk`. The repo contains the [Android, native and CLI patch source](../../patches/arcaea-7.3.1-arm64/). Applying the patches and signing a complete Akaine APK still requires a separate build. If you already have a compatible Akaine 7.3.1 client, see [server setup](05a-install-game-server.md).
