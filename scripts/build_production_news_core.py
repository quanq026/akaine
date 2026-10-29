"""Keep authentic production routing after a fresh source rebuild of accepted V36."""
import copy
import json
from pathlib import Path
import re
import shutil
import zipfile

import build_prod_rebase_core as original

import build_client_support as shared

PROD_APK_SHA = original.PROD_APK_SHA
PROD_CORE_SHA = original.PROD_CORE_SHA
OUTPUT_SHA = '1097f9e03939ae0cd47fc958bbb95ed241f61cf1f44eb7c2ef71406ea3367bbe'
STAGING_NEWS_SHA = 'ce5210a472e437b3710075cc4a3a1253485ae1ba48bc2a17405caef067c5b1cf'
ROUTE_PINS = ((0x782a74, 37), (0x782ab0, 56), (0x782afc, 51), (0x1ba5ff0, 55))


def production_routes(prod, rebuilt):
    original.require(original.sha(prod) == PROD_CORE_SHA, 'Authentic production V9 core required')
    original.require(original.sha(rebuilt) == STAGING_NEWS_SHA, 'Fresh accepted V36 source core required')
    result = bytearray(rebuilt)
    rows, allowed = [], set()
    for address, size, before_sha, staging in original.ROUTES:
        source_at = original.file_offset(prod, address, size)
        output_at = original.file_offset(rebuilt, address, size)
        before = prod[source_at:source_at + size]
        original.require(original.sha(before) == before_sha and rebuilt[output_at:output_at + size] == staging,
                         'Exact original and staging route preimages required')
        result[output_at:output_at + size] = before
        allowed.update(range(output_at, output_at + size))
        rows.append(dict(runtime_VA=hex(address), output_offset=hex(output_at), bytes=size,
                         original_sha256=before_sha, staging_sha256=original.sha(staging)))
    changed = {i for i, (a, b) in enumerate(zip(rebuilt, result)) if a != b}
    original.require(len(result) == len(rebuilt) and len(changed) == 61 and changed <= allowed
                     and original.sha(result) == OUTPUT_SHA, 'Finite production routing restoration differs')
    for address, size in ROUTE_PINS:
        a, b = original.file_offset(prod, address, size), original.file_offset(result, address, size)
        original.require(prod[a:a + size] == result[b:b + size], 'Production routing layer differs')
    return bytes(result), dict(route_spans=rows, changed_bytes=61,
                              visible_and_encrypted_shared_routes_match_authentic_production=True,
                              all_other_fresh_V36_bytes_identical=True)


def cli_route_pins(text, prod):
    original.require(original.sha(prod) == PROD_CORE_SHA, 'Authentic production V9 core required')
    for index, (address, size) in enumerate(ROUTE_PINS):
        at = original.file_offset(prod, address, size)
        data = ','.join(hex(value) for value in prod[at:at + size])
        pattern = rf'(inline constexpr unsigned char CLI_ROUTE_{index}\[\] = \{{)[^}}]+(\}};)'
        text, count = re.subn(pattern, lambda match: match[1] + data + match[2], text)
        original.require(count == 1, 'Unique CLI routing pin required')
    return text
