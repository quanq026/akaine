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
