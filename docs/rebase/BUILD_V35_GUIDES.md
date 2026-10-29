# V35 guide CLI candidate

This staging candidate adds `guide status` and `guide next` to the production
V9 rebase. It has no menu performance patch or media conversion. The original
V34 lock, checkout map, plan and build tools remain byte-identical.

## Sibling source profile

- `patches/arcaea-7.0.255-arm64/prod-rebase-guides-v35-source-lock.json`
- `patches/arcaea-7.0.255-arm64/prod-rebase-guides-v35-checkout-sources.json`
- `patches/arcaea-7.0.255-arm64/prod-rebase-guides-v35-plan.json`

The profile pins the four changed native guide inputs, matching host CLI, and
two added guide fixtures. Only the monitor payload differs from V34. Core,
loader, both DEX controls, production APK and asset identity are unchanged.
Content version `.20` is the retained client profile value; this source build
does not activate or publish a bundle.

## Build with the existing engine

Use the private path map with the reviewed guide monitor as its expected hash
control. Expected payload files are never compilation inputs. Set the existing
opaque header environment reference as described in [BUILD.md](BUILD.md).
From the repository root, run this with the configured QA Python runtime:

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path("scripts").resolve()))
import build_prod_rebase_release as release

profile = release.ROOT / "patches/arcaea-7.0.255-arm64"
release.PROFILE = profile / "prod-rebase-guides-v35-source-lock.json"
release.CHECKOUT = profile / "prod-rebase-guides-v35-checkout-sources.json"
release.PLAN = profile / "prod-rebase-guides-v35-plan.json"
lock = json.loads(release.PROFILE.read_bytes())
local = json.loads(Path("<private-kit>/prod-rebase-guides-v35-paths.json").read_bytes())
paths = release.bound_paths(lock, local["paths"])
release.verify(lock, paths)
release.build(lock, paths, Path("D:/AkaineBuilds/<fresh-v35-build-directory>"))
```

This uses the unmodified five-payload production-root pipeline, including its
input, provenance, private-header, dependency and asset checks. Internal unsigned
APK assembly is allowed after all five payloads match. Signing and installation
remain separate operator steps.

The existing builder and verifier command-line entry points still select V34 by
default. For signed V35 verification, keep the same three module bindings above,
then invoke `verify_prod_rebase_release.main()` with its usual receipt/APK
arguments in `sys.argv`. Its imported `release` is the same bound module. Calling
the default V34 entry point directly must reject this candidate's source hashes.

## Verification scope

The original guide QA APK exercised eight Welcome/Settings/Main Menu steps, two
Pack Hint steps, and one exact Advanced Tutorial Skip callback. Each `guide next`
performs at most one validated native callback, using fresh context. The last
Pack Hint step remained active with zero pending steps until its final callback;
one acknowledgement does not mean the whole guide has finished.

The simultaneous Pack Hint plus Advanced Tutorial case was not reproduced.
Its dispatch priority remains unproved and the CLI blocks competing guide
owners. Do not describe this candidate as fixing that exact overlap.

See [V35 source receipt](GUIDES_V35_SOURCE.json) for current build/test evidence.
The signed candidate reproduces the full SHA-256 of the earlier guide QA APK:
`63fe18f40ddd19289532f435a0a221067a0f60cab1d2f1001b8cdc189221fdc0`.
All five payloads, 4,996 assets and 5,413 preserved production members passed
verification. The prior native callback evidence applies to the identical APK;
this remains a staging candidate with no menu performance patch or production
publication.
