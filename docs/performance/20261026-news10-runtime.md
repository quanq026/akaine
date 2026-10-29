# V36 news page construction: emulator verification

The user approved showing only the ten latest Main Menu news cards. The complete
song catalogue, all image/audio bytes, and Song Select behavior remain unchanged.

## Cause and change

Main Menu rebuilt 199 news pages each time. Instrumented normal V35 attributed
2.48–2.53 seconds (92–93% of warm initialization) to ContentUpdateLayer. Catalog
lookup and the native validation loop were small; page construction dominated.

V36 preserves the native validation, sort, owning descriptor storage and cleanup.
It ranks descriptors by canonical song date (a pack uses its latest member date),
retains native order for ties, and builds at most ten pages. Unknown state follows
the original native path. No cross-constructor cache or resource conversion was added.

## Runtime evidence

The same ASG emulator and normal guide CLI were used, with original-quality local
base25. Actual mapped core/monitor hashes matched the reviewed outputs. Native
reads confirmed 199 retained descriptors, ten PageView items and descending dates.

| Return from Song Select to Main Menu | Actual presentation gap |
| --- | --- |
| Normal V35, two returns | 2,578 / 2,734 ms |
| V36, two returns | 510 / 426 ms |
| V36 warm repeat, two returns | 767 / 391 ms |

The repeated Main Menu stalls fell roughly 70–86%. This measures presentation
stalls during that transition, not total command time or initialization CPU.
SurfaceFlinger column two was sampled every 0.25 seconds, prehistory was removed,
and the captures had no disjoint snapshot pairs. Host and Android clocks were
never subtracted. Action order and plateau windows identify the transition.

The same native navigation path reached gameplay and passed Pause/Quit twice.
All Songs still contained 2,440 native eligible entries in the current account.
Testify, Arghena, DIE IN and Daybreak selection passed. Mod/Variety transitions
passed, and restarting retained login, settings and the local bundle.
Detailed sanitized hashes and caveats are in `20261026-news10-runtime.json`.

## Remaining work and limits

Main Menu to Song Select, opening Pack Select and gameplay loading still contain
second-scale stalls. This patch does not complete every menu/loading target.
Do not use the mixed-scene 45-second average FPS as a scene FPS benchmark.

Physical-device improvement is unmeasured. The public staging bundle is still the
older quality-reduced base20; the original-quality base25 is local and has a
separate online download/activation gate. Nothing was deployed to production.
Canonical dates include placeholders/future values; equal-date chronology is not
invented. ANGLE/Vulkan work remains deferred.
