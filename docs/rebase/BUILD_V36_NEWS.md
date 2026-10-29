# V36 news card construction

V36 is a staging sibling of the V35 guide checkpoint. Application version remains
7.0.255. The user approved showing the ten latest Main Menu news cards. The full
song library and original media are retained.

## Source and build boundary

The V34/V35 profiles, shared owned module and existing builders are unchanged.
V36 maps its owned module role to the sibling authored
`owned_pack_module_news_v36.cpp`; hydration keeps the original role filename.
The V36 source profile, checkout map and replacement plan use the `prod-rebase-news-v36-` prefix.
`build_prod_rebase_news_release.py` binds the existing five-payload pipeline to
that profile for the duration of one invocation.

`build_prod_rebase_news_core.py` rebuilds the ordinary core from the authentic
production V9 APK, then `build_news_core.py` compiles the two authored news gates.
The extension changes four finite spans: RX end metadata, the news sort call,
the news local-loop end, and a 180-byte gate region. Every other ordinary-core
byte is preserved. The final core and regenerated pins must match the reviewed
identities before the existing monitor, DEX, loader and archive steps proceed.
Accepted final native binaries are hash controls, never compilation inputs.

The monitor retains all V35 guide CLI behavior and adds the date-ranking callback.
It preserves the native sort/validation and all owning descriptor records, then
limits only the UI construction loop. Unknown module/rank/thread/owner state uses
the native behavior. Equal dates keep native order. Pack date is its latest member
song date; placeholder/future catalog dates are not rewritten.

## Operator commands

Use the existing private path map and opaque loader header environment reference.
Keep both outside Git. With the configured QA Python runtime, run:

```text
python scripts/build_prod_rebase_news_release.py verify --local-paths <private-path-map.json>
python scripts/build_prod_rebase_news_release.py build --local-paths <private-path-map.json> --output D:/AkaineBuilds/<fresh-v36-directory>
```

`payloads` is an optional stop after five matching payloads and base asset checks,
before archive assembly. `build` assembles an unsigned APK only after those checks.
Signing remains a separate operator action. For signed verification, enter the
same `build_prod_rebase_news_release.bindings()` context before invoking the existing
`verify_prod_rebase_release.main()` with its normal path/receipt/APK arguments.
The default old-profile verifier must not accept a V36 artifact.

## Verification

Eight focused host tests cover exact gate behavior, private-pin updates,
unknown-input rejection, binding restoration and the pre-assembly stop. The actual
emitted gates pass 1,152 fallback/owner/state cases. The pure C++ fixture covers
stable date selection and preserving whole owning records.

Runtime evidence is recorded in
[the V36 menu report](../performance/20261026-news10-runtime.md). The news-specific
return-to-Main-Menu stalls dropped about 70–86% on the ASG emulator. Other scene
transitions still stall and are not claimed fixed. Source/build/signature receipts
are recorded separately; a source build alone does not establish runtime success.

## Separate bundle gate

The profile retains content metadata 7.0.255.20; this build does not publish or
activate any bundle. The original-quality base25 was tested locally. Public
staging still serves the older quality-reduced base20, so broad original-quality
beta distribution remains gated on the separate online bundle workflow.
No production publication, phone installation, ANGLE/Vulkan change or CI/CD step
is included.
