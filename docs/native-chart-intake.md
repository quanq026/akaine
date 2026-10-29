# Current native-chart intake workflow

This is the local Akaine7.0.255 workflow. It reuses the current catalogs, server DownloadList metadata, AKFC encryption and bundle builder. It adds a read-only intake gate, not a new chart store, import catalog format, renderer or upload service.

## Input layout and identity

Keep the author's original ZIP/folder unchanged. A prepared native song payload is one flat folder (or flat ZIP) containing canonical `0.aff` through `4.aff` files for supplied classes, `base.ogg`, an ordinary `base.jpg`/PNG jacket and optional `preview.ogg`/resolution variants. The gate rejects nested directories, unsafe ZIP names, duplicate casefold filenames, links and bounded-size violations. Unknown extension files remain uninspected and quarantined; they are never executed or silently ported.

Use existing prepared files:

- Complete `songs/songlist` and `songs/packlist` from the overlay for the intended release.
- Server `song_metadata.json` in the existing `{song_id: {files, hashes}}` shape, with plaintext MD5 for every downloadable file.
- Optional constants JSON in the existing `Song.to_dict()` shape: `{song_id, name, charts:[{difficulty,chart_const}]}` or a list of those records. This is a server export/input shape already used by `server/core/song.py`, not a new constants store.

The report hashes the original ZIP, or the complete supported folder file inventory, and hashes each prepared catalog/metadata/constants reference. Supported files keep their original bytes and names. Unrecognized files are listed as uninspected quarantine reasons; the folder fingerprint is explicitly the supported-file set, not a false claim that their content was inspected. No timestamp or random identifier makes equivalent reruns differ.

## One read-only gate

From the repository, using the existing Python environment:

```text
python scripts/native_chart_intake.py validate \
  --source <native-song-folder-or-flat-ZIP> --song-id <stable_song_id> \
  --songlist <prepared-overlay/songs/songlist> \
  --packlist <prepared-overlay/songs/packlist> \
  --metadata <prepared-song_metadata.json> \
  --constants <optional-existing-Song-export.json> \
  --report <fresh-local-report.json>
```

Omit `--constants` when no reliable constant exists. The chart is then explicitly unranked (`-1`, no ranked classes); no constant is inferred from displayed level. A positive constant for a class without a real exposed source chart is rejected. The tool does not write the chart database or any score/PTT data.

`dry-run` executes the same validation and report path, with no source/catalog/build/encryption/publication changes. The output report refuses overwrite; omit `--report` for a summary-only check. Exit0 means the limited intake gate passed. Exit2 means `QUARANTINED_NOT_PLAYABLE`. Malformed input/dependencies fail before a successful report. Neither status is gameplay acceptance.

Existing `build_content_bundle.validate_catalog()` validates the complete song/pack relationship, duplicate IDs, missing parents and parent cycles. No62-pack ceiling is added: the current patched dynamic client uses its reviewed profile, while legacy clients retain their separately bounded server projection. Reusing a current supported pack remains the simplest import path.

The gate checks canonical AFF presence, note events, event separators/parentheses/arity and finite numeric fields. It recognizes the standard timing/tap/hold/arc/arctap/camera/timinggroup structure. Unknown event names, custom arc samples, nontrivial timing-group options and SceneControl consumers without proved native support are quarantined. It does not remove an event or replace a sample to force compatibility. Chart source is preserved for a separate reviewed compatibility decision.

Playable-note proof counts only events outside `noinput` groups, including inherited nested groups. A skyline/trace arc alone is visual; only its attached arctaps count as playable events. A standalone arctap is invalid. Difficulty `audioOverride` or `jacketOverride` is quarantined in this minimum flat-payload subset because class-specific audio/jackets are not yet supported and verified by this gate.

Prepared songlist, packlist, DownloadList metadata and constants bytes are snapshotted before checking and compared again before a successful report. The report binds those same checked bytes; an edit during source scanning fails rather than attaching a new hash to an old validation result.

For a real BYD class, declare `world_unlock=false` on the difficulty itself; song-level flags alone do not suppress the native class3 default. Do not fabricate visible difficulties to satisfy downloads. Any explicitly approved hidden completion shim must already exist in the prepared payload/metadata and remain hidden/unranked. The gate does not invent those copies.

## Remaining source checks

The intake audio check is the OGG container signature plus exact DownloadList hash. Run the existing FFprobe/decode step from chapter09 before building: require one Vorbis audio stream, sane duration/rate/channels and valid timestamps. A renamed MP3 may pass a filename check but must not pass that media probe.

The intake image check is dependency presence only. Use the existing jacket/background preparation and image preview checks for actual decode, dimensions, scale and alpha. Required preview audio, pack covers and backgrounds remain part of the prepared overlay review. Do not treat a limited intake receipt as a completed media/artifact verification.

## Reuse build/encrypt/staging commands

1. Preserve the intake report and exact original input hashes. Resolve every quarantine/missing dependency before encryption or publish. Positive constants remain blocked in the report while the chart is quarantined.
2. Prepare the overlay using the existing complete catalog rows, selector/jacket/preview assets and server metadata. Keep unrelated catalog rows unchanged. Run the existing bundle catalog/media checks.
3. Encrypt real AFF classes using `scripts/encrypt_akfc_aff.py` with the matching RSA3072 **public** key, stable song ID/class and a fresh output/receipt. It uses the shared server AKFC library and verifies the roundtrip in memory. Never put plaintext AFF under the public song route. Do not add another encryption implementation here.
4. Build from the known-good full source via `scripts/build_content_bundle.py --source <verified-source> --overlay <prepared-overlay> --output <fresh-output> --alias <new-staging-alias> --version <newer-content-version> --detail-key-file <private-HMAC-reference>`. The existing builder validates every source/output span, catalog dependency and authenticated detail. A content target must exceed current installed versions that must update. Private key values are never echoed or copied into reports.
5. Prepare the existing immutable R2/Worker allowlist and server metadata/constants plan. Use the established conditional-create/full S3+CDN SHA publication machinery. An intake gate does not authorize an upload, Worker modification, entitlement grant or database write. Root alone performs reviewed staging activation and owns rollback.
6. Verify actual client download/decrypt, native gameplay, skill/effects/audio, Results/score and restart persistence. Keep uncertain constants unranked. Production is a separate accepted promotion after staging.

There is intentionally no `stage` subcommand in this read-only gate. Staging requires the existing reviewed artifact/publication/activation receipts; making a second deploy path would bypass them. The command chain above is the single supported workflow, with this gate at its beginning.

## Historical tools and guide boundary

`server/tools/validate_custom_bundle.py`, `build_custom_bundle_update.py` and `rebuild_custom_catalog.py` retain6.14/executioner-era assumptions. They are historical utilities, not the current7.0.255 release path. Existing guide09 manual examples describe the old62-slot client; read this workflow and current build/profile receipts before using those examples. The new gate does not silently redirect those legacy tools or change a live server.

This slice does not reconstruct every SceneControl/ArcCreate extension, normalize media automatically, infer constants, modify source archives, import existing scores, add a persistent database or run CI/CD.
