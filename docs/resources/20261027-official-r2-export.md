# Official-only R2 resource export — 27 October 2026

A private offline ZIP was prepared at the user's request. It contains the
standard Akaine `r2/` tree, matching `server/database/` content files, a Vietnamese
README and a standard-library-only verifier. No APK, toolchain, credential,
player database, fan chart or Aurora content is included. No R2 or server state
was changed and the ZIP was not published.

- 553 official catalogue songs, 62 packs.
- 2,427 canonical official song objects: 3,538,788,536 bytes, each matching the
  remote70 metadata MD5 and R2 snapshot ETag.
- 31 separate original official jackets.
- Five unchanged official base CB parts: 8,454 validated logical entries,
  including 11 official special/tutorial resource IDs.
- 2,472 files including the kit manifest; one empty private-song directory.
- ZIP64 size: 5,771,854,676 bytes. ZIP uses storage without media conversion.
- ZIP SHA-256: `48d305ec49d6b0c39c79fce2075aaff60e90df6eda472898c243c18c0dfc89a2`.

## Classification and layout

The original official source manifest has SHA-256
`74894af200205302f6028bba96b495d3b5e4fb062f6d74976d59a93730bdaea2`.
Its embedded 553-song catalogue exactly matches the live production remote70
catalogue. All original bundle spans and five whole-part identities passed the
existing source validators. The adjacent fan-album image is not a manifest entry
and was excluded.

Song objects come from the canonical official R2 namespace
`staging/7.0.255-remotedl-20260908/songs/`, normalized to `r2/songs/` in the ZIP.
Its exact file set matches official metadata. Legacy root R2 catalogues, mixed
bundles, private fan objects and undeclared extra difficulties under official
IDs were excluded. The private allowlist is `{}` and its song directory is empty.

```text
README.txt
manifest.json
verify.py
r2/bundle/<alias>.json
r2/bundle/<alias>_0.cb ... <alias>_4.cb
r2/songs/songlist
r2/songs/<official-id>/<declared-file>
r2/assets/jackets/<official-id>.jpg
r2/private/asset-manifest.json
r2/private/songs/
server/database/songs/songlist
server/database/song_metadata.json
server/database/bundle/<alias>.json
```

The portable alias is `akaine-7.0.255-official-base-20261027`. The unchanged source
version remains **7.0.255.5**: this kit is for an independent clean setup, not a
content-version downgrade for an already updated production/staging client.

## Verification and limits

Fourteen helper fixtures passed. The actual extracted kit's exact file set,
sizes, SHA-256 values, official ID membership and metadata/allowlist boundaries
passed. Every ZIP entry was read and rehashed, then the final external-drive ZIP
was verified against its whole SHA-256. A separate `SHA256SUMS.txt` accompanies
it. Temporary ZIP data on W: was removed after successful final verification.

This verifies archival identity and official-only membership; runtime playback
was not retested. Recipient tools/APK and deployment credentials are separate.
See the public [private-resource guide](https://github.com/quanq026/akaine/blob/main/docs/guide/04-private-resources.md)
and [R2 layout guide](https://github.com/quanq026/akaine/blob/main/docs/guide/05-cloudflare-content.md).
Those checked pages request private contact with the project owner/authorized
provider; no Discord handle or invite was published in the checked sources.
No message was sent to anyone.
