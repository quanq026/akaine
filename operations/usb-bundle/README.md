# Local USB bundle installation references

These two files preserve the exact reviewed operator helpers used on 2026-10-26.
Their relative `HERE` location belongs to the original workspace paths in
`PROVENANCE.json`; do not launch the references from this directory. Media,
transport archives, machine-local input paths and per-device journals stay
outside Git.

The transport is a plain USTAR archive. Every source span is hash-checked, its
writer computes the complete archive SHA, and a final header inventory rejects
anything except the expected regular files. Media bytes are never encoded,
resized or compressed. The receipt binds exact manifest, archive hash and size.

The installer operates on one explicit allowlisted device. It checks APK identity,
space, app UID, parent/symlink boundaries, force-stops the app, pushes the archive,
verifies its device hash, extracts into a fresh app-owned tree and verifies all
20,903 resources plus metadata. A second force-stop precedes the cache switch.
The previous complete `cb` directory is retained when it exists. An EXIT trap
restores it if promotion fails; this is a recoverable two-rename operation,
not a crash-atomic filesystem transaction. Controls/logs are outside `cb`.

A local cache copy does not validate native downloader progress, API aggregate
size above4GiB, per-song original MP3/Ogg metadata publication or all codec paths.
Those release gates remain separate. No production route or R2 object is changed.

A fresh-install follow-up found that an inherited umask could create `files/`
with mode0777. The current helper explicitly creates a missing parent with0700,
requires app UID/GID and rejects world-write, symlinks and non-directories. It
does not silently change an existing parent. The original emulator was repaired
separately to Android-standard0771; content and APK bytes stayed unchanged.
