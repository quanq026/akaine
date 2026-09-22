# Get and verify the private resource kit

GitHub contains the source code and this guide. Game assets and content bundles
come from a separate resource kit. Chapter 6 downloads its upstream XAPK and
build tools directly from their published sources.

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

## Configure Apktool

Set the environment variable from the extracted kit location:

```powershell
$kitRoot = [Environment]::GetEnvironmentVariable("AKAINE_KIT_ROOT", "User")
$apktool = Join-Path $kitRoot "tools\apktool.jar"

Get-Item $apktool

[Environment]::SetEnvironmentVariable(
    "APKTOOL_JAR",
    $apktool,
    "User"
)
```

Close and reopen PowerShell, then run the strict Android check:

```powershell
$repoRoot = [Environment]::GetEnvironmentVariable("AKAINE_REPO_ROOT", "User")
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
Set-Location $repoRoot
Get-Item $python
& $python scripts\doctor.py --android
if ($LASTEXITCODE -ne 0) {
    throw "Strict Android toolchain check failed."
}
```

The command must finish with `Requested toolchain is ready.` If it reports a
missing tool, return to the matching installation step instead of continuing.

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
