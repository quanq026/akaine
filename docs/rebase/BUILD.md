# Build the production-based staging candidate

This profile starts with the authentic 2026-10-22 production V9 APK and rebuilds
the accepted staging payloads. It does not publish to production or change a
server, database, Worker, song object or bundle route.

## Private prerequisites

Keep the production APK, SDK/JDK, crypto archive, generated game-byte pins,
expected controls and machine-specific path map outside Git. The input APK must
match the production SHA-256 in `DEVELOPMENT.md`. The existing signing key and
opaque loader key header remain operator-owned private resources.

The current output guard requires the configured physical D: build disk and a
fresh output directory. Do not overwrite an earlier build to bypass a failure.
All source files must retain their original bytes; Git attributes preserve them.

## Source build

From the repository root, with the configured QA Python runtime:

```powershell
python scripts/build_prod_rebase_release.py verify --local-paths "<private-kit>/prod-rebase-paths.json"
$env:AKAINE_PRODUCTION_KEY_HEADER = "<existing-private-key-directory>/embedded_key.h"
python scripts/build_prod_rebase_release.py build --local-paths "<private-kit>/prod-rebase-paths.json" --output "D:/AkaineBuilds/<fresh-build-directory>"
```

The compiler consumes the existing opaque header. The driver does not read,
copy, hash or log it. Five payloads must match their reviewed controls before
the APK can be assembled. Source/private/tool hashes are checked again afterward.

## Signing and verification

Use the existing operator signing helper and its environment-slot password
transport. Preserve the certificate pinned in the source lock. Use 16KiB native
ZIP alignment and verify the APK signature; do not put passwords in arguments.

The artifact receipt must bind the exact source build receipt, unsigned APK,
five payload hashes, source lock, checkout map, signer and asset identity.

```powershell
python scripts/verify_prod_rebase_release.py --local-paths "<private-kit>/prod-rebase-paths.json" --build-receipt "<build>/BUILD_RECEIPT.json" --apk "<signed-candidate>.apk" --apk-receipt "<signed-candidate>.receipt.json"
```

This verifier checks the production-root core/DEX provenance, exact build
binding, signature, assets and every undeclared APK member against production.
It rechecks input hashes before reporting success.

## Runtime

Use the matching `scripts/akaine_cli/akaine_stag.py` host on the isolated staging
emulator. Preserve the existing account and bundle cache with an install-over
update. Verify the loaded native hashes before testing Account Management,
Logout, private QA login, Cloud Sync Download and the main play loop.

Input is through native CLI callbacks. Do not use coordinate/OCR control,
automatic notes or synthetic scores. Emulator checks do not establish physical
speaker/Bluetooth quality, thermals or exhaustive song/partner coverage.
