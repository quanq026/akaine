# Whole-archive APK baseline comparison

Every file member was streamed and SHA256/ZIPCRC checked in three pinned APKs. Signature metadata was excluded only from the content comparison. No member was extracted. Duplicate, unsafe, encrypted and symlink entries were rejected.

| Logical input | Whole APK SHA256 | Compared members | APK assets |
|---|---|---:|---:|
| authentic_prod_v9_20261022 | `f14c5ab0871440dec7ecf2107d32d6e2cad745abc82047d03b49db9dbac3f545` | 5418 | 4996 / 1183742598 bytes |
| latest_staging_v33_20261025 | `3ca59cd27b1fdd0033194a56827461bcb770685841f55afdb9d0920ab560b08d` | 5418 | 4996 / 1183742598 bytes |
| historical_builder_v18_base | `4d80a24b55bf54779454a294fc13397be92dddcbeb97818ed2b9c76097b842db` | 5418 | 4996 / 1183742598 bytes |

## Content differences

| From | To | Unchanged | Changed | Added | Removed |
|---|---|---:|---:|---:|---:|
| authentic_prod_v9_20261022 | latest_staging_v33_20261025 | 5414 | 4 | 0 | 0 |
| historical_builder_v18_base | authentic_prod_v9_20261022 | 5415 | 3 | 0 | 0 |
| historical_builder_v18_base | latest_staging_v33_20261025 | 5414 | 4 | 0 | 0 |

## Changes outside the five declared payloads

- authentic_prod_v9_20261022 to latest_staging_v33_20261025: **none**.
- historical_builder_v18_base to authentic_prod_v9_20261022: **none**.
- historical_builder_v18_base to latest_staging_v33_20261025: **none**.

The five declared payloads are the core, monitor, loader, classes3.dex and classes4.dex. Exact per-member before/after hashes are in the JSON.

## Resource and omission conclusion

All three APK asset rows match the expected4,996-file/1,183,742,598-byte asset manifest, canonical digest `eccacb215213b17e1be6df318bbe716b0154942742c4e42c5e52e693ded8c5ab`. The private asset list and input map were not copied into this repository.

Production members absent from latest staging: **0**. Production members absent from the historical builder base: **0**. Existing production resource inheritance must be judged from these complete path/hash sets, not from matching a few libraries.

This gate establishes byte identity and archive completeness. It does not prove runtime compatibility, behavior parity, media quality after a separate bundle update, or final signature acceptance. No APK, asset, source, device or service was modified.
