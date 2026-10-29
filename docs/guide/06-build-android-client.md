# Build the V36 Android client

English | [Tiếng Việt](vi/06-build-android-client.md)

This chapter builds Akaine V36 for Arcaea `7.0.255` (`1209852`) from the
verified production V9 APK dated 2026-10-22. An upstream XAPK, staging APK or
different repack is not an interchangeable input.

Public source contains the native runtime, Android changes and build tools.
The private resource kit supplies the matching APK, catalogue and AKFC inputs.
No developer disk identity, frozen source kit or local path map is required.

![Chapter 06 Android client assembly line](../images/guides/06-android-client-assembly.svg)

## What this build includes

V36 keeps package `akai.arc.lmao`, label `AkaineXD`, application version
`7.0.255` and version code `1209852`. It includes the semantic CLI,
first-run guide handling, character-skill fixes, anomaly replay controls,
the Mod category, dynamic packs, latest-ten news and guarded partial-cache
handling for bundle downloads.

The builder preserves the base APK's media. It does not resize jackets,
re-encode audio or create a content bundle. Content `7.0.255.25` is installed
separately through the configured server. ANGLE, Vulkan and unfinished
scene/loading experiments are not included.

The included client uses the published Akaine production hosts. It does not
replace them with your chapter-2 domain. Another API host needs a separately
verified native route change covering login, aggregate, content bundles and
the encrypted shared API base. A successful server check in chapter 5a does
not change client routes.

## Step 1: reopen the prepared workstation

Keep the same PowerShell window for all remaining steps:

```powershell
$repoRoot = [Environment]::GetEnvironmentVariable("AKAINE_REPO_ROOT", "User")
$kitRoot = [Environment]::GetEnvironmentVariable("AKAINE_KIT_ROOT", "User")
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
Set-Location $repoRoot
Get-Item $python, $kitRoot
& $python scripts\build_v36_client.py --help
if ($LASTEXITCODE -ne 0) { throw "V36 builder help failed." }
```

The paths were saved in chapters 3 and 4. The help command must list the
explicit inputs used below. Finish earlier setup if a folder or tool is
missing. These build commands do not deploy a server or publish content.

## Step 2: verify the base APK

Obtain the matching input through the private channel in
[chapter 4](04-private-resources.md), then verify the complete file:

```powershell
$baseApk = Get-Item (Read-Host "Full path to the production V9 APK")
$expectedBaseHash = "f14c5ab0871440dec7ecf2107d32d6e2cad745abc82047d03b49db9dbac3f545"
$baseHash = (Get-FileHash -Algorithm SHA256 $baseApk.FullName).Hash.ToLowerInvariant()
if ($baseHash -ne $expectedBaseHash) { throw "Wrong base APK. Stop here." }
$baseApk | Select-Object Name, Length
$baseHash
```

The hash must match exactly. This APK is an input, not the V36 output.
Do not change the expected hash to make another APK pass.

## Step 3: select the toolchain

Use Android NDK `28.2.13676358` for Windows and Java 17. Java's directory must
also contain `javac.exe` and `keytool.exe`. Select the matching jadx all-in-one
JAR and Android Build-Tools `d8.jar` specified by the verified kit instructions:

```powershell
$ndk = Get-Item (Read-Host "Full path to Android NDK 28.2.13676358")
$java = Get-Item (Read-Host "Full path to Java 17 java.exe")
$jadx = Get-Item (Read-Host "Full path to the matching jadx all-in-one JAR")
$d8 = Get-Item (Read-Host "Full path to Android Build-Tools d8.jar")
$javac = Join-Path $java.DirectoryName "javac.exe"
$llvm = Join-Path $ndk.FullName "toolchains\llvm\prebuilt\windows-x86_64\bin"
Get-Item $javac, (Join-Path $llvm "clang++.exe"), (Join-Path $llvm "llvm-objcopy.exe")
& $java.FullName -version
if ($LASTEXITCODE -ne 0) { throw "Java failed." }
```

The NDK folder contains `toolchains`; it is not the SDK root or the compiler
file. `d8.jar` normally sits inside the Build-Tools folder's `lib` directory.
Do not rename an unrelated JAR. Tools may remain at locations you choose.

## Step 4: select the catalogue and AKFC inputs

Use the native `songlist` JSON matching your content catalogue. It supplies
the CLI catalogue; the base APK does not contain it. A server metadata file
is not a substitute.

For existing Akaine charts, use the matching key header from the verified
private kit. **Do not generate a new AKFC key for existing charts.**
Select the arm64 static BoringSSL archive built with the `akfc_` symbol prefix:

```powershell
$songlist = Get-Item (Read-Host "Full path to the verified native songlist JSON")
$keyHeader = Get-Item (Read-Host "Full path to the matching private AKFC key header")
$crypto = Get-Item (Read-Host "Full path to the arm64 symbol-prefixed BoringSSL static archive")
Get-Item $songlist.FullName, $keyHeader.FullName, $crypto.FullName | Select-Object Name, Length
```

These commands show names and lengths, not key contents. Keep the header
outside Git. The builder passes it to the compiler without displaying it.
A process-wide `libcrypto.so` is not a replacement for the static archive.

### Only for a new server: generate its chart key

Skip this subsection for an existing catalogue. A new server may generate one
RSA-3072 pair, encrypt its charts with the public half and build the client
with the matching private header:

```powershell
$keyFolder = [IO.Path]::GetFullPath((Read-Host "Private folder for a new server's AKFC keys"))
$privateKey = Join-Path $keyFolder "akfc-private.pem"
$publicKey = Join-Path $keyFolder "akfc-public.pem"
$newKeyHeader = Join-Path $keyFolder "embedded_key.h"
if (-not (Test-Path $privateKey) -and -not (Test-Path $publicKey)) {
    & $python scripts\generate_akfc_keypair.py --private-key $privateKey --public-key $publicKey
    if ($LASTEXITCODE -ne 0) { throw "AKFC key generation failed." }
} elseif (-not (Test-Path $privateKey) -or -not (Test-Path $publicKey)) {
    throw "Only half of the AKFC pair exists. Restore its matching partner."
}
& $python scripts\generate_akfc_key_header.py --private-key $privateKey --output $newKeyHeader
if ($LASTEXITCODE -ne 0) { throw "AKFC header generation failed." }
$keyHeader = Get-Item $newKeyHeader
```

The guard reuses a complete existing pair and stops on a half-missing pair.
Changing the key of an existing catalogue requires re-encrypting affected
charts. AKFC key material is embedded in the APK; it is not permanent secrecy
against determined reverse engineering.

### If the static crypto archive was not supplied

Install CMake and Ninja through Android Studio SDK Tools, then build the
pinned, symbol-prefixed archive with the existing helper:

```powershell
$env:ANDROID_NDK_ROOT = $ndk.FullName
$cryptoWork = [IO.Path]::GetFullPath((Read-Host "Private working directory for the crypto build"))
$cryptoOutput = Join-Path $cryptoWork "libakfc-crypto.a"
& $python scripts\build_boringssl_android.py --work $cryptoWork --output $cryptoOutput
if ($LASTEXITCODE -ne 0) { throw "BoringSSL build failed." }
$crypto = Get-Item $cryptoOutput
```

This downloads and compiles BoringSSL. Stop on a failed build; a temporary
archive does not establish success. This step does not replace the chart key.

## Step 5: compile and assemble

Choose a new output directory outside the public repository, on any suitable
drive. Do not choose a folder containing your APK or private key inputs:

```powershell
$buildOutput = [IO.Path]::GetFullPath((Read-Host "New output directory for the V36 build"))
if (Test-Path $buildOutput) { throw "Choose a new output directory." }
$arguments = @(
    "--base-apk", $baseApk.FullName,
    "--songlist", $songlist.FullName,
    "--ndk", $ndk.FullName,
    "--java", $java.FullName,
    "--jadx", $jadx.FullName,
    "--d8", $d8.FullName,
    "--crypto", $crypto.FullName,
    "--key-header", $keyHeader.FullName,
    "--output", $buildOutput
)
& $python scripts\build_v36_client.py @arguments
if ($LASTEXITCODE -ne 0) { throw "V36 source build failed. Do not sign its output." }
$unsignedApk = Join-Path $buildOutput "unsigned.apk"
$buildReceipt = Join-Path $buildOutput "BUILD_RECEIPT.json"
Get-Item $unsignedApk, $buildReceipt | Select-Object Name, Length
Get-Content $buildReceipt -Raw | ConvertFrom-Json | Format-List
& $python -m zipfile -t $unsignedApk
if ($LASTEXITCODE -ne 0) { throw "Unsigned APK archive check failed." }
```

The builder verifies the base and catalogue, compiles V36 native and managed
payloads and the AKFC loader, and assembles `unsigned.apk`.
`BUILD_RECEIPT.json` records inputs and results. Inspect it before signing.
The ZIP check verifies archive integrity, not gameplay or server connectivity.

An unsigned APK is not ready to install. On failure keep the first error and
the build directory for inspection. Use a fresh directory for another attempt.

## Step 6: align the APK

Select the installed Android SDK Build-Tools and verify the required files:

```powershell
$sdk = [Environment]::GetEnvironmentVariable("ANDROID_SDK_ROOT", "User")
if (-not $sdk) { $sdk = [Environment]::GetEnvironmentVariable("ANDROID_HOME", "User") }
$buildTools = Get-ChildItem (Join-Path $sdk "build-tools") -Directory |
    Sort-Object { [version]$_.Name } -Descending |
    Select-Object -First 1
if (-not $buildTools) { throw "Install Android SDK Build-Tools first." }
$zipalign = Join-Path $buildTools.FullName "zipalign.exe"
$apksigner = Join-Path $buildTools.FullName "apksigner.bat"
$aapt = Join-Path $buildTools.FullName "aapt.exe"
Get-Item $zipalign, $apksigner, $aapt
$alignedApk = Join-Path $buildOutput "Akaine-v36-aligned.apk"
$signedApk = Join-Path $buildOutput "Akaine-v36.apk"
& $zipalign -P 16 -f -v 4 $unsignedApk $alignedApk
if ($LASTEXITCODE -ne 0) { throw "APK alignment failed." }
& $zipalign -c -P 16 -v 4 $alignedApk
if ($LASTEXITCODE -ne 0) { throw "APK alignment verification failed." }
```

Version sorting is numeric. `-P 16` applies native-library page alignment;
`4` applies ordinary ZIP alignment. The second command checks the result
separately. Stop if either invocation fails.

## Step 7: sign and verify

Reuse the keystore for an existing installation. Create one only when you
are establishing your own signing identity:

```powershell
$keystore = [IO.Path]::GetFullPath((Read-Host "Full path to your private Android keystore"))
$keyAlias = Read-Host "Signing-key alias"
$keytool = Join-Path $java.DirectoryName "keytool.exe"
Get-Item $keytool
if (-not (Test-Path $keystore)) {
    New-Item -ItemType Directory -Force (Split-Path -Parent $keystore) | Out-Null
    & $keytool -genkeypair -keystore $keystore -alias $keyAlias -keyalg RSA -keysize 4096 -validity 10000
    if ($LASTEXITCODE -ne 0) { throw "Signing-key generation failed." }
}
& $apksigner sign --ks $keystore --ks-key-alias $keyAlias --v4-signing-enabled false --out $signedApk $alignedApk
if ($LASTEXITCODE -ne 0) { throw "APK signing failed." }
& $apksigner verify --verbose --print-certs $signedApk
if ($LASTEXITCODE -ne 0) { throw "APK signature verification failed." }
& $aapt dump badging $signedApk | Select-String "package:|application-label:|launchable-activity:"
Get-FileHash -Algorithm SHA256 $signedApk
```

Passwords are requested interactively. Keep the keystore and passwords out
of Git, resource kits and shell arguments. The Android signing key is
independent of the AKFC chart key.

Verification must succeed and show APK Signature Scheme v2 as verified.
Record the signer certificate digest for later install-over comparisons.
Badging must show `akai.arc.lmao`, `AkaineXD`, `7.0.255`, `1209852`
and activity `low.moe.AppActivity`.

An APK signed by you differs from an APK signed by another operator.
Compare package and signer for your installation; your signed APK does not
need the published release's exact signed hash.

## Step 8: select the device and install

Connect the intended Android device or emulator and choose its exact serial:

```powershell
adb devices -l
$serial = Read-Host "Exact device serial shown above"
$package = "akai.arc.lmao"
adb -s $serial shell pm path $package
```

Continue only when the device is listed with state `device`.
`unauthorized` needs USB-debugging acceptance on the unlocked device;
`offline` needs its connection fixed first. A `package:` result means
Akaine is already installed.

For a fresh installation:

```powershell
adb -s $serial install $signedApk
if ($LASTEXITCODE -ne 0) { throw "Fresh installation failed." }
```

For an existing installation with the same signing certificate:

```powershell
adb -s $serial install -r $signedApk
if ($LASTEXITCODE -ne 0) { throw "Install-over failed. Check the signer before doing anything else." }
```

Do not uninstall automatically on `INSTALL_FAILED_UPDATE_INCOMPATIBLE`.
Uninstalling deletes local data. Use the correct signer or make an explicit
backup-and-fresh-install decision.

## Step 9: inspect the client through the CLI

Launch the exact activity and read semantic state:

```powershell
adb -s $serial shell am start -n "akai.arc.lmao/low.moe.AppActivity"
if ($LASTEXITCODE -ne 0) { throw "Android launch request failed." }
& $python scripts\akaine_cli\akaine.py --serial $serial status
if ($LASTEXITCODE -ne 0) { throw "Client bridge status failed. Inspect the app and logs." }
& $python scripts\akaine_cli\akaine.py --serial $serial ui list
if ($LASTEXITCODE -ne 0) { throw "Client UI state read failed." }
& $python scripts\akaine_cli\akaine.py --serial $serial --help
```

The CLI invokes the device's semantic bridge without screen coordinates or
image scanning. `status` and `ui list` inspect the current state. A launch
request alone does not establish that the app stayed alive. Inspect the app
and logs if the bridge is not ready.

Use `--help` for catalogue search, songs/difficulties, characters, filters,
settings, Cloud Sync and recognized first-run guide commands. Read a fresh
`ui list` before using an action token; it belongs to the current scene.
A hidden modal or Android permission prompt can block an action.
Never place credentials in shell arguments or public logs.

The [first-run CLI reference](06a-semantic-cli.md) explains recognized
guide steps, Note Speed confirmation and unknown-outcome handling in detail.

## Step 10: test the client and content together

Source, archive and signature checks do not replace runtime checks. Use an
isolated test account and matching catalogue on the target server before
distributing your APK:

1. Reach the title screen without a crash or bundle loop.
2. Download the configured standalone bundle and restart.
3. Sign in, use Cloud Sync Download, restart and confirm login persists.
4. Read scene/overlay state through the CLI and complete recognized guides.
5. Open packs/songs, search/filter and select a character.
6. Confirm Mod and Fan Charts placement match the catalogue.
7. Check a character's distinctive skill gauge in actual gameplay.
8. Check anomaly replay disabled and enabled, including required restarts.
9. Play an official chart and a native fan chart with matching AKFC files;
   check audio, jackets and saved results.
10. Restart and confirm downloaded content remains available.

Save logs when a check fails:

```powershell
$logFile = Join-Path $buildOutput "client-logcat.txt"
adb -s $serial logcat -d | Set-Content -Encoding utf8 $logFile
Select-String -Path $logFile -Pattern "Fatal signal","FATAL EXCEPTION","JNI DETECTED ERROR","ClassNotFoundException","FMOD"
```

Redact credentials, device identifiers and personal account data before
sharing logs. Emulator checks do not establish physical-device performance,
exhaustive chart compatibility or a general FPS improvement.

Next: [Build, verify and release a content bundle](07-build-release-content-bundle.md).
