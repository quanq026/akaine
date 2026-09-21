# Prepare your Windows computer

Install the tools below on Windows 10 or Windows 11. The final commands check
the installation before you continue.

## Time, storage and permissions

- Time: 30 to 60 minutes, mostly downloads.
- Free disk space: at least 30 GB; 60 GB is more comfortable when rebuilding
  APKs and keeping an emulator.
- Permissions: a Windows administrator account is needed for installers.

## Step 1: choose where to keep the files

Choose two folders on any drive with enough free space: one for the public Git
repository and one different folder for private resources. They must not be
nested inside each other.

Open PowerShell and paste the full paths when prompted:

```powershell
$repoRoot = Read-Host "Full path for the Akaine source folder"
$privateRoot = Read-Host "Full path for the private resource folder"

$repoRoot = [IO.Path]::GetFullPath($repoRoot)
$privateRoot = [IO.Path]::GetFullPath($privateRoot)

New-Item -ItemType Directory -Force $privateRoot | Out-Null
[Environment]::SetEnvironmentVariable("AKAINE_REPO_ROOT", $repoRoot, "User")
[Environment]::SetEnvironmentVariable("AKAINE_PRIVATE_ROOT", $privateRoot, "User")
```

These variables let later chapters use your chosen locations without assuming
a drive letter or folder name. Keeping the folders separate prevents an
accidental Git commit from including private files.

## Step 2: install Git, Python and Java

Windows includes `winget` on current Windows 10/11 installations. Run these
commands in PowerShell:

```powershell
winget install --exact --id Git.Git
winget install --exact --id Python.Python.3.12
winget install --exact --id EclipseAdoptium.Temurin.17.JDK
```

Close PowerShell completely and open it again so the new PATH entries load.

Check the installations:

```powershell
git --version
python --version
java -version
```

Each command must print a version instead of “not recognized”. Python should
start with `3.12`, and Java should report version `17`.

If `python` opens the Microsoft Store, open **Settings** → **Apps** →
**Advanced app settings** → **App execution aliases**, then disable the Store
aliases for `python.exe` and `python3.exe`. Reopen PowerShell and try again.

## Step 3: install Android Studio and SDK tools

1. Download and install Android Studio from the official Android developer
   website. Keep the standard installation options.
2. Start Android Studio.
3. On the welcome screen select **More Actions** → **SDK Manager**. If a project
   is open, use **Tools** → **SDK Manager**.
4. On **SDK Platforms**, install at least one stable Android platform.
5. On **SDK Tools**, enable:
   - Android SDK Build-Tools;
   - Android SDK Platform-Tools;
   - Android SDK Command-line Tools (latest);
   - Android Emulator, if you will not use a physical phone.
6. Select **Apply**, accept the licenses, and wait for installation.
7. Copy the **Android SDK Location** shown at the top.

Set the environment variables using that path. The following command asks for
it instead of assuming where Android Studio installed the SDK:

```powershell
$sdk = Read-Host "Android SDK Location shown by Android Studio"
$sdk = [IO.Path]::GetFullPath($sdk)
[Environment]::SetEnvironmentVariable("ANDROID_HOME", $sdk, "User")
[Environment]::SetEnvironmentVariable("ANDROID_SDK_ROOT", $sdk, "User")
[Environment]::SetEnvironmentVariable(
    "Path",
    [Environment]::GetEnvironmentVariable("Path", "User") + ";$sdk\platform-tools;$sdk\emulator",
    "User"
)
```

Close and reopen PowerShell, then run:

```powershell
adb version
```

## Step 4: clone the Akaine source

```powershell
$repoRoot = [Environment]::GetEnvironmentVariable("AKAINE_REPO_ROOT", "User")
git clone https://github.com/quanq026/akaine.git $repoRoot
Set-Location $repoRoot
```

You should now see `README.md`, `server`, `scripts` and `docs`:

```powershell
Get-ChildItem
```

## Step 5: confirm the folders are separate

```powershell
$repoRoot = [Environment]::GetEnvironmentVariable("AKAINE_REPO_ROOT", "User")
$privateRoot = [Environment]::GetEnvironmentVariable("AKAINE_PRIVATE_ROOT", "User")
Get-Item $repoRoot, $privateRoot
```

Both paths must exist and must be different. The private folder must not be
inside the repository.

## Step 6: run the core readiness check

Close and reopen PowerShell, then run:

```powershell
$repoRoot = [Environment]::GetEnvironmentVariable("AKAINE_REPO_ROOT", "User")
Set-Location $repoRoot
python scripts\doctor.py
```

A prepared core workstation prints `OK` for `git` and `python`. The command
also reports the optional Android tools it can find. Apktool is expected to be
missing until the private resource chapter.

The complete Android tool list is:

```text
git
python
node
npm
java
adb
zipalign
apksigner
apktool
```

If `zipalign` or `apksigner` is missing, return to Android Studio's SDK Manager
and install Android SDK Build-Tools. The next chapter adds Apktool and runs the
strict check.

## Step 7: prepare the Python environment

From the repository folder:

```powershell
$repoRoot = [Environment]::GetEnvironmentVariable("AKAINE_REPO_ROOT", "User")
Set-Location $repoRoot
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
```

Verify the public source checks:

```powershell
.\.venv\Scripts\python scripts\ci_public_repo_check.py
.\.venv\Scripts\python -m compileall -q server scripts
```

The first command should end with `Public repository check passed`. The second
command normally prints nothing when compilation succeeds.

## Check your work

- The source and private-resource folders exist at the locations you chose.
- The private-resource folder is outside the Git repository.
- `doctor.py` reports all available tools accurately.
- Git, Python 3.12, Java 17 and adb print versions.
- The Python environment installs successfully.
- Public source check and Python compilation pass.

## Remove the local setup

1. Delete the `.venv` folder inside your repository to remove Python packages.
2. Delete the repository folder if you no longer want the source checkout.
3. Keep or securely delete your private-resource folder depending on your
   permission to retain the kit.
4. Uninstall Android Studio, Git, Python or Java from Windows Settings if
   you no longer need them.

Next: [Get and verify the private resource kit](04-private-resources.md).
