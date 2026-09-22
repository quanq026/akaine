# Lessons and failures from building Akaine 7.0.255

This chapter records problems encountered while building and operating the
7.0.255 client, content bundle and server. It is meant to save you from
repeating the same diagnosis, not to replace the build and release procedures
in chapters 6 and 7.

The most expensive mistakes came from changing the wrong layer. Akaine has an
Android wrapper, native game code, a content bundle, remote song storage,
server metadata, account data and several caches. A successful check in one
layer says little about the next one.

## Use evidence levels carefully

Use the narrowest accurate description when reporting a result:

| Level | What it proves |
| --- | --- |
| Static verified | Files, hashes, package metadata or manifest structure are correct without running the client. |
| Server verified | The expected API response and server-side state were observed. |
| Client verified | The real client completed the named action without a crash or unexpected response. |
| Gameplay verified | A chart entered gameplay and continued far enough to exercise chart and audio loading. |
| Restart verified | The same state still works after fully stopping and reopening the app. |

"The file exists", "the service is active" and "the title screen opened" are
useful observations. None of them is a complete release result.

## Start with the symptom, then isolate the layer

| Symptom | First layer to inspect | Evidence to collect before changing anything |
| --- | --- | --- |
| APK will not install | package identity, alignment and signer | adb install error, `aapt` badging, zipalign and apksigner verification |
| Login works but Cloud Sync logs out | native request routing | client log, server request log and route comparison for direct API calls |
| Bundle reports `-1013` | bundle manifest and partition bytes | manifest, part names, offsets, lengths, hashes and Range response |
| Bundle reaches 100%, then boot-loops | catalogue references or startup resources | first cold-start log after installation and final `songlist`/`packlist` |
| Song is black but can otherwise exist | selector assets or native reveal state | jacket/preview hashes plus comparison with a known-good control song |
| BYD is visible but cannot be selected | native class-3 registry state | exact song ID, difficulty class and selector log/behavior |
| Download icon remains | DownloadList contract | client request, `song_metadata.json`, allowlist and actual CDN objects |
| Song crashes when play begins | chart/audio/AKFC runtime | logcat fatal or FMOD line, requested difficulty and delivered files |
| Score saves but PTT does not move | chart constant and rating eligibility | chart row, best-score rating and whether the play enters B30/recent |

Record the exact time and stop touching the app after a crash. Repeatedly
reopening it can overwrite the useful section of logcat.

## Client lesson: one hostname was not the whole routing system

An early source-built client could sign in, but Cloud Sync returned error `-4`
and the account appeared logged out after restart. The server database, login
token and DNS were initially suspected because the symptom looked like an
authentication failure.

The client actually had two routing mechanisms. Visible strings handled login,
aggregate and content-bundle requests. Direct endpoints such as saved-data
requests used a separate encrypted shared API base. Patching only the visible
URLs produced a client that looked connected until it used one of those direct
routes.

The fix was added to the guarded native plan, then verified with this complete
sequence: login, Cloud Sync download, force-stop, reopen, confirm the account is
still signed in, and run Cloud Sync again.

The lasting rule is to trace the request that failed. A successful login does
not prove that every API family uses the same host.

## Client lesson: bisection beat a convincing theory

The AKFC loader originally risked packaging a process-wide `libcrypto.so`.
That could interfere with unrelated native code, so the public build moved to
a statically linked BoringSSL archive whose symbols have an `akfc_` prefix.

When the logout problem remained, it was tempting to keep blaming the loader,
DEX rebuild or crypto change. Candidates were rebuilt with one component
changed at a time. A client with the public static loader and no process-wide
crypto library still synced correctly when paired with the known-good native
game library. Replacing that library reproduced the failure and led to the
missing shared API base operation.

This is why chapter 6 keeps receipts for exact APK members. Compare archive
entries and change one variable per candidate. Several simultaneous changes
can produce a working build without identifying which change mattered.

## Client lesson: install-over depends on the signer

The package name and version code are not enough for an Android update. An APK
signed with a different certificate cannot replace the installed package.
Uninstalling to "fix" the error deletes local application data.

Keep one signing identity for the package, record its certificate SHA-256 and
back up the keystore. When the signer is unknown, stop and decide whether local
data can be lost. Never automate uninstall as an install-error fallback.

## Bundle lesson: 100% checking can still produce a permanent boot loop

A bundle once downloaded and checked to 100%, then crashed before the start
screen on every launch. The bytes and transfer were valid. A pack had been
removed while songs and a child pack still referred to it.

The client accepted the archive and failed later when resolving catalogue
relationships. That is why the 7.0.255 builder now rejects a `song.set` that is
neither `single` nor a current pack ID, and rejects a `pack_parent` whose parent
does not exist.

Do not repair a selector by deleting pack entries until the screen looks
clean. Change the pack, its child packs and all member songs as one coherent
catalogue operation.

## Bundle lesson: full roots were safer than unproven deltas

Some early candidates used a one-part or delta layout because it was faster to
produce. The client rejected layouts that appeared reasonable in static
inspection with `-1013` or repeated the update.

The reliable 7.0.255 path starts from a known-good full root with
`previousVersionNumber: null`, preserves the source partition contract,
recomputes every span hash and publishes a new alias. A local success is not
enough: the manifest and every part must also match after a full CDN download.

Never overwrite a cached alias with new bytes. A new content version needs a
new object name even when the previous release was broken.

## Bundle lesson: a screen at 100% may still be working

Large bundles can remain on a 100% checking screen while the client moves data
from temporary storage and extracts it. Tapping the confirmation button again,
force-stopping the app or restarting the emulator during that transition can
create a different failure.

Observe file growth and logs for a bounded period. If temporary bundle data is
still changing and there is no fatal line, wait. "The percentage stopped
moving" is not the same as "the process is dead".

## Selector lesson: valid assets did not guarantee a preview

Several Divine/Konzetsu songs had valid jackets and `preview.ogg`, yet the
selector remained black or silent. Replacing assets and changing server
unlocks did not address the behavior. A comparison with control songs showed
that the native pre-challenge reveal state suppressed the selector before FMOD
was involved.

The release fix changes only the verified 7.0.255 native state path. Bundle
assets are still required, but they were not the root cause in that incident.

Always compare one affected song with one known-good song. If both request the
same valid asset but diverge before playback, inspect the client state gate
before rebuilding the CDN content again.

## Selector lesson: entitlement did not make BYD selectable

The server could grant a song and the bundle could contain its class-3 chart,
while the BYD tile stayed absent or visible but unclickable. Final Verdict songs
and Axium Crisis exposed this distinction.

The missing layer was the client's active-state registry for specific class-3
song IDs. The guarded allowlist fixed only the verified IDs; it did not grant
every unknown BYD chart automatically.

Test the actual difficulty tab. Seeing the song at FTR is not proof that its
BYD entry exists. Seeing a BYD tile is not proof that tapping it reaches
gameplay.

## Gameplay lesson: FMOD error 18 was not a single diagnosis

FMOD error 18 was initially treated as proof that `base.ogg` was missing. In
practice it can also follow a bad file-read contract or a chart that requests
an unresolved effect file. If the same OGG plays with a control chart, the
audio container is unlikely to be the only problem.

Check the log for the exact filename FMOD tried to open. Inspect AFF arc-effect
tokens, difficulty-specific audio paths and the native read result. Do not
replace a valid OGG repeatedly without evidence that decoding that file failed.

## Gameplay lesson: special charts need null-safe state

Aether Crest ETR could crash because a special-condition list was absent while
native code assumed it existed. Assets, entitlement and chart delivery could
all be correct before this dereference.

The accepted patch adds a null guard and keeps the ordinary non-null path
unchanged. This is safer than forcing a global "unlocked" result at a later
renderer branch. For unusual charts, trace the earliest shared state check that
fails.

## Download lesson: four inventories must agree

A remote song is described by several inventories:

1. bundle `songlist`, including `remote_dl` and `additional_files`;
2. server `song_metadata.json`;
3. protected-file allowlist;
4. actual public and protected objects in R2/CDN.

If the bundle asks for an additional video or WAV that metadata does not
declare, or metadata declares a file that storage cannot return, the client can
keep a download icon even when the main OGG and chart are valid.

Treat `additional_files` as a subset of the metadata file list. Verify the
actual response, byte count and checksum for every requested object. A `200`
for one file does not prove the song's complete download set.

Difficulty-specific previews are separate from playable audio. When
`audioOverride` is active, a selector may require
`<ratingClass>_preview.ogg` even though the downloadable `<ratingClass>.ogg`
exists elsewhere.

## Emulator lesson: a process death was not always an app crash

During a large bundle install, an undersized emulator became unresponsive and
Android's low-memory killer terminated the game. There was no native fatal,
JNI error or linker failure. The event looked like a post-download crash from
the screen alone.

Check logcat for `SIGABRT`, `FATAL EXCEPTION`, tombstones and process-exit
reasons. LMKD kills, system-wide ANRs and emulator stalls belong to the test
environment until they reproduce with app-level crash evidence. Increasing
the emulator's RAM allowed the same data and APK to finish booting.

This does not mean every crash is an emulator problem. It means the cause must
come from the log, not from the moment the window disappeared.

## CDN lesson: Range and cache HIT did not prove throughput

A small Range request could return `206`, the correct `Content-Range` and
`CF-Cache-Status: HIT` while a large client download remained slow or timed
out. In one investigation, an independent cloud host downloaded quickly while
the Windows connection collapsed intermittently.

Verify byte identity first, then measure full or concurrent downloads from a
second network before changing R2 or cache rules. Correct cache semantics prove
the route and bytes, not the sustained speed of one client connection.

## Server lesson: active did not mean ready

After a service restart, `systemctl` could report `active` before the local
HTTP port had finished binding. Nginx briefly returned `502`. Restarting again
only made the observation noisier.

Use a bounded readiness loop against the expected API route. Promote or roll
back only after the route succeeds or the timeout expires. Process state is one
signal; the HTTP contract is the release gate.

The content-bundle API must also remain uncached. Static bundle objects benefit
from long cache lifetimes, while a cached `/game/content_bundle` response can
make current clients redownload old content.

## Data lesson: compatibility belongs at the boundary

Some older clients used a compatibility song ID while 7.0 used the canonical
ID. Rewriting stored scores to whichever client was currently being tested
would have split player history. The safer design keeps one canonical storage
identity and translates only when serializing for a legacy client.

The same principle applies to 7.0 progression fields. Extend old account data
without discarding scores, purchases or cloud saves. Verify both an existing
account and a newly created account; testing only an administrator account can
hide migration gaps.

A saved score does not automatically prove PTT is correct. The chart constant,
best-score rating and B30/recent eligibility all participate in that result.

## Release lesson: staging must prove the route as well as the feature

A healthy staging API does not prove the installed client is using it. Before
accepting a staging test, correlate the client's fresh request with the staging
server log and verify the returned content version. Otherwise a client can
silently test production while everyone believes staging passed.

Promote the exact bytes tested on staging. Rebuilding between staging and
production creates a new artifact, even if the source did not intentionally
change. Keep the previous APK, bundle manifest, server configuration and
database backup until cold install, restart and normal downloads pass.

When a request returns `429`, wait for the retry window and resume the same
step. Rebuilding, renaming or clearing data does not repair rate limiting and
destroys useful evidence.

## Rules kept after these incidents

- Change one layer at a time and keep its receipt.
- Compare an affected case with a known-good control.
- Preserve the first useful log before reopening or retrying.
- Use new immutable names for release objects.
- Treat download, gameplay and restart as separate gates.
- Never uninstall, clear player data or edit production as a diagnostic shortcut.
- Keep staging isolated and prove which endpoint the client reached.
- Call a result release-ready only after the real client passes the named action.

These rules are intentionally stricter than "it worked once". Most costly
failures in this project worked once, passed one layer, or looked correct from
the wrong side of the system.
