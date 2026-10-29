# Remaining menu/loading stalls: implementation plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` when implementation is authorized. Track the checkboxes below. This document is a proposed plan only; no diagnostic, client patch, installation or service change is authorized by writing it.

**Goal:** Remove the remaining second-scale stalls when entering Song Select, opening Pack Select and entering gameplay, while preserving original media and game behavior.

**Architecture:** Measure the owner of each stall, then change the smallest expensive operation. Reuse the existing native phase diagnostics, semantic CLI and source release pipeline. Treat shared texture eviction, repeated pack updates and gameplay preparation as hypotheses until their cost is measured.

**Tech stack:** Existing ARM64/C++17 client adapters, assembly gates, Python tools, ADB, SurfaceFlinger and simpleperf. No new dependency is planned.

**Spec/evidence:** The user's three-target planning request; [V36 runtime evidence](../../performance/20261026-news10-runtime.json); [exact native targets](../../performance/20261026-next-transition-targets.json); [V36 build boundary](../../rebase/BUILD_V36_NEWS.md).

**Status:** Execution authorized by the user on 2026-10-26. Baselines and coarse + one-partition native attribution are complete for all three areas. No product fix has passed the benefit/correctness gate; implementation for all three areas is deferred under the agreed cost limit after final static review. See `docs/performance/20261026-remaining-transitions-status.md`.

## Global constraints

- Start from accepted staging V36, commit `084d93ec5f6bff3f2720ec936edba73138723983`.
- Accepted APK SHA-256: `f826119d5d6c89dc3591a2c32df32022578ff5e1879e2e2cbe9c15ff9ab3a372`.
- Keep the current ASG emulator, 30 GB userdata, 4 CPU, 4096 MiB RAM, 1280×720 at 120 Hz and original-quality local base25.
- Preserve all song/chart availability, original image/audio bytes, native validation and cryptography. The current account exposes 2,440 eligible Song Select entries; its count is a fixture, not a limit on future libraries.
- Preserve V36 news10 behavior, guide CLI, partner skills, account state, search/filter/sort and dynamic pack capacity.
- Use semantic CLI actions for navigation. Screenshots are evidence only; no coordinate clicks or image recognition controls.
- Do not change FPS caps, audio routing/presets, emulator graphics, bundle contents or online services during this comparison.
- Keep Vulkan/ANGLE, online bundle activation and score/cloud changes outside this plan.
- Test on the emulator first. Physical-device verification follows emulator acceptance and device availability.

## 1. Baseline and measurement contract

| Target | Observed V36 presentation stall | First question |
| --- | --- | --- |
| Main Menu → Song Select | Approximately 1.9–3.1 s | Incoming scene construction, outgoing teardown or transition work? |
| Open Pack Select | Approximately 1.6–2.4 s | First construction or repeated update of the existing layer? |
| Play → loading → gameplay | Approximately 1.5–2.3 s | Which preparation phase blocks animation, and does it precede/follow GameScene initialization? |

These are observed gaps between presented frames, not constructor durations or CLI round-trip times. They are baseline ranges, not predicted savings.

### Task 1: Establish three separately attributable baselines

**Reuse:** Workspace `work/emu-finish-20261025/capture_long.py`, `work/perf-20261023/analyze_frames.py` and `work/menu-performance-20261026/asg_navigation_capture.py`.

**Output:** Private measurement artifacts under a fresh `D:/AkaineBuilds` directory; portable aggregate evidence in `docs/performance/`. No runtime account data or game media enters Git.

- [ ] Verify the installed APK/core/monitor identity, ASG, local bundle and unchanged settings before a capture.
- [ ] Capture each transition independently. Record one first-use sample and two warm repeats initially. Do not label an app restart as a filesystem-cold test; do not drop OS caches or wipe the emulator.
- [ ] For each sample, record total transition latency, largest actual-present gap and frame-time distribution during the animation. Record native wall/CPU attribution separately.
- [ ] Retain SurfaceFlinger column-two actual-present timestamps; trim prehistory; reject coverage gaps. Attribute actions with acquisition windows or Android-clock scene markers, never by subtracting host and Android clocks.
- [ ] Do not build, hash large files, record audio or take screenshots during a performance capture. Keep incidental CLI reads outside the measured native interval.
- [ ] Distinguish native invocations from user actions: one action can construct more than one scene/root. Reject partial or quota-censored data as evidence of complete loading cost.

**Gate:** Baselines must identify which transition owns each gap. A mixed-scene average FPS is not an acceptance metric for any of the three targets.

## 2. Song Select — first priority

### Task 2: Locate the expensive phase

**Reuse:** Existing workspace `content-update-phases-diagnostic-v2` sequential timer, parser/fixture conventions and build precondition checks. New probes stay outside the accepted release profile.

**Exact first probe:**

| RVA | Meaning |
| --- | --- |
| `0x161a8c4` | SongSelectScene initialization entry |
| `0x161a914` | Before TextureCache eviction call |
| `0x161a918` | After that call |
| `0x161e784` | Normal initialization return |

- [ ] Check original instruction bytes and branch/ABI preservation; review the compiled probe before installation.
- [ ] Accept only complete, ordered roots on the actual owner thread. Use bounded aggregates flushed outside measured regions. Preserve native return values and exception behavior.
- [ ] Separate preamble, direct eviction and the remaining constructor. Preserve the existing clock-conservation rules; do not clamp negative/skewed values into valid results.
- [ ] Compare constructor wall time with the presentation gap. If construction is small, examine outgoing scene destruction/transition scheduling next.
- [ ] If the remaining constructor dominates, split its largest measured section once to distinguish list/presenter construction, image read/decode and GPU upload.

### Task 3: Apply only the supported Song Select fix

Select the first applicable small change after Task 2:

1. **Repeated resource removal/recreation:** First establish that the same expensive resource is evicted then requested again. Retain only that resource across the relevant transition with a bounded owner/lifetime and explicit release. Do not disable global texture eviction or retain the whole library.
2. **Repeated derived-list work:** Reuse an existing valid native result where possible. Invalidate on the inputs the computation actually reads; prove freshness before skipping any work.
3. **Offscreen presenter construction dominates:** Reuse the native lazy/recycling path. Keep every logical song searchable/selectable; do not cap Song Select entries.
4. **Non-GL preparation dominates and no small reuse fix exists:** Consider a narrowly scoped background operation only after proving thread safety and cancellation. Keep node creation and GL upload on their owner thread.

**Tests:** Repeated enter/back, search/filter/sort, changing pack/difficulty, downloaded and undownloaded songs, unlock/sync/content changes if they are cache inputs, image completeness and bounded retained resources. Use the full catalog and a filtered view. Restore normal V36 after diagnostic-only runs.

**Deliverable:** A measured Song Select improvement or a documented rejected candidate. Shared texture eviction is currently a measurement target, not an accepted cause.

## 3. Pack Select — second priority

### Task 4: Separate first creation from each-open update

Native code already reuses the PackListLayer at scene `+0x3a8`. Re-caching the same layer would duplicate existing ownership.

**Exact first probe:** `0x19f859c` entry; `0x19f8834` before update; `0x19f8838` after update; `0x19f88d8` before virtual tail dispatch. First custom initialization is `0x1393564`; each-open update is `0x1763524`.

- [ ] Label first-open and existing-layer roots separately.
- [ ] Measure creation/preparation, update and post-update phases. The last probe is before a tail dispatch, not completion of Pack Select; retain the presentation capture to cover the remaining animation/dispatch.
- [ ] If the per-open update dominates, partition only its expensive substep. Do not assume the whole update can be skipped.

### Task 5: Remove proven repeated pack work

- [ ] Prefer an existing native dirty/revision signal. Otherwise reuse only the measured derived result and define its exact input set.
- [ ] Invalidate for relevant catalog revision, difficulty, selected pack/category, filter/sort, ownership/unlocks and download state. Avoid a global cache that becomes stale after Cloud Sync or a bundle change.
- [ ] If first creation dominates, examine visible-card construction/recycling; preserve every pack, category and scroll target.
- [ ] Verify Mod ↔ Variety, all category navigation, open/close/reopen, selected-song preservation, search/filter/difficulty changes and refresh after sync/download.
- [ ] Inspect resource counts and memory over at least ten repeated opens. A stale view or steadily growing retained-resource count rejects the cache candidate.

**Deliverable:** Separate first-open and warm-open results, plus a freshness/ownership fixture for any new reuse behavior. Preserve dynamic pack storage and avoid fixed-size assumptions.

## 4. Gameplay loading — third priority

### Task 6: Locate the blocking preparation phase

Start with GameScene entry `0xe2ea48`, before texture eviction `0xe2ee2c`, after it `0xe2ee30` and normal return `0xe2f948`. Recheck these instruction boundaries against the exact V36 core before building a probe.

- [ ] Capture selection → loading → loading exit → first gameplay frame. Determine whether the stall occurs before, inside or after GameScene initialization.
- [ ] Measure the phase that owns the gap, then distinguish chart read/decrypt/parse, audio open/decode/start and texture/node preparation only within that phase.
- [ ] Compare one already-downloaded official chart and one protected fan chart; include one resource-heavy chart after the smaller case is understood. Keep difficulty, partner, replay and audio settings controlled.
- [ ] Use historical protected-loader evidence only to prioritize. Three earlier opens took 19.619, 24.160 and 114.298 ms, with completion wait below 0.373 ms; that capture does not establish current whole-loading cost or audio/chart parsing cost.

### Task 7: Preserve animation while fixing the measured blocker

Candidate order:

1. Remove a proven duplicate read/parse/initialization within the same song-load request.
2. Reuse an already valid resource with an explicit lifetime and invalidation policy.
3. If one long non-GL task remains, consider a bounded prepare stage or worker only for that task. Define cancellation on Back/Quit/retry/song change and discard stale results.
4. Keep audio playback start, chart clock initialization and gameplay readiness synchronized with the original native contract. No early audio playback, lower-quality decode, validation bypass or decrypted chart persistence is permitted.

**Tests:** Official/protected chart, first use/retry/second song, Pause/Resume/Quit, failed/missing download, rapid song change/cancellation and restart. Inspect original media hashes and compare audio timing with V36. Any worker/caching change needs a focused stale-result/cancellation/ownership fixture before target execution.

**Deliverable:** Report animation stalls and total time to gameplay separately. Smoother animation may be valuable without shorter total loading, but it must not conceal a longer load or worsen gameplay timing.

## 5. Acceptance, cost limits and release integration

### Task 8: Validate each chosen fix independently

- [ ] Before implementation, declare the target metric and baseline for that fix. Preferred target: at least 30% reduction in the matched warm stall, reproduced in two short validation blocks. This is an engineering target, not a predicted gain.
- [ ] Report first-use/cold-start behavior separately. Investigate a repeatable regression above 10% rather than hiding it inside a warm average.
- [ ] Reject changes that reduce media quality, lose entries/cards, leave stale state, grow resources across repeated transitions or regress smooth gameplay/audio timing.
- [ ] Keep the news10 return-to-Main-Menu gain within normal baseline variation. Recheck guide behavior, partner skill, selected state and account/bundle retention where the changed path can affect them.
- [ ] A region accounting for less than 10% of a stall is not the main target. Allow one coarse probe and one partition of its dominant phase per area before reassessing the benefit/cost.
- [ ] Prefer a small fix saving hundreds of milliseconds. If the only remaining proposal is a broad worker/preload/cache redesign for a small gain, document the estimate and defer that feature instead of implementing speculative infrastructure.
- [ ] Do not promise a percentage until ownership is measured. Do not remove native transition duration merely to make a command finish sooner.

### Task 9: Package accepted work without losing V36

- [ ] Integrate each accepted change as a reproducible sibling profile of V36. Preserve previous profile/owned-source bytes; use a sibling authored file when a shared file would break old source locks.
- [ ] Record original-byte preconditions, gate/ABI checks, invalid-state fallback and every declared native difference. Release gates must have supported unwind/ABI behavior; QA-only instrumentation limitations must not enter a distributable APK.
- [ ] Rebuild the five payloads from the authentic production V9 root, verify original APK assets/members, sign separately and run the bound artifact verifier.
- [ ] Install only the reviewed emulator candidate; complete the targeted runtime check and retain the last accepted V36 APK as rollback.
- [ ] Commit sanitized code, source locks and before/after evidence to the private branch. Do not commit binaries, media, account data, credentials or private input maps.
- [ ] After emulator acceptance, verify the accepted candidate on physical Android for animation pacing, memory and audio timing. Report untested device behavior explicitly if a device is unavailable.

## Execution order and checkpoints

1. Baseline three transitions with V36 unchanged.
2. Song Select: measurement → smallest justified fix → paired validation → checkpoint.
3. Pack Select: measurement → smallest justified fix → paired validation → checkpoint.
4. Gameplay loading: measurement → smallest justified fix → paired validation → checkpoint.
5. Whole-flow regression, reproducible signed candidate and physical-device verification.

Static/source review can run in parallel with the root's work. One owner controls the emulator, and performance captures are serialized. Reuse a shared fix across targets only after both call paths and their measured benefit support it.

The next executable step, after implementation is requested, is Task 1 followed by the four-point Song Select probe. No emulator or client change was made to produce this plan.
