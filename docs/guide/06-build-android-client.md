# Build the Arcaea 7.0.255 Android client

Build an installable Akaine client from the verified Arcaea 7.0.255 XAPK. The
process mirrors the 7.0.255 release pipeline: verify the input, merge its
splits, patch the managed and native code, align and sign the APK, then install
it and collect logs.

Download the original application yourself; the commercial APK and signing
keys are not stored in this repository. GitHub contains the build process,
verification code and version-locked native and Smali patches.

## What "matches the release" means

The 7.0.255 reference client has this contract:

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
$xapkExpectedSize = 1219427332
$xapkExpectedHash = "459bb01f8357dde82b13a817d4dd5dbf81e7a70d0805cc0d5f1aebde36fa2b7a"
$xapkHash = (Get-FileHash -Algorithm SHA256 $xapk.FullName).Hash.ToLowerInvariant()

if ($xapk.Length -ne $xapkExpectedSize -or $xapkHash -ne $xapkExpectedHash) {
  throw "XAPK size or SHA-256 does not match the verified arm64 input."
}

$xapk | Select-Object Name, Length
$xapkHash
```

Both size and SHA-256 must match. A file for 7.0.256, an armeabi-v7a variant or
a repacked mirror is not an interchangeable input. Native offsets and expected
bytes are tied to this exact build.

`Get-Item` resolves the path and collects the real file size. The next two
variables hold the verified reference values. `Get-FileHash` reads the entire
download, so it can take a while for a 1.2 GB file. The `if` statement stops on
either mismatch. Reaching the final two output lines means the input gate
passed; it does not mean the XAPK has been modified.

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

$apkEditorExpectedSize = 7733037
$apkEditorExpectedHash = "a9cd40df818845456be6d696de6110c89edf4b0a0580cb83438ed6b25a366e67"
$apkEditorHash = (Get-FileHash -Algorithm SHA256 $apkEditor.FullName).Hash.ToLowerInvariant()
if ($apkEditor.Length -ne $apkEditorExpectedSize -or $apkEditorHash -ne $apkEditorExpectedHash) {
  throw "APKEditor size or SHA-256 does not match the verified tool."
}

java -Xmx4g -jar $apkEditor.FullName merge `
  -i $xapk.FullName `
  -o $baseline
if ($LASTEXITCODE -ne 0) {
  throw "XAPK merge failed."
}

$baselineExpectedSize = 1206740473
$baselineExpectedHash = "746dd90c2efac21fc88ffd032e5a71c78c0955766477382c7f48ece87e23026e"
$baselineInfo = Get-Item $baseline
$baselineHash = (Get-FileHash -Algorithm SHA256 $baseline).Hash.ToLowerInvariant()
if ($baselineInfo.Length -ne $baselineExpectedSize -or $baselineHash -ne $baselineExpectedHash) {
  throw "Merged baseline does not match the verified reference."
}
```

`-Xmx4g` lets the Java merge process use up to 4 GiB of memory. `merge` tells
APKEditor to combine split modules, `-i` selects the XAPK and `-o` selects the
new APK path. The command does not change `$xapk`. The final size/hash gate
proves that the expected five modules produced the same baseline used to derive
the later patches.

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
$sdk = [Environment]::GetEnvironmentVariable("ANDROID_SDK_ROOT", "User")
if (-not $sdk) {
  throw "ANDROID_SDK_ROOT is not set. Return to chapter 3."
}

$buildTools = Get-ChildItem (Join-Path $sdk "build-tools") -Directory |
  Sort-Object { [version]$_.Name } -Descending |
  Select-Object -First 1

if (-not $buildTools) {
  throw "No Android Build-Tools installation was found."
}
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
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

Set-Location $repoRoot
Get-Item $python
& $python scripts\doctor.py --android
```

Do not continue unless the strict tool check passes.

The first three lines reload the locations saved in chapters 3 and 4. The
fourth selects the repository's virtual-environment Python, which already has
the required `cryptography` package; using an unrelated system Python can make
key generation fail later. `Set-Location` makes every relative repository path
in the chapter resolve from the same place. `Get-Item` proves the virtual
environment exists before `doctor.py` checks Java, adb, Apktool, zipalign and
apksigner. The last line must end with `Requested toolchain is ready.`

## Understand the public patch set

An APK is a ZIP archive containing several kinds of program data. This build
changes three layers:

| Layer | Files in this build | What the layer controls |
| --- | --- | --- |
| Android wrapper | `AndroidManifest.xml`, resources and `classes.dex` | Package name, app label, Android components and the Java/Smali bridge that starts AKFC |
| Game code | `libcocos2dcpp.so` | Server routes and the native conditions used by Divine, BYD, Dread Area and Aether Crest |
| Audio file bridge | `libfmodProvider.so` | The result returned to FMOD after a file read |

The content bundle is separate from these layers. It supplies catalogues,
layouts, jackets and previews after the client connects. An APK patch can make
a selector accept a song, but it cannot create a missing jacket or audio file.

The transformation is assembled from source in this repository:

- `patch_android_client_sources.py` changes the decoded manifest, label,
  package references and AKFC lifecycle calls;
- `AkfcLoader.smali` is the managed JNI bridge;
- `akfc_loader.cpp` implements protected-chart loading;
- the key scripts generate a different RSA-3072 identity for each operator;
- `build_boringssl_android.py` creates a symbol-prefixed static crypto archive
  that is linked only into the AKFC loader;
- `native-plan.json` applies guarded before/after byte operations to the two
  original native libraries.

No patched `.dex` or `.so` is downloaded from Akaine. The only non-source input
is the verified upstream XAPK.

Three terms appear throughout this chapter. Managed code is the Android and
Java side compiled into `classes.dex`; Apktool represents it as readable Smali
assembly. Native code is arm64 machine code stored in `.so` libraries. A hook
redirects one known function or call site to replacement logic. It does not
mean a remote server hook or a modification to every function in the game.

### How a guarded binary patch works

`native-plan.json` is a list of small byte replacements. Each operation has
four useful fields:

- `offset` is the byte position inside the native library;
- `before` is the exact byte sequence expected in the untouched 7.0.255 file;
- `after` is the same-length replacement;
- `label` gives the replacement a readable name for the build receipt.

The builder first checks the SHA-256 of the original library. It then checks
the `before` bytes at every offset, applies the replacements and checks the
final SHA-256. If any check fails, the build stops without producing a patched
APK. This prevents an offset intended for 7.0.255 from being written into a
different release where the same position could contain unrelated code.

The hexadecimal text is machine input, not a step that you should edit by
hand. Change a native operation only after analysing the target library and
updating its source hash, guarded bytes and output hash together.

## What the native release patch does

The 7.0.255 native patch is version-specific. Every operation checks the original
bytes before writing because offsets from another client version are unsafe.

The labels in the plan are grouped below by the player-facing problem they
solve.

The login route returns the access token. The aggregate route combines several
startup API calls into one request. The content-bundle route tells the client
which downloadable resource update it needs. Other calls, including Cloud
Sync, are built from the shared API base.

| Plan labels | What changes | What happens when it is missing |
| --- | --- | --- |
| `production-routes`, `route-helper`, `route-hook-a`, `route-hook-b`, `route-hook-c`, `route-hook-d` | Store the production login, aggregate and content-bundle URLs, then redirect the native call sites that construct those requests through the route helper. The helper matters because adding unused URL text alone would not change a request. | Login or bundle requests still go to an official, staging or obsolete endpoint. |
| `production-shared-api-base` | Replaces the encrypted base URL used by direct API requests such as `/user/me/save`. This route is separate from the visible login and aggregate URL strings. | Login may appear to succeed, but opening Network or Cloud Sync returns error `-4`, the client says another device logged in, and the saved session is unusable after restart. |
| `byd-allowlist`, `byd-registry-hook` | Adds the exact class-3 song IDs accepted by the native active-state registry and sends the registry check through that allowlist. It covers `pentiment`, `arcanaeden`, `worldender`, `testify`, `infinitestrife`, `last`, `lasteternity` and `axiumcrisis`. | The BYD tile can be absent or visible but not selectable even when the chart and server entitlement exist. The allowlist affects only the named songs. |
| `divine-gate`, `divine-cell-a`, `divine-cell-b` | Enables the known Divine reveal path and its selector cells. | The songs can exist in the bundle while their selector presentation remains black or incomplete. Jackets and previews must still exist in the bundle. |
| `aether-guard-cave`, `aether-guard-hook` | Adds a null check before the client enumerates Aether Crest's special-condition list. The ordinary non-null path continues unchanged. | Opening or starting Aether Crest ETR can dereference a missing list and crash. |
| `dread-area` | Repairs the known Dread Area pre-start condition path. | The song reaches selection but can fail immediately before gameplay begins. |
| `crash-logger` | Keeps the native crash-logger branch used by the accepted release disabled. It does not unlock content or hide Java errors from logcat. | The client follows a different native crash-reporting path from the verified release. |
| `fmod-18-read-contract` | Changes `libfmodProvider.so` so its file-read result matches the contract expected by FMOD. | Music playback can return FMOD error 18 or crash when a song starts even though the audio file exists. |

The route operations deserve special attention. Arcaea does not build every
request from one plain-text hostname. Login, aggregate and bundle have visible
route strings, while other endpoints use an encrypted shared base. Both layers
must point to the same server. This is why a client can log in successfully and
still fail Cloud Sync if `production-shared-api-base` is omitted.

The guarded byte operations listed above are published in
`patches/arcaea-7.0.255-arm64/native-plan.json`. They are generated from the
verified APKPure baseline and can be reproduced without a pre-patched native
library. See the README beside that plan for the exact command and receipt
checks.

The package rename and managed AKFC bridge are also public in
`scripts/patch_android_client_sources.py` and the `smali` folder beside the
native plan. The next section explains those edits before applying them.

The AKFC loader C++ source and its build commands are also included. Each
operator generates a different 3072-bit RSA key pair locally; the private key
is embedded only into that operator's loader and the public key is used to
encrypt charts.

## How to follow the build steps

Use one PowerShell window for steps 1 through 14. Variables such as
`$outputFolder` and `$signedApk` live only in that window. Closing it does not
delete any files, but you must run the variable-setting blocks again before
continuing.

Paste one code block at a time. Wait for the prompt to return before pasting
the next block. If a command prints a red error or `$LASTEXITCODE` is not zero,
stop at that step. Running later commands usually hides the first useful error
under several secondary failures.

PowerShell syntax used in this chapter:

| Text | Meaning |
| --- | --- |
| `$name = value` | Save a value under a temporary variable name. It does not create a file unless the command on the right does so. |
| `Read-Host "Question"` | Pause and wait for you to type a value. Type the path only; do not include the `>` prompt or add quotation marks. |
| `` ` `` at the end of a line | Continue the same command on the next line. Nothing may follow the backtick, including a space. |
| `& $tool` | Run the executable whose full path is stored in `$tool`. |
| `|` | Send the output on the left into the command on the right. |
| `Join-Path $folder "name"` | Build a path without assuming a drive letter or slash style. |
| `$LASTEXITCODE` | Exit code from the last native program. Zero means success. |

The build moves through these artifacts:

| Artifact | Created by | Purpose | Keep after release? |
| --- | --- | --- | --- |
| Arm64 XAPK | Download | Verified upstream input containing five split APK modules. | Keep its hash and an authorized local copy. |
| Merged baseline APK | APKEditor | One APK containing the base, arm64 libraries and asset split. | Keep until the release is accepted. |
| `decoded` folder | Apktool decode | Readable manifest, resources and Smali plus extracted native libraries. | Rebuildable; safe to remove after release. |
| Managed unsigned APK | Apktool build | Package rename, label and AKFC Java/Smali bridge compiled back into an APK. | Rebuildable intermediate. |
| Unsigned patched APK | Akaine builder | Managed APK plus guarded native route, gameplay and FMOD changes. | Keep its receipt; APK itself is rebuildable. |
| Aligned APK | `zipalign` | Unsigned archive with Android-compatible ZIP and native-library alignment. | Rebuildable intermediate. |
| Signed release APK | `apksigner` | Installable artifact tied to your signing identity. | Keep, hash and back up. |

Do not edit an intermediate APK with a ZIP program between steps. Any change
after alignment invalidates alignment, and any change after signing invalidates
the signature.

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

Line by line:

1. `Read-Host` asks where this build may write several gigabytes of temporary
   data. A new empty folder is easiest to diagnose.
2. `GetFullPath` converts relative input such as `build` into one unambiguous
   absolute path.
3. `New-Item` creates the folder. `-Force` means an existing folder is accepted;
   it does not delete its contents.
4. The five `Join-Path` lines name later outputs. They do not build those files
   yet.

At this point only `$outputFolder` must exist. If it contains files from a
failed build, choose a new folder so an old intermediate cannot be mistaken for
the current result.

## Step 2: decode the merged baseline

```powershell
$apktool = Get-Item (Read-Host "Full path to apktool_2.12.1.jar")
Get-FileHash -Algorithm SHA256 $apktool.FullName

java -Xmx6g -jar $apktool.FullName decode -f `
  $baseline `
  -o $decoded
```

What each part does:

| Part | Meaning |
| --- | --- |
| `$apktool = Get-Item ...` | Ask for the jar path and fail immediately if that file does not exist. |
| `Get-FileHash` | Calculate the jar identity before executing downloaded code. |
| `java` | Start the Java runtime installed in chapter 3. |
| `-Xmx6g` | Allow Apktool to use up to 6 GiB of memory. It is a limit, not an immediate 6 GiB allocation. |
| `-jar $apktool.FullName` | Run the verified Apktool jar. |
| `decode` | Convert the binary Android resources and DEX representation into an editable directory. |
| `-f` | Replace an existing decode result at the selected output path. This is why the build folder should contain no work you need to keep. |
| `$baseline` | Input: the merged and hash-verified APK, not the original XAPK or a split APK. |
| `-o $decoded` | Output: the decoded directory named in step 1. |

Confirm that decode completed and produced the four inputs used by the managed
patcher:

```powershell
if ($LASTEXITCODE -ne 0) {
  throw "Apktool decode failed. Do not continue to patching."
}

$requiredDecoded = @(
  (Join-Path $decoded "AndroidManifest.xml")
  (Join-Path $decoded "res\values\strings.xml")
  (Join-Path $decoded "smali\low\moe\AppActivity.smali")
  (Join-Path $decoded "lib\arm64-v8a\libcocos2dcpp.so")
)

Get-Item $requiredDecoded | Select-Object FullName, Length
```

All four rows must print with a non-zero length. A missing arm64 library usually
means the XAPK was not merged correctly or the wrong architecture was chosen.

The Apktool jar must be 25,926,183 bytes with SHA-256
`66cf4524a4a45a7f56567d08b2c9b6ec237bcdd78cee69fd4a59c8a0243aeafa`.

## Step 3: patch the managed sources

This script edits readable files produced by Apktool. Its changes are small,
but they must agree with each other:

| File | Change | Reason |
| --- | --- | --- |
| `AndroidManifest.xml` | Rename `moe.low.arc` to `akai.arc.lmao`, including seven component authorities and the login callback host/scheme. | Android treats the package as the app's identity. Provider authorities and callback declarations must follow the new identity or sharing and login callbacks can target the wrong app. The new package can also be installed separately from the official client. |
| `res/values/strings.xml` | Change the launcher label from Arcaea to AkaineXD. | This is the name Android displays. It does not change networking or gameplay. |
| `BuildConfig.smali` | Set `APPLICATION_ID` to `akai.arc.lmao`. | Code that reads its build identity must agree with the manifest package. |
| `AppActivity.smali` | Update the share provider authority, call `AkfcLoader.init()` after native libraries load and call `wipeDecrypted()` during activity destruction. | The loader cannot hook `libcocos2dcpp.so` before that library exists, and decrypted chart data must be removed when the activity ends. |
| `AkfcLoader.smali` | Add the Java-to-native bridge for the two loader functions. | Java cannot call the C++ loader exports without a JNI bridge. |

Every replacement includes an expected match count. A count of zero usually
means the input is the wrong version. A larger count means the script cannot
prove which occurrence is safe. Either case stops the build.

```powershell
Set-Location $repoRoot
& $python scripts\patch_android_client_sources.py `
  --decoded $decoded `
  --receipt (Join-Path $outputFolder "managed-patch-receipt.json")
```

This changes only exact version-locked source strings and adds the public Smali
bridge. Any missing or duplicate match stops the build.

The first line returns to the repository so the relative `scripts\...` path
resolves correctly. `--decoded` selects the directory to edit. `--receipt`
records every changed file and its before/after hash; it is evidence, not an
APK.

Check the result before compiling it:

```powershell
$managedReceiptPath = Join-Path $outputFolder "managed-patch-receipt.json"
$managedReceipt = Get-Content $managedReceiptPath -Raw | ConvertFrom-Json

if ($LASTEXITCODE -ne 0 -or $managedReceipt.status -ne "patched") {
  throw "Managed patch did not complete."
}

$managedReceipt.changes |
  Select-Object path, before_sha256, after_sha256 |
  Format-Table -AutoSize
```

The table must include `AndroidManifest.xml`, `strings.xml`,
`BuildConfig.smali`, `AppActivity.smali` and the newly added
`AkfcLoader.smali`. A blank or missing receipt means this step did not finish.
Do not manually create a receipt to bypass the check.

## Step 4: generate this server's AKFC key

AKFC protects a chart in two layers. The chart is encrypted with a random AES
key, then that AES key is wrapped with the operator's RSA public key. The APK
contains the matching private key in obfuscated generated C data so it can
unwrap the AES key during play. A client built with a different private key
cannot read those protected charts.

Generate one key pair for the server/client pair and keep it for later builds.
Rotating it requires re-encrypting the protected charts that use the old public
key.

The private key is part of the installed APK, so a determined person can
eventually recover it. AKFC raises the effort needed to copy distributed chart
files; it is not hardware-backed DRM and should not be treated as permanent
secrecy.

```powershell
$keyFolder = Read-Host "Private folder for this server's AKFC keys"
$keyFolder = [IO.Path]::GetFullPath($keyFolder)
$privateKey = Join-Path $keyFolder "akfc-private.pem"
$publicKey = Join-Path $keyFolder "akfc-public.pem"
$keyHeader = Join-Path $keyFolder "embedded_key.h"

if (-not (Test-Path $privateKey) -and -not (Test-Path $publicKey)) {
  & $python scripts\generate_akfc_keypair.py `
    --private-key $privateKey `
    --public-key $publicKey
} elseif (-not (Test-Path $privateKey) -or -not (Test-Path $publicKey)) {
  throw "Only one AKFC key exists. Restore the matching pair from backup."
}

& $python scripts\generate_akfc_key_header.py `
  --private-key $privateKey `
  --output $keyHeader

Get-Item $privateKey, $publicKey, $keyHeader |
  Select-Object Name, Length
```

Keep the private key and generated header outside Git. The server uses the
public key when encrypting AFF containers.

The first three `Join-Path` lines name the key pair and generated C header. The
`if` branch generates a pair only when neither key exists. The `elseif` branch
stops if only half of the pair exists; generating a replacement half would
create keys that cannot work together. On later builds, both existing keys are
reused and only `embedded_key.h` is regenerated.

`--private-key` is the RSA key embedded into the loader. `--public-key` is the
matching encryption key used by the chart-packaging side. `--output` writes C
data consumed by the native compiler. The final command prints file names and
sizes without displaying the private key contents.

## Step 5: build the AKFC loader

Install **NDK (Side by side)** from Android Studio's SDK Tools, then select the
NDK folder:

```powershell
$env:ANDROID_NDK_ROOT = Read-Host "Full path to the installed Android NDK"
$loader = Join-Path $outputFolder "libakfcloader.so"
$nativeFolder = Join-Path $decoded "lib\arm64-v8a"
$cryptoWork = Join-Path $outputFolder "boringssl-work"
$crypto = Join-Path $outputFolder "libakfc-crypto.a"

& $python scripts\build_boringssl_android.py `
  --work $cryptoWork `
  --output $crypto
if ($LASTEXITCODE -ne 0) {
  throw "BoringSSL build failed."
}

& $python scripts\build_akfc_loader.py `
  --source patches\arcaea-7.0.255-arm64\native\akfc_loader.cpp `
  --key-header $keyHeader `
  --crypto $crypto `
  --output $loader
if ($LASTEXITCODE -ne 0) {
  throw "AKFC loader build failed."
}

Copy-Item $loader (Join-Path $nativeFolder "libakfcloader.so")
Get-Item $crypto, $loader, (Join-Path $nativeFolder "libakfcloader.so") |
  Select-Object FullName, Length
```

Line by line:

1. `ANDROID_NDK_ROOT` tells both Python build scripts which NDK toolchain to
   use. `$env:` makes it available to child processes in this PowerShell
   window; it does not permanently change Windows.
2. `$loader` is the compiled arm64 shared library. `$nativeFolder` is the exact
   directory Apktool will package as `lib/arm64-v8a/`.
3. `$cryptoWork` holds the pinned BoringSSL checkout and CMake output. The first
   build downloads and compiles it, so it can take several minutes. Later
   builds reuse that checkout after checking its revision.
4. `$crypto` is the static archive after every exported symbol receives the
   `akfc_` prefix.
5. `build_akfc_loader.py` compiles `akfc_loader.cpp`, includes the generated key
   header and links the prefixed crypto archive.
6. `Copy-Item` places the finished loader into the decoded APK tree. Building
   the loader without this copy would leave it outside the APK.

The final table must show three non-empty files. The two loader rows should
have the same length because one is the build output and the other is its copy
inside the decoded tree. A missing `cmake`, `ninja`, compiler or `llvm-objcopy`
is an NDK/SDK installation problem; return to Android Studio SDK Tools instead
of editing the script.

The BoringSSL symbols receive an `akfc_` prefix before they are linked into the
loader. The build does not add or replace a process-wide `libcrypto.so`, so the
AKFC runtime cannot alter unrelated client encryption or saved login state.

At runtime the loader does this only for files that look like chart downloads
and begin with the `AKFC` magic bytes:

1. intercept the native file-open or file-size request;
2. wait briefly if a `.tmp` download has not reached its declared size;
3. authenticate the container identity and unwrap its AES key;
4. decrypt the AFF into the app's private storage and report the plaintext size
   expected by the chart reader;
5. wipe tracked plaintext files when the Android activity is destroyed.

Ordinary assets pass through the original file functions. The magic-byte check
is important: an `.aff` filename alone is not enough to trigger decryption.

## Step 6: rebuild and apply guarded native patches

Apktool compiles the managed edits back into `classes.dex`, the binary manifest
and Android resources. `build_android_client.py` then opens that rebuilt APK
and changes only the guarded native members. Rebuilding first matters because
the final archive must contain both the Android/JNI bridge and the native code
that the bridge calls.

```powershell
java -Xmx6g -jar $apktool.FullName build `
  $decoded `
  -o $managedApk
if ($LASTEXITCODE -ne 0) {
  throw "Apktool rebuild failed."
}

& $python scripts\build_android_client.py `
  --source $managedApk `
  --plan patches\arcaea-7.0.255-arm64\native-plan.json `
  --kit-root $repoRoot `
  --output $unsignedApk
if ($LASTEXITCODE -ne 0) {
  throw "Guarded native patch failed."
}

$nativeReceiptPath = "$unsignedApk.receipt.json"
$nativeReceipt = Get-Content $nativeReceiptPath -Raw | ConvertFrom-Json
$nativeLabels = @()
foreach ($property in $nativeReceipt.binary_patch_labels.PSObject.Properties) {
  $nativeLabels += @($property.Value)
}

if ($nativeReceipt.status -ne "unsigned-built") {
  throw "Native build receipt is not complete."
}
if ($nativeLabels.Count -ne 17 -or $nativeLabels -notcontains "production-shared-api-base") {
  throw "Native patch receipt does not contain the full release plan."
}

Get-Item $managedApk, $unsignedApk | Select-Object Name, Length
$nativeLabels | Sort-Object
```

The receipt must list all 17 native labels, including
`production-shared-api-base`. The plan guards the exact original
`libcocos2dcpp.so` and `libfmodProvider.so` hashes even though Apktool changes
the surrounding ZIP container.

The Apktool `build` command turns the entire decoded tree back into an APK. The
next command has four inputs:

| Argument | Meaning |
| --- | --- |
| `--source $managedApk` | APK containing the managed edits and newly compiled AKFC loader. |
| `--plan ...native-plan.json` | Version-locked list of guarded native operations. |
| `--kit-root $repoRoot` | Root used to resolve public source payloads named by the plan. It is not the private resource kit in this command. |
| `--output $unsignedApk` | New APK receiving the native changes. It is still unsigned. |

The builder verifies the source members before changing them, removes obsolete
v1 signature entries, writes through a temporary file and produces the receipt
beside the APK. The validation block counts all 17 operation labels and checks
the easy-to-miss shared API base patch. If this block fails, do not sign the
APK even if `$unsignedApk` happens to exist.

## Step 7: find Android Build-Tools

Use the newest installed Build-Tools folder instead of assuming a version or
drive:

```powershell
$buildTools = Get-ChildItem (Join-Path $sdk "build-tools") -Directory |
  Sort-Object { [version]$_.Name } -Descending |
  Select-Object -First 1

if (-not $buildTools) {
  throw "No Android Build-Tools installation was found."
}

$zipalign = Join-Path $buildTools.FullName "zipalign.exe"
$apksigner = Join-Path $buildTools.FullName "apksigner.bat"
$aapt = Join-Path $buildTools.FullName "aapt.exe"

Get-Item $zipalign, $apksigner, $aapt
```

All three files must exist.

`Get-ChildItem` lists installed Build-Tools versions. The pipeline passes each
folder name through `[version]` so `35.0.0` sorts numerically above `9.0.0`.
`Select-Object -First 1` keeps the newest installation. The three `Join-Path`
lines then name the exact executables used below; `Get-Item` is the final
existence check.

## Step 8: align the APK

Native libraries require page alignment. The release pipeline uses 16 KiB page
alignment and 4-byte ZIP alignment:

```powershell
& $zipalign -P 16 -f -v 4 $unsignedApk $alignedApk
if ($LASTEXITCODE -ne 0) {
  throw "APK alignment failed."
}
& $zipalign -c -P 16 -v 4 $alignedApk
if ($LASTEXITCODE -ne 0) {
  throw "Aligned APK verification failed."
}
```

The second command must finish with `Verification successful`.

`-P 16` aligns uncompressed native libraries for 16 KiB memory pages. `-f`
allows replacement of an old aligned output at the chosen path. `-v` prints
the work, and `4` applies ordinary four-byte ZIP alignment. The second command
uses `-c` to check rather than write. It is a separate gate: the existence of
`$alignedApk` alone does not prove alignment succeeded.

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
  if ($LASTEXITCODE -ne 0) {
    throw "Android signing-key generation failed."
  }
}

Get-Item $keystore | Select-Object FullName, Length, LastWriteTime
```

`keytool` asks for passwords and certificate identity interactively. Store the
passwords in a password manager. Never put the keystore or passwords in Git,
the resource kit, a screenshot or a shell script.

Back up this keystore securely. Losing it means future APKs cannot update the
installed application without uninstalling and deleting its local data.

`-keystore` chooses the private key container and `-alias` names one key inside
it. `-keyalg RSA -keysize 4096` creates the signing key; it is unrelated to the
separate RSA-3072 AKFC chart key. `-validity 10000` keeps the signing certificate
valid for 10,000 days. For the identity questions, a personal test deployment
may use descriptive values; none of those answers changes the package name.

The `if` guard is deliberate. If the keystore already exists, the command does
not generate a new signer. Confirm that the displayed path is outside the Git
repository before continuing.

## Step 10: sign and verify

```powershell
& $apksigner sign `
  --ks $keystore `
  --ks-key-alias $keyAlias `
  --v4-signing-enabled false `
  --out $signedApk `
  $alignedApk
if ($LASTEXITCODE -ne 0) {
  throw "APK signing failed."
}

& $apksigner verify --verbose --print-certs $signedApk
if ($LASTEXITCODE -ne 0) {
  throw "APK signature verification failed."
}
```

The verification must report v2 and v3 signatures as verified. Record the
signer certificate SHA-256; every later build for the same package must report
the same value.

`sign` reads the aligned APK and writes a different file at `--out`; it does
not modify the aligned input. `--ks` and `--ks-key-alias` select the identity
created in step 9. V4 signing is disabled because the guide distributes one
APK rather than an APK plus a separate `.idsig` file. The verification command
reads the finished APK, checks its signing schemes and prints the certificate
digest needed for future install-over comparisons.

## Step 11: inspect package and version

```powershell
$badging = & $aapt dump badging $signedApk
$badging | Select-String "package:|application-label:|launchable-activity:"
```

For the 7.0.255 contract it must show `akai.arc.lmao`, `AkaineXD`, version
`7.0.255`, version code `1209852` and `low.moe.AppActivity`.

`aapt dump badging` reads metadata from the APK without installing it. The first
line contains package, version code and version name. The label line controls
the launcher name. The launchable-activity line tells Android which activity
opens from the icon. If any value differs, return to the managed patch or input
selection step; changing the filename cannot correct APK metadata.

Also record the artifact identity:

```powershell
Get-Item $signedApk | Select-Object Name, Length
Get-FileHash -Algorithm SHA256 $signedApk
```

## Step 12: choose fresh install or install-over

Connect the Android device or emulator and run:

```powershell
adb devices
$serial = Read-Host "Device serial shown in the first column above"
$package = "akai.arc.lmao"
adb -s $serial shell pm path $package
```

`adb devices` must show the intended device with state `device`. `unauthorized`
means unlock the screen and accept the USB-debugging prompt. `offline` means
reconnect or restart that emulator. `$serial` makes every later command target
the device you selected instead of whichever device adb chooses first.

`pm path` is read-only. A line beginning with `package:` means AkaineXD is
already installed. `package ... was not found` means it is a fresh install.

If the package is not installed, perform a fresh install:

```powershell
adb -s $serial install $signedApk
if ($LASTEXITCODE -ne 0) {
  throw "Fresh APK installation failed."
}
```

Use install-over only when the installed package has the same signing
certificate:

```powershell
adb -s $serial install -r -d $signedApk
if ($LASTEXITCODE -ne 0) {
  throw "Install-over failed."
}
```

For install-over, `-r` keeps application data and replaces the APK. `-d`
allows reinstalling the same or a lower version code during controlled tests;
it does not bypass signature checks. A successful command ends with `Success`.

`INSTALL_FAILED_UPDATE_INCOMPATIBLE` means the signer differs. Do not uninstall
automatically: uninstalling deletes local application data. Either sign with
the original key or make an explicit backup-and-fresh-install decision.

## Step 13: launch with a clean log

```powershell
$package = "akai.arc.lmao"
$activity = "low.moe.AppActivity"

adb -s $serial logcat -c
adb -s $serial shell am force-stop $package
adb -s $serial shell am start -n "$package/$activity"
Start-Sleep -Seconds 10
adb -s $serial shell pidof $package
```

The first line clears old device logs so crashes from another build do not
pollute this test. `force-stop` gives the app a cold process start. `am start`
launches the exact package/activity pair. The ten-second wait gives native
libraries and the start screen time to load. `pidof` should print a number; an
empty result means the process exited and the log must be collected immediately.

A PID only shows that the process is alive. Save the complete log before
reproducing a problem:

```powershell
$logFile = Join-Path $outputFolder "client-logcat.txt"
adb -s $serial logcat -d | Set-Content -Encoding utf8 $logFile

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

Run one numbered action at a time. Write down `PASS` or `FAIL`, the local time
and what was visible on screen. If the app closes, freezes or returns to the
title screen unexpectedly, stop interacting and save logcat before reopening
it. Reopening first can move the useful crash lines out of the log buffer.

Use these acceptance rules:

| Check | Pass | Fail and stop condition |
| --- | --- | --- |
| Bundle | Download and checking reach 100%, title/menu opens, restart does not download it again. | `-1013`, repeated download, crash before title or loading loop. |
| Login/session | Account remains signed in after a complete app restart. | Login succeeds once but the next launch returns to guest state. |
| Cloud Sync | Download completes, returns normally and the session still works after restart. | Error `-4`, “another device” message, logout or sync failure. |
| Official audio/chart | Preview plays and the chart starts without FMOD errors. | Silent preview, FMOD 18, process exit or return before gameplay. |
| Divine/BYD/ETR | Jacket and difficulty tile render, tile is selectable and gameplay begins. | Black selector, missing tile, unclickable tile or crash after selection. |
| Protected fan chart | Download icon clears, chart starts, then starts again after restart. | Permanent icon, download error, AKFC/JNI error or first-start-only success. |

Passing a later row never cancels an earlier failure. Keep the APK as a
candidate until every required row passes on the same signed build.

## Diagnose failures by stage

| Symptom | Likely layer | First check |
| --- | --- | --- |
| APK will not install | signing/alignment | `apksigner verify`, `zipalign -c`, signer mismatch |
| Crash before title after bundle reaches 100% | bundle catalogue integrity | every song set and child pack references an existing pack |
| Login or content bundle uses the wrong server | native route patch | plan input hash, production/staging route selection, URL byte budget |
| Music Play opens but one group is black | bundle selector assets | jacket and preview entries, not a global unlock flag |
| BYD tile is absent or cannot be selected | native registry gate | exact song ID and difficulty class in the verified allowlist |
| Aether Crest ETR crashes | native special-condition list | null guard is present in the selected patch plan |
| Protected chart downloads but will not start | AKFC runtime | loader, prefixed static crypto and DEX integration match the 7.0.255 patch set |
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
