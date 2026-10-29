# Original Aurora per-song delivery ledger

`prepare_original_delivery.reference.py` preserves the exact operator helper
used to prepare the original-byte delivery candidate. It does not upload, copy
or encode media and does not access encryption keys. It verifies existing
ciphertext-chart identities and original raw audio/resource identities, then
updates the per-song plaintext checksum metadata only where audio bytes differ.

This is a historical source reference, not a portable command from this folder.
Its `HERE`/`ROOT` layout points to the original workspace location recorded in
`PROVENANCE.json`. Re-run only in that explicit layout with fresh output names;
existing output files are rejected. Private source maps, object ledgers and
actual metadata remain outside Git.

The candidate uses a fresh private object namespace. No existing staging or
production object has been overwritten. Native MP3/pre-remux Ogg compatibility
and publication still require separate verification.
