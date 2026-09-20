# Build the Android client

This chapter turns a verified APK and a private patch set into an installable
Akaine client. It follows the same artifact pipeline used by the current 7.0
release: verify the input, apply only declared APK-member replacements, remove
the obsolete signature, align the archive, sign it, inspect the result, install
it and collect crash evidence.

The public repository does not contain the commercial APK, patched native
libraries, DEX payloads or signing keys. Those remain in the private resource
kit. The public builder only describes and verifies how they are assembled.

## What “matches the release” means

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

Functional equivalence and byte identity are different:

- the same verified input, patch payloads and configuration reproduce the same
  application behavior;
- the same signing identity is also required for an install-over update;
- the exact archive ordering, timestamps and signer are required for a
  byte-identical APK.

Never copy another operator's signing key. Generate and protect your own.

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

## Understand the private patch set

The kit provides three inputs:

1. A source APK that you are authorized to modify.
2. A JSON build plan.
3. Replacement payloads referenced by that plan.

The plan uses this shape:

```json
{
  "schema": "akaine.client-build.v1",
  "source_sha256": "64_HEXADECIMAL_CHARACTERS",
  "required_entries": [
    "AndroidManifest.xml",
    "classes.dex",
    "lib/arm64-v8a/libcocos2dcpp.so"
  ],
  "replacements": [
    {
      "archive_path": "lib/arm64-v8a/libcocos2dcpp.so",
      "file": "payload/libcocos2dcpp.so",
      "sha256": "64_HEXADECIMAL_CHARACTERS"
    }
  ],
  "expected": {
    "label": "AkaineXD",
    "package": "akai.arc.lmao",
    "version_name": "7.0.255",
    "version_code": "1209852",
    "launchable_activity": "low.moe.AppActivity"
  }
}
```

Every replacement has an archive destination and a SHA-256. The builder stops
before producing output if the source APK, plan schema, required entries or any
payload does not match. It also rejects absolute and parent-relative payload
paths, so the plan cannot read arbitrary files from the computer.

The release patch set may replace several types of member:

- `AndroidManifest.xml` or `resources.arsc` for package, label and Android
  configuration changes;
- one or more `classes*.dex` files for Java/Smali integration;
- `lib/arm64-v8a/libcocos2dcpp.so` for native routing and gameplay guards;
- the AKFC loader and its crypto dependency.

Do not hand-copy only one of these pieces. For example, an AKFC chart can
download successfully and still fail at play time when the loader, crypto
library and DEX integration are not all from the same verified patch set.

## What the native release patch does

The 7.0 native patch is version-specific. It is guarded by the exact source
hash because offsets from another client version are unsafe.

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

These changes describe the release contract. The actual native payload stays
in the private kit because it is coupled to the verified APK input and must not
be applied to arbitrary versions.

## Step 1 — select the build inputs

```powershell
$sourceApk = Get-Item (Read-Host "Full path to the verified source APK")
$planFile = Get-Item (Read-Host "Full path to the client build plan")
$patchRoot = Get-Item (Read-Host "Full path to the plan's private payload folder")
$outputFolder = Read-Host "Full path for build output"
$outputFolder = [IO.Path]::GetFullPath($outputFolder)
New-Item -ItemType Directory -Force $outputFolder | Out-Null

$unsignedApk = Join-Path $outputFolder "AkaineXD-unsigned.apk"
$alignedApk = Join-Path $outputFolder "AkaineXD-aligned.apk"
$signedApk = Join-Path $outputFolder "AkaineXD-release.apk"
```

Check the source hash before doing anything else:

```powershell
Get-FileHash -Algorithm SHA256 $sourceApk.FullName
```

It must match `source_sha256` in the plan. Do not edit the plan to silence a
mismatch. Obtain the correct input APK.

## Step 2 — build the unsigned APK

```powershell
Set-Location $repoRoot
python scripts\build_android_client.py `
  --source $sourceApk.FullName `
  --plan $planFile.FullName `
  --kit-root $patchRoot.FullName `
  --output $unsignedApk
```

The command streams large ZIP members instead of loading the full APK into
memory. It preserves undeclared members, replaces only plan entries, removes
the old JAR/v1 signature and writes a receipt next to the unsigned APK.

Open the receipt and confirm the replacement list:

```powershell
Get-Content "$unsignedApk.receipt.json"
```

If an unexpected APK member appears in `replaced_entries`, stop and inspect the
private plan before signing.

## Step 3 — find Android Build-Tools

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

## Step 4 — align the APK

Native libraries require page alignment. The release pipeline uses 16 KiB page
alignment and 4-byte ZIP alignment:

```powershell
& $zipalign -P 16 -f -v 4 $unsignedApk $alignedApk
& $zipalign -c -P 16 -v 4 $alignedApk
```

The second command must finish with `Verification successful`.

## Step 5 — create your signing identity once

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

## Step 6 — sign and verify

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

## Step 7 — inspect package and version

```powershell
$plan = Get-Content $planFile.FullName -Raw | ConvertFrom-Json
$badging = & $aapt dump badging $signedApk
$badging | Select-String "package:|application-label:|launchable-activity:"
```

Compare the output with the `expected` object in the plan. For the current
reference contract it must show `akai.arc.lmao`, `AkaineXD`, version
`7.0.255`, version code `1209852` and `low.moe.AppActivity`.

Also record the artifact identity:

```powershell
Get-Item $signedApk | Select-Object Name, Length
Get-FileHash -Algorithm SHA256 $signedApk
```

## Step 8 — choose fresh install or install-over

Connect the Android device or emulator and run:

```powershell
adb devices
adb shell pm path $plan.expected.package
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

## Step 9 — launch with a clean log

```powershell
$package = $plan.expected.package
$activity = $plan.expected.launchable_activity

adb logcat -c
adb shell am force-stop $package
adb shell am start -n "$package/$activity"
Start-Sleep -Seconds 10
adb shell pidof $package
```

A PID proves that the process is still alive, not that the client is fully
working. Save the complete log before reproducing a problem:

```powershell
$logFile = Join-Path $outputFolder "client-logcat.txt"
adb logcat -d | Set-Content -Encoding utf8 $logFile

Select-String -Path $logFile -Pattern `
  "Fatal signal","FATAL EXCEPTION","JNI DETECTED ERROR", `
  "FileUtilsSaveError","LoadUnlocksMap","Cocos2dxDownloader", `
  "ClassNotFoundException","FMOD"
```

## Step 10 — test the release contract

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
- private plan SHA-256;
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

## What this chapter does not publish

GitHub intentionally does not contain:

- the source APK;
- modified native libraries or DEX payloads;
- the production signing key;
- commercial game assets;
- private chart encryption material;
- production domains, credentials or player data.

The build process is public. Inputs that the project cannot redistribute remain
private and are verified by hash before use.
