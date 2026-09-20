# Get and verify the private resource kit

GitHub contains the source code and this guide. It does not contain the base
APK, game assets, content bundles or tested Apktool package needed by later
chapters.

## Request the kit

Direct-message Discord user `kuan.026`. Do not ask for the kit in a public
GitHub issue, Discussion, server channel or group chat. Accept the download
only from that exact Discord account.

The message you receive should identify a kit version and include a SHA-256
manifest. If it does not include both, ask for them before downloading.

## Create the destination folder

Open PowerShell:

```powershell
New-Item -ItemType Directory -Force C:\Akaine\resources | Out-Null
```

Download the archive into `C:\Akaine\resources`. Do not put it inside the Git
repository at `C:\Akaine\akaine`.

## Verify the downloaded archive

The owner will provide an expected SHA-256 value. Run this command, replacing
the filename:

```powershell
Get-FileHash -Algorithm SHA256 "C:\Akaine\resources\akaine-kit-VERSION.zip"
```

Compare the complete 64-character hash with the owner's message. Letter case
does not matter; every character must otherwise match. If it differs, delete
the file and contact `kuan.026`. Do not extract or run it.

## Extract and verify the contents

After the archive hash matches, extract it into a versioned folder:

```powershell
Expand-Archive `
  -LiteralPath "C:\Akaine\resources\akaine-kit-VERSION.zip" `
  -DestinationPath "C:\Akaine\resources\akaine-kit-VERSION"
```

The kit will include a manifest and a verification script. Run the command
printed in the kit's `README.txt`. The result must say that every declared file
exists and matches its expected size and SHA-256.

Do not proceed if the verification reports a missing or mismatched file.

## Configure Apktool

The verified kit places Apktool at:

```text
C:\Akaine\resources\akaine-kit-VERSION\tools\apktool.jar
```

Set the environment variable using the actual versioned folder name:

```powershell
[Environment]::SetEnvironmentVariable(
    "APKTOOL_JAR",
    "C:\Akaine\resources\akaine-kit-VERSION\tools\apktool.jar",
    "User"
)
```

Close and reopen PowerShell, then run the strict Android check:

```powershell
Set-Location C:\Akaine\akaine
python scripts\doctor.py --android
```

The command must finish with `Requested toolchain is ready.` If it reports a
missing tool, return to the matching installation step instead of continuing.

## Keep the kit private

- Do not commit it to Git or GitHub.
- Do not upload it to a public file host.
- Do not send it to another person; tell them to contact `kuan.026`.
- Do not store production credentials or player databases in the same folder.
- Access to the kit does not grant permission to redistribute its contents.

## How to know this chapter is complete

- The archive hash matches the value sent by `kuan.026`.
- The extracted manifest verification passes.
- The kit is outside the Git repository.
- `C:\Akaine\resources\akaine-kit-VERSION` contains the verified files.

The later client and content chapters will tell you which verified kit files to
use. Do not guess their purpose or run scripts that are not named by the guide.
