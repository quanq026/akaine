# Production V9 rebase checklist

Baseline: authentic production V9, 2026-10-22, APK SHA-256
`f14c5ab0871440dec7ecf2107d32d6e2cad745abc82047d03b49db9dbac3f545`.
Candidate: staging V34. Source/input locks count build inputs, not features.

| Change retained | Implementation or boundary | Verification |
| --- | --- | --- |
| Existing production game behavior | Actual production core is the input; only declared route, hook, gate and ELF changes are permitted | Complete output-byte reconstruction |
| Staging API selection | Four exact route spans, 61 changed bytes | Production preimages and whole normalized core hash |
| Dynamic owned-pack storage | Existing authored owned gates and module | Recompiled gates, regenerated pins, exact accepted final core |
| Menu Reset and child-order fixes | Reset, integrity and child-order assembly; guarded child repair | Exact compiled gate hashes and original fallback retained |
| Download size and duplicate-dispatch guards | Existing integrity and run-once gates | Exact source rebuild and finite hook preimages |
| Original encrypted chart loader | Existing production-compatible source and crypto | Rebuilt exact loader; opaque key stays outside Git |
| Initial 60Hz interval guard | One declared production DEX method replacement | 724 other classes and all other renderer methods unchanged |
| Startup preparation and frame pacing | Existing source-based startup/pacing builders | Generated production DEX inputs; exact final DEX hashes |
| Partial bundle download cache | Existing Java helper and bounded downloader changes | JVM fixture, class/method/exception-coverage checks and exact DEX |
| Physical-device map bounds | Existing V33 maps snapshot limits | Current source rebuilt into the monitor |
| Native CLI, onboarding and overlay state | Current V33 semantic adapters and host | Existing focused host/native fixtures retained |
| Current login errors and SubmitCycle | Current V33 account adapter | Independent review verifies these bodies are unchanged |
| Production Account Management and Logout | Merged into current account adapter, bridge and host | 128 host tests; native ownership/deletion-negative fixtures; independent review |
| APK assets and other original members | Original production archive, five declared payload replacements | All 4,996 assets match; signed verifier compares every other member to production |

The source build recompiles all five payloads. Expected binary files are identity
controls and never compiler inputs. Core and raw DEX come from the actual
production APK; the old staging APK and raw DEX are forbidden inputs.

## Separate artifacts

See [the non-APK ledger](NON_APK_LEDGER.md) for bundle/catalog, server, bot,
database grants and the historical deployed Worker. These are not implicitly
changed or deployed by installing this APK.

Lossy jacket/preview projection is rejected. Original-media recovery remains
offline and is not part of this APK's quality claim. Worker/preload experiments,
the deferred Reader cache and the canceled ArcCreate runtime are not new rebase
features.

## Acceptance records

- [Whole-archive baseline comparison](APK_BASELINE_DIFF.md)
- [Frozen V33 five-payload source reproduction](V33_BASELINE_SOURCE_PROOF.json)
- [Production-root build profile](../../patches/arcaea-7.0.255-arm64/prod-rebase-source-lock.json)
- Signed artifact and emulator acceptance are recorded separately after their
  checks complete. A successful build alone does not prove runtime acceptance.
- [V34 bounded acceptance](RELEASE_V34.md) records the completed checks and limits.

## V36 staging news construction

The user approved a ten-card Main Menu news carousel. Native validation and all
owning descriptors remain; only ten canonical-date-ranked UI pages are built.
The V36 sibling source build and runtime evidence are described in
[BUILD_V36_NEWS.md](BUILD_V36_NEWS.md) and the
[menu measurement report](../performance/20261026-news10-runtime.md).
Other scene/loading stalls remain separate work; this is not a production release.
