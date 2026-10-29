# Source reliability candidate and V19 R5 build contract

Historical source-review checkpoint. Use [the current five-payload build and verification workflow](local-release-build-final.md) for the combined staging release. The source/runtime loader mismatch described in later V6 equivalence notes supersedes the original read-mode-only fix summary below.

This candidate starts from repository snapshot `b6920d426581a946472ba18a877f78a10feb178c`. It does not deploy to a service, edit a live database, rebuild a game bundle or replace an APK. The accepted R5 runtime remains the control artifact.

## Focused fixes

- **AKFC read mode:** the existing fopen hook also accepts exact `rbe`, used by the retained native checksum path. Other read/write/null modes and error fallbacks remain unchanged. A host fixture compiles the actual extracted hook; the baseline reproduces failure and this candidate passes.
- **Pack parents:** the existing bundle catalog validator rejects self-parent and longer parent cycles before writing output. Traversal is iterative and linear; valid shared parents and a4,096-entry hierarchy remain accepted. No larger arbitrary pack cap is introduced.
- **Credential ingress:** Discord creation calls the repository in-process; account passwords are no longer subprocess arguments. Standalone account creation uses `--password-stdin` or getpass. The former positional password is rejected with a fixed error rather than echoed. Password whitespace is validated through the same existing validator used by the bot; it is no longer stripped silently. Username remains public argument input.
- **Account and mapping:** the original provisioning statements remain in `provision_account`, which uses the caller's cursor without committing or closing it. Discord attaches its mapping DB to the game connection, begins one transaction, provisions/verifies the account, inserts/verifies the mapping and commits once. Failure rolls back both. Duplicate retry creates no second account. Standalone `create_account` continues to own its transaction and supports dry-run.

The obsolete `LYGUS_CREATE_CLI` subprocess override is removed from bot settings. The maintained local provisioner now belongs beside the bot/core modules, while `LYGUS_GAME_DB` and `LYGUS_MAPPING_DB` continue selecting the intended databases. B30 subprocess behavior is unchanged.

### Journal boundary

Cross-file SQLite crash atomicity requires a file-backed main DB and rollback journals. The new creation method refuses WAL, OFF or MEMORY journal modes; it does not convert a live database's policy. This guard applies only to new account/link creation. Verify actual service DB modes before a deployment decision. [SQLite's ATTACH contract](https://sqlite.org/lang_attach.html) explains this requirement.

### Commands

```text
python -m unittest discover -s scripts -p test_catalog_parent_cycles.py -v
python -m unittest discover -s server/tools -p test_account_creation_atomic.py -v
python scripts/test_akfc_read_modes.py -v
python server/tools/create_user_cli.py QaPlayer --password-stdin --database <disposable-or-selected-db>
```

Supply password through private stdin; never insert it in a shell command. The C++ hook test uses an already-installed host compiler and skips when none exists. The Windows development host ran it through its existing WSL g++; no package was installed. Account tests use disposable databases. Full Discord integration tests require the project's existing Discord environment; these focused tests do not fabricate that dependency.

## R5 release input lock

`patches/arcaea-7.0.255-arm64/staging-v19-r5-source-lock.json` maps actual R5 compiler inputs and SHA-256 identities using logical private-kit roles. It includes56 observed monitor-local inputs, the owned translation unit's dependency-only scan, observed NDK headers/link archives/tools, DEX inputs/RawDexTool/JAR, core patch sources, generated pins, and four final replacement identities. No private source, game resource, signing key or password is exported into this source candidate.

`staging-v19-r5-plan.json` uses the **existing** `akaine.client-build.v1` schema. With the four accepted payloads materialized at their logical private-kit paths, the existing builder can assemble an unsigned APK:

```text
python scripts/build_android_client.py --source <private-kit>/base/v18-staging.apk --plan patches/arcaea-7.0.255-arm64/staging-v19-r5-plan.json --kit-root <private-kit> --output <physical-D-output>/v19-r5-unsigned.apk
```

This command is staging-only by its exact V18 source hash and pinned replacements. Alignment/signing remains the established separate operation with the public signer-certificate identity and environment-slot password ingress. Reusing signed payloads is artifact assembly, not proof of a clean source rebuild or signed-byte identity.

### Minimum clean build sequence still to implement

1. One ignored local config resolves private kit, SDK/NDK/JDK, work/output and signing-reference roots. Logical roles from the source lock replace dated absolute work paths.
2. Reuse current core gate assembly/patch code against the pinned V18 core. Regenerate core pins and run the existing branch/pin census.
3. Compile owned code with its existing exception boundary; compile monitor with its existing no-exception/no-RTTI flags. Link the same static runtime, page alignment and exports. Require the recorded payload SHA or explain a reviewed compiler/layout difference.
4. Disassemble pinned V18 DEX inputs using RawDexTool/dexlib2, apply only early prepare changes while preserving V18 pacing, assemble DEX037 and repeat existing method/checksum checks. Do not depend on an old pre-disassembled work tree.
5. Feed four verified outputs to the existing APK builder; align/sign/verify with the established private signing identity, then run the selected release's runtime gates. No deployment is implicit.

Current dated core/native/DEX wrappers still need that path normalization. The source lock deliberately says `CLOSURE_MAPPED_CLEAN_BUILD_NOT_YET_PROVEN`; do not claim source reproduction from the plan alone.

## Live parity and release decision

Fresh read-only capture found stage bot/provisioner differ from this snapshot, and staging lacks `discord_bot_core.py`. Production bot/provisioner also differ; matching production core hash alone does not establish parity. The new source candidate is **not a blind live overlay**. Reconcile actual initialization/configuration and journal state before a separate stage patch. Loader source fixture success likewise does not establish equivalence to the loaded production native module.

Root retains exact source baseline hashes, diff, test evidence, live-parity report and local-only role/path map outside the public candidate. No live deployment or physical ARM64 acceptance was performed by this source task.
