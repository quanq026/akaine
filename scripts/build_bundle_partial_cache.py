"""Compile the reviewed public staging partial cache and patch the exact cap60 DEX."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import tempfile
import zlib

import build_cap60_dex as dexutils
import build_client_support as shared

SOURCE_SHA = 'ec16e94016acb1d602e9f01bd99beacd4a9c5b7eac9fa84825f078d6fabc6153'
OUTPUT_SHA = '20cdddd94102ef27c366379a5b11b3cb33cc8aa3e67cca502158373c62498761'
JAVA_SOURCES = (
    'AkaineBundlePartialCache.java', 'PartialCacheFixture.java',
    'compile-stubs/org/cocos2dx/lib/FileTaskHandler.java',
    'compile-stubs/org/cocos2dx/lib/Cocos2dxDownloader.java',
    'compile-stubs/cz/msebera/android/httpclient/HttpEntity.java',
)


def normalized_method(text):
    """Compare ordered effective catch handlers, independent of split DEX try regions."""
    lines = [line.split('#', 1)[0].strip() for line in text.splitlines()]
    labels, count = {}, 0
    for line in lines:
        if line.startswith(':'): labels[line] = count
        elif line and not line.startswith('.'): count += 1
    def label(match):
        return '@' + str(labels[match[0]]) if match[0] in labels else match[0]
    normalized, catches = [], [[] for unused in range(count)]
    for line in lines:
        if not line or line.startswith(':') or line.startswith('.line '): continue
        if line.startswith('.catch'):
            match = re.fullmatch(r'\.catch(all)?(?: (L[^ ]+;))? \{(:\w+) \.\. (:\w+)\} (:\w+)', line)
            if not match: raise ValueError('Unexpected DEX exception region')
            kind, start, end, target = match[2] or '*', labels[match[3]], labels[match[4]], labels[match[5]]
            if not 0 <= start <= end <= count: raise ValueError('Invalid DEX exception range')
            for index in range(start, end): catches[index].append((kind, target))
        else: normalized.append(re.sub(r':\w+', label, line))
    return normalized, catches


def equivalent_handler(left, right):
    pattern = re.compile(r'(?ms)^\.method ([^\n]+)\n.*?^\.end method$')
    a = {m[1]: normalized_method(m[0]) for m in pattern.finditer(left)}
    b = {m[1]: normalized_method(m[0]) for m in pattern.finditer(right)}
    if a != b: raise ValueError('Handler instructions or ordered exception coverage differ')
    headers = [pattern.sub('', value) for value in (left, right)]
    if sorted(dexutils.normalize_method(headers[0])) != sorted(dexutils.normalize_method(headers[1])):
        raise ValueError('Handler metadata differs')
    return {'method_count': len(a), 'ordered_exception_handlers_at_every_instruction_identical': True}


def compare(before, after, patcher):
    old = {p.relative_to(before).as_posix(): p.read_text('utf-8') for p in before.rglob('*.smali')}
    new = {p.relative_to(after).as_posix(): p.read_text('utf-8') for p in after.rglob('*.smali')}
    if len(old) != 725 or set(new) != set(old) | {patcher.HELPER}:
        raise ValueError('Partial-cache DEX class set differs')
    if {name for name in old if old[name] != new[name]} != {patcher.CALLER, patcher.HANDLER}:
        raise ValueError('Unrelated DEX class changed')
    if (new[patcher.CALLER].replace(patcher.SELECT, '') != old[patcher.CALLER]
            or patcher.unwrap(new[patcher.HANDLER]) != old[patcher.HANDLER]):
        raise ValueError('Unrelated downloader instructions changed')
    return {'existing_classes': 725, 'new_helper_classes': 1, 'existing_methods_changed': 4,
        'new_methods': 1, 'other_723_classes_unchanged': True, 'HTTP_guard_instructions_and_onSuccess_unchanged': True}
