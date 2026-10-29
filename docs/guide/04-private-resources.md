# Get and verify the private resource kit

GitHub contains source code and this guide. Download the original client
from the APKPure link in chapter 6. The private resource kit supplies matching
content, its native catalogue and AKFC inputs. The NDK, Java and Android tools
remain installed at paths you choose; no prepatched Akaine APK is required.

![Chapter 04 private resource chain of trust](../images/guides/04-private-resources-chain-of-trust.svg)

## Obtain the kit

Obtain the private resource kit and its expected SHA-256 value from the project
owner through a private channel. Do not request or post private resources in a
public GitHub issue, Discussion, server channel or group chat.

Download the archive anywhere outside the Git repository.

The provider should send two separate items through a private channel: the
archive and its 64-character SHA-256 value. A filename, file size or screenshot
is not a substitute for the hash.

## Verify the downloaded archive

The provider will give you an expected SHA-256 value. Run:

```powershell
$kitArchive = Get-Item (Read-Host "Full path to the downloaded kit archive")
$expectedKitHash = (Read-Host "Expected 64-character SHA-256 from the provider").Trim().ToLowerInvariant()
$actualKitHash = (Get-FileHash -Algorithm SHA256 $kitArchive.FullName).Hash.ToLowerInvariant()

if ($expectedKitHash -notmatch '^[0-9a-f]{64}$') {
    throw "The expected SHA-256 is not 64 hexadecimal characters."
}
if ($actualKitHash -ne $expectedKitHash) {
    throw "The private resource archive does not match its expected SHA-256."
}

$kitArchive | Select-Object Name, Length, FullName
$actualKitHash
```

Compare the complete 64-character hash with the expected value. Letter case
does not matter; every character must otherwise match. If it differs, delete
the file and ask the provider for a verified replacement. Do not extract or
run it.

`Get-Item` stops if the selected archive does not exist. `Get-FileHash` reads
the complete archive and may take a while. The two `if` blocks make the hash a
stop gate instead of relying on visual comparison.

## Extract and verify the contents

After the archive hash matches, choose where to extract it:

```powershell
$kitRoot = Read-Host "Full path for the extracted kit"
$kitRoot = [IO.Path]::GetFullPath($kitRoot)

if (Test-Path $kitRoot) {
    if (Get-ChildItem -Force $kitRoot | Select-Object -First 1) {
        throw "The extraction folder is not empty. Choose a new folder."
    }
} else {
    New-Item -ItemType Directory -Force $kitRoot | Out-Null
}

Expand-Archive `
  -LiteralPath $kitArchive.FullName `
  -DestinationPath $kitRoot

[Environment]::SetEnvironmentVariable("AKAINE_KIT_ROOT", $kitRoot, "User")
Get-Item (Join-Path $kitRoot "README.txt")
```

The empty-folder rule prevents files left by an older kit from being mistaken
for current files. `Expand-Archive` extracts without modifying the downloaded
archive. The environment variable records the chosen folder for later
chapters. The final command must find `README.txt`.

The kit will include a manifest and a verification script. Run the command
printed in the kit's `README.txt`. The result must say that every declared file
exists and matches its expected size and SHA-256.

Open the instructions without executing anything first:

```powershell
Get-Content (Join-Path $kitRoot "README.txt")
```

Run only the verification command named there. Do not run an executable or
maintenance script merely because it is present in the archive.

Do not proceed if the verification reports a missing or mismatched file.

## Check the V36 client inputs

Before chapter 6, identify these verified files in the kit instructions:

- The native `songlist` JSON matching the content catalogue. Server metadata
  is a different file and cannot replace it.
- The private AKFC key header matching the protected charts. It remains
  outside the repository and is passed directly to the native compiler.
- The arm64 BoringSSL static archive with `akfc_`-prefixed symbols, or the
  instructions for building it with the public helper.
- The matching jadx all-in-one JAR and Android Build-Tools `d8.jar`, with their
  verification information. Java 17 and NDK `28.2.13676358` are selected in
  chapter 6.

The original APKPure XAPK and APKEditor are obtained separately in chapter 6;
that chapter includes their exact hashes. The kit does not need an Akaine APK,
a developer's local path map, copied SDK directory, patched final `.so`/`.dex`
payloads or another operator's Android keystore. Chapter 6 takes explicit
input paths and builds from the original client and public source.
Do not generate a new AKFC key when using an existing catalogue: that client
would not decode the already encrypted charts.

## Keep the kit private

- Do not commit it to Git or GitHub.
- Do not upload it to a public file host.
- Do not redistribute it unless you have permission from every relevant owner.
- Do not store production credentials or player databases in the same folder.
- Access to the kit does not grant permission to redistribute its contents.

## Check your work

- The archive hash matches the expected value from the provider.
- The extracted manifest verification passes.
- The kit is outside the Git repository.
- `AKAINE_KIT_ROOT` points to the extracted and verified kit.

The later client and content chapters will tell you which verified kit files to
use. Do not guess their purpose or run scripts that are not named by the guide.
