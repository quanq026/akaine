# Arcaea 7.0.255 arm64 native patch

This directory contains the guarded native stage used by the AkaineXD 7.0
client. It applies directly to the standalone APK produced by merging the
verified APKPure arm64 XAPK described in chapter 6.

The plan changes 531 bytes in `libcocos2dcpp.so` and 25 bytes in
`libfmodProvider.so`. Every operation includes its expected original bytes. A
different client build stops at the first guard mismatch instead of writing to
an unverified offset.

Covered behavior:

- production auth, aggregate and content-bundle routes;
- Divine reveal/cell handling;
- Final Verdict and Axium Crisis BYD registry handling;
- Dread Area pre-start handling;
- Aether Crest ETR null guard;
- native crash-logger suppression retained by the release;
- FMOD error-18 read contract.

Run from the public repository folder:

```powershell
$baseline = Get-Item (Read-Host "Full path to the merged 7.0.255 arm64 baseline APK")
$output = Read-Host "Full output path for the native-patched unsigned APK"
$output = [IO.Path]::GetFullPath($output)

python scripts\build_android_client.py `
  --source $baseline.FullName `
  --plan patches\arcaea-7.0.255-arm64\native-plan.json `
  --kit-root . `
  --output $output
```

The receipt must list all 16 labels from `production-routes` through
`fmod-18-read-contract`. This stage deliberately leaves the ELF build-id note
unchanged, so the functional native output is not byte-identical to the old
release binary even though every executable patch range matches.

Do not sign this intermediate APK yet. The managed package/Smali and AKFC
loader stages must be applied before alignment and signing.

## Managed source patch

Decode the verified merged baseline with Apktool 2.12.1. The official jar used
for verification is 25,926,183 bytes with SHA-256
`66cf4524a4a45a7f56567d08b2c9b6ec237bcdd78cee69fd4a59c8a0243aeafa`.

```powershell
$apktool = Get-Item (Read-Host "Full path to apktool_2.12.1.jar")
$decoded = Read-Host "Full output folder for decoded sources"
$decoded = [IO.Path]::GetFullPath($decoded)

java -Xmx6g -jar $apktool.FullName decode -f `
  $baseline.FullName `
  -o $decoded

python scripts\patch_android_client_sources.py `
  --decoded $decoded `
  --receipt (Join-Path (Split-Path $decoded -Parent) "managed-patch-receipt.json")
```

The version-locked source patch:

- changes the package and provider authorities to `akai.arc.lmao`;
- changes the label to `AkaineXD`;
- updates `BuildConfig.APPLICATION_ID` and the share provider string;
- adds the small public `AkfcLoader.smali` bridge;
- initializes AKFC after FMOD libraries load and wipes decrypted temporary
  charts during activity destruction.

The script requires exact source strings and match counts. It stops rather than
guessing if a different version or already-patched source tree is supplied.

The remaining unpublished component is the native implementation loaded as
`libakfcloader.so`. Until its source reconstruction is complete, the fully
public pipeline ends at this managed-source stage; the old verified binary is
used only for private parity testing and is not stored in GitHub.
