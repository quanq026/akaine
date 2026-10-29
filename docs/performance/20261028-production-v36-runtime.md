# Production V36: bounded emulator QA

Core emulator QA passed on the signed production V36 APK, SHA-256
`a8b243c59adc527e8fa1ada27a0394979234d345b2063da40fcc2fbcc2ffc5fd`.
The operator used the production API and an existing private QA account. Account
identity and credentials are excluded from this record.

**Restart, login persistence and cache persistence passed.** An early title
snapshot precedes native account initialization, so its `signed_in: false` flag
alone does not establish lost login. Native preparation later reached ready;
a fresh available Continue reached Main Menu with login retained. Direct Play
of the cached Aurora song then entered gameplay without another Download prompt.
Pause and Quit succeeded; the final state was Song Select with Replay Off.

## Passed cases and exact bounds

| Case | Observed result | Bound |
| --- | --- | --- |
| Production login / Cloud Sync | Login reached signed-in state; explicit Cloud Sync Download reached `success`. | Existing private QA account only; no account data is reproduced. |
| Catalogue / pack navigation | Operator checked installed content25: 2,543 songs and 63 packs. Pack catalogue reported 63. Mod 8, Variety 7, Mod 8 transitions succeeded; `xd_fan_album` exposed 1,888 current FTR entries. | A difficulty-specific native list is not the total installed song count. |
| DIE IN ETR | `diein`, native difficulty 4, entered gameplay. Pause, Resume, Pause and Quit returned valid states. | 60.85 seconds between confirmed gameplay entry and first pause response. No full-song clear or score claim. |
| Arghena FTR | `arghena`, difficulty 2, entered gameplay; Pause and Quit succeeded. | 39.30 seconds between confirmed entry and pause. The preceding download command exceeded the CLI deadline; see below. |
| Testify BYD, Replay Off | `testify`, difficulty 3, entered gameplay with replay disabled; Pause and Quit succeeded. | 9.01 seconds between confirmed entry and pause. Monitor: replay `disabled`, modifier `none`, mode `-1`. |
| Testify BYD, Replay On | Fresh semantic reads confirmed gameplay and replay enabled; Pause and Quit succeeded. Monitor showed replay selected, applied and native initialization ready. | Two successful gameplay reads were 23.27 seconds apart. Native modifier was `28SpecialSceneTestifyChallenge`, mode `2`. The Play command exceeded the CLI deadline. |
| Aurora download / gameplay | Production per-song Download for `aurora_bf2e0923` (`reflex`) succeeded; FTR gameplay, Pause and Quit succeeded. | 20.96 seconds between confirmed entry and pause. A clean full-screen paused PNG is retained outside Git. |
| Legacy FTR / Tempest | `amega_daybreakfrontline` entered FTR gameplay with character 35. Native expected gauge, scene gauge and life bar all reported `6`; Pause and Quit succeeded. | Bounded start/gauge/navigation observation, not sustained performance or full-song completion. |
| Legacy FTR / Grievous Lady | The same song entered FTR gameplay with the asset-verified character 7. Native expected gauge, scene gauge and life bar all reported `2`; Pause and Quit succeeded. | Character 7 is the Grievous Lady identity verified from actual APK assets. |
| Lacrymira preview | Character 98 was shown as the character-dialog preview, with selection available. | Preview only; no character98 gameplay or skill/gauge acceptance. |
| Restart / persistence | Fresh Main Menu retained production login without another submission. Bundle25 had no repeat update; cached Aurora FTR opened through direct Play without Download confirmation, then Pause and Quit succeeded. | The initial Continue acknowledgement remained at Title during online preparation. A later fresh available Continue reached Main Menu; no stale context retry. |

Wall intervals above come from command-record timestamps. They document the
bounded observations; they are not frame-rate, latency or performance benchmarks.

## Timeouts, guards and test corrections

The CLI has an existing 30-second command deadline. Arghena's `play_download`
timed out; a fresh read and a later explicit Play confirmed eventual completion.
The Testify Replay On Play also timed out; a fresh read 25.94 seconds after the
timeout already showed gameplay. Neither case used an automatic mutation retry.
These cases pass eventual-completion checks and do not pass a 30-second timing
target.

An initial `pack_close` in the wrong state returned `WRONG_SCENE`. Selecting
`diein` while the fan-pack list was active returned `SONG_NOT_IN_CURRENT_LIST`;
selecting the all-pack list then allowed it. Download confirmation guards were
respected before explicit Download commands.

Early guesses of character IDs 6 and 9 were test-selection mistakes. The Grievous
Lady assertion was corrected using the actual APK character assets, which map
Grievous Lady to ID 7. No product source change was made for those mistakes.

## Startup observation and monitor scan

The production startup observation reached native ready state at 126.3 seconds.
The process `read_bytes` counter was `4,652,531,712` and `rchar` was
`4,712,030,556` at that sample. These are process file-I/O counters, not network
download bytes. The accepted staging A/B also showed a native fetching/read wait.
This bounded observation introduces no product patch and claims no startup fix.

The retained redacted runtime-monitor sample contained zero matches for
`Fatal signal`, `FATAL EXCEPTION`, `JNI DETECTED ERROR` and `FileUtilsSaveError`.
This is a bounded log scan, not a claim that every crash path was tested.

## Evidence and limits

The [sanitized JSON record](20261028-production-v36-runtime.json) binds the signed
artifact, selected command-record prefix, character-ID proof, redacted monitor,
startup samples and screenshot hash. Raw logs and the PNG remain in the local
operator work folder outside Git. Only selected non-sensitive results and hashes
are carried into the repository.

The [installed identity receipt](production-v36-20261028/LIVE_EMULATOR_IDENTITY.json)
binds the actual installed APK and extracted core/monitor/loader hashes to the
signed source controls in the same running process. It also verifies installed
catalogue25 hashes and the 2,543-song / 63-pack counts.
The [restart receipt](production-v36-20261028/RESTART_QA.json) records the completed
persistence gate. The [derivation proof](production-v36-20261028/DERIVATION.json)
contains selected public state fields, source-prefix hashes and checked
assertions. These copies exclude account identity, credentials and session tokens.

The three unfinished loading/scene-lag investigations remain deferred. These
checks do not establish full-song clears, score/PTT uploads, exhaustive song or
partner coverage, physical-device speedup, long-duration FPS, thermals or physical
speaker/Bluetooth audio quality. Earlier staging runtime evidence is separate
from these production observations.
