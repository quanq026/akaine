# Production V36 source profile

This sibling carries the accepted normal V36 client into production. Application
version remains `7.0.255`, package remains `akai.arc.lmao`, and the existing signer
is retained. Content metadata targets the separately published standalone
`7.0.255.25` base. The accepted V34, V35 and staging V36 authored files remain
unchanged.

The clean five-payload rebuild and signed-artifact checks have passed. The signed
APK is `AkaineXD-7.0.255-prod-v36-20261027.apk`, SHA-256
`a8b243c59adc527e8fa1ada27a0394979234d345b2063da40fcc2fbcc2ffc5fd`.
See [the production V36 checkpoint](RELEASE_PRODUCTION_V36.md) for the exact source
controls, artifact identity and bounded production runtime results. Restart,
login persistence and cache persistence also passed on the same signed build.

## Build boundary

`build_production_news_release.py` reuses the existing source compilers. The raw
core and DEX input is the authentic production V9 APK, SHA-256
`f14c5ab0871440dec7ecf2107d32d6e2cad745abc82047d03b49db9dbac3f545`.
Accepted final libraries are hash controls and never compiler inputs. Native
gates retain normal unwind metadata; no QA timing probes or unfinished scene-lag
experiments are included.

The core wrapper first rebuilds V36 from source, then restores precisely four
original production route spans. These cover login, aggregate, content-bundle
and the encrypted shared API base. Complete V36 accounting plus the finite
61-byte routing restoration binds every final byte. Production core SHA-256 is
`1097f9e03939ae0cd47fc958bbb95ed241f61cf1f44eb7c2ef71406ea3367bbe`.
CLI route pins cover both routing layers. Production bridge metadata and response
JSON use `production`; `scripts/akaine_cli/akaine_prod.py` rejects staging in both
checks. The original staging client continues to reject production.

The production Java partial cache accepts only the canonical
`https://cdn.akai.id.vn/bundle/` prefix and these immutable objects:

- `7.0.255-prod-original-base25-20261027_0.cb` through `_9.cb`.
- `7.0.255-prod-collapse-full-20261022_0.cb` through `_6.cb`.
- `7.0.255-prod-collapse-from14-20261022.cb`.

All existing destination, symlink, size, age, concurrency and exception guards
remain. Staging/test aliases and unlisted production URLs fall back to ordinary
temporary transport. The original production18 aliases support rollback.

## Candidate controls and clean rebuild

Keep the private path map and opaque loader header reference outside Git. Use the
configured QA Python runtime. Preparation derives only the production siblings;
it verifies unchanged inputs against the accepted V36 lock.

```text
python scripts/prepare_production_news_profile.py --frozen-kit <accepted-v36-private-kit> --private-output <private-production-input-directory>
python scripts/build_production_news_release.py candidate --local-paths <private-production-path-map.json> --output D:/AkaineBuilds/<fresh-candidate-directory>
```

Candidate mode derives all five source payload hashes and runs the Java/DEX
checks, but explicitly cannot assemble an APK. Its controls remain unaccepted.
Review source, the candidate receipt and the five hashes before sealing:

```text
python scripts/prepare_production_news_profile.py --frozen-kit <accepted-v36-private-kit> --private-output <private-production-input-directory> --seal-from-candidate-receipt <candidate-directory>/BUILD_RECEIPT.json
```

After preparing or sealing, check the two nonsecret loader entries in the private
map. `loader/compiler` must reference the pinned installed compiler driver beside
`clang++.exe`; `loader/crypto` must reference the pinned existing crypto archive.
Use the original operator map for those references. A frozen hydrated kit can
contain an extensionless compiler copy without its adjacent executable. Do not
copy the opaque key header or change any source/hash controls to work around it.

```text
python scripts/build_production_news_release.py verify --local-paths <private-production-path-map.json>
python scripts/build_production_news_release.py build --local-paths <private-production-path-map.json> --output D:/AkaineBuilds/<fresh-clean-production-directory>
```

The clean build must reproduce the sealed five payload hashes before unsigned
APK assembly. Signing is a separate operator action using the existing signer.
Loader key material remains compiler-only through the existing opaque environment
reference; the driver never reads, copies, hashes or prints that header.

## Signed verification

The signed artifact receipt must declare `environment: production`, package
`akai.arc.lmao`, exact five payload hashes, the pinned signer certificate,
the unsigned assembly hash, the asset-set identity and
`source_build_receipt_sha256` for the exact clean build receipt.

```text
python scripts/verify_production_news_release.py --local-paths <private-production-path-map.json> --build-receipt <clean-production-directory>/BUILD_RECEIPT.json --apk <signed-production.apk> --apk-receipt <signed-production-receipt.json>
```

The verifier checks sealed source inputs and its own pinned source, production
core/DEX/loader/cache provenance, actual signature and v2 scheme, all five signed
payloads, all 4,996 assets, both routing layers against authentic production V9,
and all 5,413 undeclared production members. Preserving the original manifest
also preserves package and application version. Staging receipts and candidate
controls fail closed. A successful static result does not claim runtime success.

No command in this document publishes cloud objects, changes a server, installs
an APK, or activates production content. Those remain separate rollout actions.
