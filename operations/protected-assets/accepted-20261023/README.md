# Historical accepted protected-assets Worker

This directory preserves the deployed source reviewed on 2026-10-23. It is a
historical implementation reference, not a deployment command or a claim about
the current live service.

| File | Purpose |
|---|---|
| `worker.accepted.mjs` | Exact reviewed source after the Aurora literal-allowlist extension. SHA256`54748325983a7c1bfc7e1b3486446a2d279f4782f68ce54218aff3ebed9f7402`. |
| `worker.before.mjs` | Exact preimage, retained for deterministic patch/rollback proof. |
| `allowlist-additions.json` | The1,532 added song IDs and6,434 exact filenames. These names do not contain game media. |
| `worker_catalog_patch.py` | Pure literal patch/owned rollback functions; no network or credential loading. |
| `test_worker_catalog_patch.py` | Existing synthetic rejection and preservation fixtures. |
| `PROVENANCE.json` | Exact file hashes, historical review references, content scan and focused verification results. |

The accepted change preserved458 existing song IDs/1,998 filenames and every
source byte outside one static JSON literal. It preserved the five binding
names/types and routes and added no broad `aurora_` authorization.

`cloudflare/protected-assets/worker.mjs` uses a generic manifest-driven design.
That file is different from this captured literal-allowlist implementation and
has not been replaced. A rebase must not silently deploy one as the other.

Only binding names are recorded. Secret values, live operator configuration,
Cloudflare credentials, signed URLs and private input maps are excluded. Fresh
live source/binding/route checks and a reviewed rollout are required before any
future deployment. No deployment wrapper or CI/CD job is supplied here.

## Offline checks

From the repository root, with an existing Python and Node installation:

```text
python -m unittest discover -s operations/protected-assets/accepted-20261023 -p test_worker_catalog_patch.py -v
node --check operations/protected-assets/accepted-20261023/worker.accepted.mjs
node --check operations/protected-assets/accepted-20261023/worker.before.mjs
python scripts/ci_public_repo_check.py
```

The Python tests use synthetic data. The preservation milestone also compares
the real before/additions/after files through the pure patcher and checks owned
rollback and byte identity. These checks do not contact Cloudflare or R2.
