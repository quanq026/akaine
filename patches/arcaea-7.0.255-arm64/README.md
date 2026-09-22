# Arcaea 7.0.255 arm64 native patch

This directory contains the guarded native stage used by the AkaineXD 7.0.255
client. It applies directly to the standalone APK produced by merging the
verified APKPure arm64 XAPK described in chapter 6.

The plan changes 531 bytes in `libcocos2dcpp.so` and 25 bytes in
`libfmodProvider.so`. Every operation includes its expected original bytes. A
different client build stops at the first guard mismatch instead of writing to
an unverified offset.

Covered behavior:

- production shared API base plus auth, aggregate and content-bundle routes;
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

## Build the AKFC loader from source

Install **NDK (Side by side)** from Android Studio's SDK Manager. Select an NDK
folder and save it for the current terminal:

```powershell
$env:ANDROID_NDK_ROOT = Read-Host "Full path to the installed Android NDK"
$keyFolder = Read-Host "Private folder for this server's AKFC keys"
$keyFolder = [IO.Path]::GetFullPath($keyFolder)
$privateKey = Join-Path $keyFolder "akfc-private.pem"
$publicKey = Join-Path $keyFolder "akfc-public.pem"
$keyHeader = Join-Path $keyFolder "embedded_key.h"
$nativeFolder = Join-Path $decoded "lib\arm64-v8a"
$cryptoWork = Join-Path (Split-Path $decoded -Parent) "boringssl-work"
$crypto = Join-Path (Split-Path $decoded -Parent) "libakfc-crypto.a"

python scripts\generate_akfc_keypair.py `
  --private-key $privateKey `
  --public-key $publicKey

python scripts\generate_akfc_key_header.py `
  --private-key $privateKey `
  --output $keyHeader

python scripts\build_boringssl_android.py `
  --work $cryptoWork `
  --output $crypto

$loader = Join-Path (Split-Path $decoded -Parent) "libakfcloader.so"
python scripts\build_akfc_loader.py `
  --source patches\arcaea-7.0.255-arm64\native\akfc_loader.cpp `
  --key-header $keyHeader `
  --crypto $crypto `
  --output $loader
```

The source hooks the game library's `fopen`, `open`, `__open_2`, `stat`,
`lstat` and `fstatat` imports. It recognizes AKFC chart containers, unwraps the
per-file AES key with the operator's RSA key, authenticates AES-256-GCM using
the song/file identity, exposes the plaintext size to the game and wipes
temporary plaintext during shutdown.

The public source keeps the production hardening used by the release: logging
macros are compiled out and the test-only `decryptFile` JNI export is absent.
The private RSA key is generated locally and is never committed. The matching
public key is used by the server-side `server/core/akfc.py` encryption code.

Copy the compiled loader into the decoded APK before rebuilding:

```powershell
Copy-Item $loader (Join-Path $nativeFolder "libakfcloader.so")
```

The BoringSSL build is static and its symbols are prefixed with `akfc_` before
linking. Only `libakfcloader.so` is copied into the APK. Do not add or replace a
process-wide `libcrypto.so`; that can change unrelated client behavior such as
saved authentication state.
