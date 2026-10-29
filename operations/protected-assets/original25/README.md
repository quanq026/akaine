# Original25 staging audio route

`patch_original25.py` patches the exact accepted Worker SHA
`54748325983a7c1bfc7e1b3486446a2d279f4782f68ce54218aff3ebed9f7402`.
Its output SHA is
`f617e04a99dae6c4654d1794591840209638a502e85ba8b67356121199bf13e2`.

The new signed path is `/protected/songs/original25/<song>/<file>`.
HMAC validation still binds the entire path, song, filename and expiry.
Exactly 50 original audio objects use the new private candidate namespace.
Other files use their existing `private/songs/` objects. Existing signed paths
continue using their old storage keys, so production URLs retain their behavior.
No chart object, encrypted identity or allowlist changes are included.

The staging server selects the new signed prefix and updates the corresponding
50 plaintext audio MD5 values in both metadata files. Files lists and chart hashes
stay unchanged. Do not update only the bundle and leave these audio hashes stale.

## Private storage guard

The existing CDN route covers only `private/songs/*`. The new candidate prefix
therefore needs its own Worker route:

```text
cdn.akai.id.vn/private/candidates/aurora-full-base-20261025-original/*
    -> akaine-protected-assets
```

This exact route was added after a direct Range request demonstrated public
access to a new raw audio object. The same URL now returns 404. The Worker rejects
the storage URL; its authenticated handler reads R2 internally. No chart or
credential was exposed by this namespace. Existing routes and bindings remain
unchanged. Keep this denial route while any objects remain under that prefix.

## Verification

```text
python -m unittest discover -s operations/protected-assets/original25 -p test_patch_original25.py
```

The check builds from the pinned accepted source in a temporary directory, then
runs Node against all 50 mappings. It exercises old paths, compact and ordinary
signatures, signature transplantation denial, unchanged storage fallbacks and
unsigned storage denial. The patcher also rejects a changed source or incomplete
mapping. Tests use a synthetic signing secret.

The deployed signed URLs and all 50 original audio bodies were independently
checked by full GET/hash. These transport checks do not establish native codec
compatibility or gameplay acceptance. See the online bundle receipt for those
separate results.
