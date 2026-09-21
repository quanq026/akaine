# Build the Android client

Build an installable Akaine client from the verified Arcaea 7.0.255 XAPK. The
process mirrors the current 7.0 release pipeline: verify the input, merge its
splits, patch the managed and native code, align and sign the APK, then install
it and collect logs.

Download the original application yourself; the commercial APK and signing
keys are not stored in this repository. GitHub contains the build process,
verification code and version-locked native and Smali patches.

## What "matches the release" means

The current reference client has this contract:

- application label: `AkaineXD`;
- package: `akai.arc.lmao`;
- version name: `7.0.255`;
- version code: `1209852`;
- production API routes, not staging routes;
- Divine display and preview fixes;
- Final Verdict and Axium Crisis BYD selection fixes;
- complete AKFC protected-chart runtime;
- Aether Crest ETR null guard;
- no diagnostic-only hooks or tags;
- content-bundle target `7.0.255.8`.

The reference APK SHA-256 is
`18fb7f69aa4677ee3a04235e02658c3f2b56cc92fb3a4eee78172a292271b042`.
That hash identifies the published artifact; it is not the expected hash of a
client signed with your own key. A different signing key necessarily produces
different APK bytes.

Two builds can behave the same without having the same APK hash:

- the same verified input, patch payloads and configuration reproduce the same
  application behavior;
- the same signing identity is also required for an install-over update;
- the exact archive ordering, timestamps and signer are required for a
  byte-identical APK.

Never copy another operator's signing key. Generate and protect your own.

## Download the exact upstream XAPK

The target is Arcaea `7.0.255` (`1209852`), package `moe.low.arc`, Android
`arm64-v8a`. APKPure distributes this version as an XAPK containing five APK
modules.
Select the arm64 variant, not the armeabi-v7a variant.

At the time this pipeline was verified, the arm64 XAPK had:

```text
SHA-256  459bb01f8357dde82b13a817d4dd5dbf81e7a70d0805cc0d5f1aebde36fa2b7a
Size     1219427332 bytes
Splits   base, arcassets, config.arm64_v8a, config.en, config.mdpi
```

After downloading, select the file and verify it before opening it:

```powershell
$xapk = Get-Item (Read-Host "Full path to the downloaded 7.0.255 arm64 XAPK")
Get-Item $xapk.FullName | Select-Object Name, Length
Get-FileHash -Algorithm SHA256 $xapk.FullName
```

Both size and SHA-256 must match. A file for 7.0.256, an armeabi-v7a variant or
a repacked mirror is not an interchangeable input. Native offsets and expected
bytes are tied to this exact build.

## Merge the XAPK splits into one baseline APK

Download `APKEditor-1.4.9.jar` from the official `REAndroid/APKEditor` GitHub
release. Verify the tool before running it:

```text
SHA-256  a9cd40df818845456be6d696de6110c89edf4b0a0580cb83438ed6b25a366e67
Size     7733037 bytes
```

Choose where to keep the tool and baseline output:

```powershell
$apkEditor = Get-Item (Read-Host "Full path to APKEditor-1.4.9.jar")
$baseline = Read-Host "Full output path for the merged baseline APK"
$baseline = [IO.Path]::GetFullPath($baseline)

Get-FileHash -Algorithm SHA256 $apkEditor.FullName
java -Xmx4g -jar $apkEditor.FullName merge `
  -i $xapk.FullName `
  -o $baseline
```

Do not simply rename `.xapk` to `.apk`. The base package does not contain the
arm64 native libraries and asset module by itself. APKEditor merges the five
modules and sanitizes the split-required manifest declarations.

The merged baseline used for this project has:

```text
SHA-256  746dd90c2efac21fc88ffd032e5a71c78c0955766477382c7f48ece87e23026e
Size     1206740473 bytes
```

Check its identity:

```powershell
$buildTools = Get-ChildItem (Join-Path $sdk "build-tools") -Directory |
  Sort-Object Name -Descending |
  Select-Object -First 1
$aapt = Join-Path $buildTools.FullName "aapt.exe"

& $aapt dump badging $baseline |
  Select-String "package:|application-label:|launchable-activity:"
```

It must still report package `moe.low.arc`, label `Arcaea`, version name
`7.0.255`, version code `1209852` and launchable activity
`low.moe.AppActivity`. The old split signature no longer verifies after merge;
that is expected because the final APK will be aligned and signed later.

## Before building

Complete chapters 3 and 4. Then open PowerShell and load the locations you
selected earlier:

```powershell
$repoRoot = [Environment]::GetEnvironmentVariable("AKAINE_REPO_ROOT", "User")
$kitRoot = [Environment]::GetEnvironmentVariable("AKAINE_KIT_ROOT", "User")
$sdk = [Environment]::GetEnvironmentVariable("ANDROID_SDK_ROOT", "User")

Set-Location $repoRoot
python scripts\doctor.py --android
```

Do not continue unless the strict tool check passes.

## Understand the public patch set

The complete transformation is assembled from public source in this
repository:

- `patch_android_client_sources.py` changes the decoded manifest, label,
  package references and AKFC lifecycle calls;
- `AkfcLoader.smali` is the managed JNI bridge;
- `akfc_loader.cpp` implements protected-chart loading;
- the key scripts generate a different RSA-3072 identity for each operator;
- `build_boringssl_android.py` builds the loader's crypto dependency from a
  pinned public revision;
- `native-plan.json` applies guarded before/after byte operations to the two
  original native libraries.

No patched `.dex` or `.so` is downloaded from Akaine. The only non-source input
is the verified upstream XAPK.

## What the native release patch does

The 7.0 native patch is version-specific. Every operation checks the original
bytes before writing because offsets from another client version are unsafe.

The accepted release contains these behavior changes:

1. **Production routing.** The shared encrypted API base and literal auth,
   aggregate and bundle routes point to production. Replacement strings must
   fit their original native storage; shorter values are NUL-padded. A longer
   hostname must use a shorter DNS name or a server-side route instead of
   overflowing the binary.
2. **Divine visibility and preview.** The relevant reveal cells are enabled
   without globally unlocking unrelated state. Preview resources remain a
   bundle concern; the APK patch only fixes the client-side selection logic.
3. **Final Verdict BYD registry.** The allowlist contains `pentiment`,
   `arcanaeden`, `worldender`, `testify`, `infinitestrife`, `last` and
   `lasteternity`.
4. **Axium Crisis BYD registry.** `axiumcrisis` class 3 follows the same safe
   allowlisted path so Axium Divergence becomes selectable.
5. **Aether Crest ETR guard.** A missing special-condition list skips its
   enumeration; the normal non-null path is unchanged.
6. **AKFC runtime.** The APK contains the loader, crypto library and matching
   managed integration. This is one feature unit, not three optional patches.

The guarded byte operations for items 1 through 5 and the FMOD error-18 repair are
published in
`patches/arcaea-7.0.255-arm64/native-plan.json`. They are generated from the
verified APKPure baseline and can be reproduced without a pre-patched native
library. See the README beside that plan for the exact command and receipt
checks.

The package rename and managed AKFC bridge are also public in
`scripts/patch_android_client_sources.py` and the `smali` folder beside the
native plan. Their README pins the Apktool version and gives the exact decode
and patch commands.

The same README now includes the AKFC loader C++ source build. Each operator
generates a different 3072-bit RSA key pair locally; the private key is embedded
only into that operator's loader and the public key is used to encrypt charts.

## Step 1: choose build locations

```powershell
$outputFolder = Read-Host "Full path for build output"
$outputFolder = [IO.Path]::GetFullPath($outputFolder)
New-Item -ItemType Directory -Force $outputFolder | Out-Null

$decoded = Join-Path $outputFolder "decoded"
$managedApk = Join-Path $outputFolder "AkaineXD-managed-unsigned.apk"
$unsignedApk = Join-Path $outputFolder "AkaineXD-unsigned.apk"
$alignedApk = Join-Path $outputFolder "AkaineXD-aligned.apk"
$signedApk = Join-Path $outputFolder "AkaineXD-release.apk"
```

## Step 2: decode the merged baseline

```powershell
$apktool = Get-Item (Read-Host "Full path to apktool_2.12.1.jar")
Get-FileHash -Algorithm SHA256 $apktool.FullName

java -Xmx6g -jar $apktool.FullName decode -f `
  $baseline `
  -o $decoded
```

The Apktool jar must be 25,926,183 bytes with SHA-256
`66cf4524a4a45a7f56567d08b2c9b6ec237bcdd78cee69fd4a59c8a0243aeafa`.

## Step 3: patch the managed sources

```powershell
Set-Location $repoRoot
python scripts\patch_android_client_sources.py `
  --decoded $decoded `
  --receipt (Join-Path $outputFolder "managed-patch-receipt.json")
```

This changes only exact version-locked source strings and adds the public Smali
bridge. Any missing or duplicate match stops the build.

## Step 4: generate this server's AKFC key

```powershell
$keyFolder = Read-Host "Private folder for this server's AKFC keys"
$keyFolder = [IO.Path]::GetFullPath($keyFolder)
$privateKey = Join-Path $keyFolder "akfc-private.pem"
$publicKey = Join-Path $keyFolder "akfc-public.pem"
$keyHeader = Join-Path $keyFolder "embedded_key.h"

python scripts\generate_akfc_keypair.py `
  --private-key $privateKey `
  --public-key $publicKey

python scripts\generate_akfc_key_header.py `
  --private-key $privateKey `
  --output $keyHeader
```

Keep the private key and generated header outside Git. The server uses the
public key when encrypting AFF containers.

## Step 5: build AKFC native dependencies

Install **NDK (Side by side)** and **CMake** from Android Studio's SDK Tools,
then select the NDK folder:

```powershell
$env:ANDROID_NDK_ROOT = Read-Host "Full path to the installed Android NDK"
$loader = Join-Path $outputFolder "libakfcloader.so"
$crypto = Join-Path $outputFolder "libcrypto.so"
$cryptoWork = Join-Path $outputFolder "boringssl-work"

python scripts\build_akfc_loader.py `
  --source patches\arcaea-7.0.255-arm64\native\akfc_loader.cpp `
  --key-header $keyHeader `
  --output $loader

python scripts\build_boringssl_android.py `
  --work $cryptoWork `
  --output $crypto

$nativeFolder = Join-Path $decoded "lib\arm64-v8a"
Copy-Item $loader (Join-Path $nativeFolder "libakfcloader.so")
Copy-Item $crypto (Join-Path $nativeFolder "libcrypto.so")
```

The BoringSSL builder pins its Git revision and verifies all loader symbols.

## Step 6: rebuild and apply guarded native patches

```powershell
java -Xmx6g -jar $apktool.FullName build `
  $decoded `
  -o $managedApk

python scripts\build_android_client.py `
  --source $managedApk `
  --plan patches\arcaea-7.0.255-arm64\native-plan.json `
  --kit-root $repoRoot `
  --output $unsignedApk

Get-Content "$unsignedApk.receipt.json"
```

The receipt must list all 16 native labels. The plan guards the exact original
`libcocos2dcpp.so` and `libfmodProvider.so` hashes even though Apktool changes
the surrounding ZIP container.

## Step 7: find Android Build-Tools

Use the newest installed Build-Tools folder instead of assuming a version or
drive:

```powershell
$buildTools = Get-ChildItem (Join-Path $sdk "build-tools") -Directory |
  Sort-Object Name -Descending |
  Select-Object -First 1

$zipalign = Join-Path $buildTools.FullName "zipalign.exe"
$apksigner = Join-Path $buildTools.FullName "apksigner.bat"
$aapt = Join-Path $buildTools.FullName "aapt.exe"

Get-Item $zipalign, $apksigner, $aapt
```

All three files must exist.

## Step 8: align the APK

Native libraries require page alignment. The release pipeline uses 16 KiB page
alignment and 4-byte ZIP alignment:

```powershell
& $zipalign -P 16 -f -v 4 $unsignedApk $alignedApk
& $zipalign -c -P 16 -v 4 $alignedApk
```

The second command must finish with `Verification successful`.

## Step 9: create your signing identity once

Choose a private keystore location and alias. If you already created a key for
this package, reuse it; creating a new key makes install-over updates
impossible.

```powershell
$keystore = Read-Host "Full path for your private Android keystore"
$keystore = [IO.Path]::GetFullPath($keystore)
$keyAlias = Read-Host "Key alias"

if (-not (Test-Path $keystore)) {
  New-Item -ItemType Directory -Force (Split-Path -Parent $keystore) | Out-Null
  keytool -genkeypair `
    -keystore $keystore `
    -alias $keyAlias `
    -keyalg RSA `
    -keysize 4096 `
    -validity 10000
}
```

`keytool` asks for passwords and certificate identity interactively. Store the
passwords in a password manager. Never put the keystore or passwords in Git,
the resource kit, a screenshot or a shell script.

Back up this keystore securely. Losing it means future APKs cannot update the
installed application without uninstalling and deleting its local data.

## Step 10: sign and verify

```powershell
& $apksigner sign `
  --ks $keystore `
  --ks-key-alias $keyAlias `
  --v4-signing-enabled false `
  --out $signedApk `
  $alignedApk

& $apksigner verify --verbose --print-certs $signedApk
```

The verification must report v2 and v3 signatures as verified. Record the
signer certificate SHA-256; every later build for the same package must report
the same value.

## Step 11: inspect package and version

```powershell
$badging = & $aapt dump badging $signedApk
$badging | Select-String "package:|application-label:|launchable-activity:"
```

For the current reference contract it must show `akai.arc.lmao`, `AkaineXD`, version
`7.0.255`, version code `1209852` and `low.moe.AppActivity`.

Also record the artifact identity:

```powershell
Get-Item $signedApk | Select-Object Name, Length
Get-FileHash -Algorithm SHA256 $signedApk
```

## Step 12: choose fresh install or install-over

Connect the Android device or emulator and run:

```powershell
adb devices
$package = "akai.arc.lmao"
adb shell pm path $package
```

If the package is not installed, perform a fresh install:

```powershell
adb install $signedApk
```

Use install-over only when the installed package has the same signing
certificate:

```powershell
adb install -r -d $signedApk
```

`INSTALL_FAILED_UPDATE_INCOMPATIBLE` means the signer differs. Do not uninstall
automatically: uninstalling deletes local application data. Either sign with
the original key or make an explicit backup-and-fresh-install decision.

## Step 13: launch with a clean log

```powershell
$package = "akai.arc.lmao"
$activity = "low.moe.AppActivity"

adb logcat -c
adb shell am force-stop $package
adb shell am start -n "$package/$activity"
Start-Sleep -Seconds 10
adb shell pidof $package
```

A PID only shows that the process is alive. Save the complete log before
reproducing a problem:

```powershell
$logFile = Join-Path $outputFolder "client-logcat.txt"
adb logcat -d | Set-Content -Encoding utf8 $logFile

Select-String -Path $logFile -Pattern `
  "Fatal signal","FATAL EXCEPTION","JNI DETECTED ERROR", `
  "FileUtilsSaveError","LoadUnlocksMap","Cocos2dxDownloader", `
  "ClassNotFoundException","FMOD"
```

## Step 14: test the release contract

Test in this order so a failure identifies the responsible layer:

1. Reach the title screen without a boot loop.
2. Finish a fresh content-bundle download and restart the app.
3. Register or sign in.
4. Use **Cloud Sync → Download** and return to the title screen.
5. Open Music Play and wait for previews to play.
6. Open one ordinary official song and start a chart.
7. Check Divine songs for normal jackets and previews.
8. Check Final Verdict BYD for Infinite Strife, Arcana Eden, Pentiment, World
   Ender, Testify, Last and Last Eternity.
9. Check Axium Crisis BYD/Axium Divergence.
10. Open Aether Crest ETR.
11. Download and start one protected fan chart.
12. Restart the app and repeat one official and one protected chart.

Do not call the build release-ready after only reaching the title screen.

## Diagnose failures by stage

| Symptom | Likely layer | First check |
| --- | --- | --- |
| APK will not install | signing/alignment | `apksigner verify`, `zipalign -c`, signer mismatch |
| Crash before title after bundle reaches 100% | bundle catalogue integrity | every song set and child pack references an existing pack |
| Login or content bundle uses the wrong server | native route patch | plan input hash, production/staging route selection, URL byte budget |
| Music Play opens but one group is black | bundle selector assets | jacket and preview entries, not a global unlock flag |
| BYD tile is absent or cannot be selected | native registry gate | exact song ID and difficulty class in the verified allowlist |
| Aether Crest ETR crashes | native special-condition list | null guard is present in the selected patch plan |
| Protected chart downloads but will not start | AKFC runtime | loader, crypto library and DEX integration all come from one patch set |
| Download icon never clears | server metadata/object set | declared files, hashes and hidden shell charts match delivery |
| Works once, fails after restart | incomplete persisted content | collect logcat from cold start and inspect downloaded bundle state |

Never fix a bundle boot crash by deleting random pack entries. A pack cannot be
removed while a song `set` or child `pack_parent` still references it.

## Release checklist

Keep a small receipt for every candidate:

- source APK SHA-256;
- native patch plan SHA-256;
- output APK SHA-256 and size;
- package, label, version name and version code;
- signer certificate SHA-256;
- replaced APK members;
- API/bundle route target;
- bundle version tested;
- fresh install or install-over result;
- title, login, Cloud Sync, official chart, special BYD/ETR and protected-chart
  results;
- crash-pattern scan result;
- known issues that remain.

Keep the previous signed APK until the new candidate passes this checklist.
Rollback means reinstalling that known-good APK with the same signer; it does
not mean deleting application data or restoring an unrelated database.

## Files that stay private

GitHub intentionally does not contain:

- the source APK;
- prebuilt modified native libraries or DEX payloads;
- the production signing key;
- commercial game assets;
- private chart encryption material;
- production domains, credentials or player data.

The build process is public. Inputs that the project cannot redistribute remain
private and are verified by hash before use.
