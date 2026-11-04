"""Guarded 7.1 native build; activation is explicit and incomplete milestones stay incomplete."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PLAN_PATH = HERE / 'native-plan.json'
PRODUCTION_PLAN_PATH = HERE / 'production-native-plan.json'
ASSEMBLY_PATH = HERE / 'native_gates.S'
REPLAY_ASSEMBLY_PATH = HERE / 'replay_gates.S'
PACKAGES = {'staging': 'akai.arc.lmao.staging', 'production': 'akai.arc.lmao'}
PRODUCTION_ROUTES = {
    'login': 'https://auth.akai.id.vn/auth/login',
    'aggregate': 'https://arcapi-v3.akai.id.vn/compose/aggregate?calls=',
    'bundle': 'https://arcapi-v3.akai.id.vn/game/content_bundle',
    'shared': 'https://arcapi-v3.akai.id.vn/',
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def number(value):
    require(type(value) in (str, int), 'Integer or hexadecimal string required')
    return int(value, 0) if isinstance(value, str) else value


def plan_path(environment='staging'):
    require(isinstance(environment, str) and environment in PACKAGES, 'Exact 7.1 native environment required')
    return PRODUCTION_PLAN_PATH if environment == 'production' else PLAN_PATH


def identity(profile):
    environment = profile.get('environment')
    require(profile.get('application_version') == '7.1.0' and profile.get('version_code') == 1209907
            and isinstance(environment, str) and environment in PACKAGES and profile.get('package') == PACKAGES[environment],
            'Exact environment/package 7.1 native profile required')
    return environment


def load_plan(path=None, *, environment='staging'):
    require(isinstance(environment, str) and environment in PACKAGES, 'Exact 7.1 native environment required')
    selected = Path(path or plan_path(environment))
    base_raw = (selected if environment == 'staging' else PLAN_PATH).read_bytes()
    plan = json.loads(base_raw)
    require(plan.get('schema') == 'akaine.native-7.1.v1'
            and plan.get('application_version') == '7.1.0'
            and plan.get('version_code') == 1209907
            and plan.get('architecture') == 'arm64-v8a', 'Exact 7.1 ARM64 native plan required')
    require(plan.get('environment', 'staging') == 'staging'
            and plan.get('package', PACKAGES['staging']) == PACKAGES['staging'],
            'Staging base native plan identity differs')
    plan.update(environment='staging', package=PACKAGES['staging'])
    selected_raw = base_raw
    if environment == 'production':
        selected_raw = selected.read_bytes()
        overlay = json.loads(selected_raw)
        require(isinstance(overlay, dict) and set(overlay) == {'schema', 'application_version', 'version_code', 'architecture',
                'environment', 'package', 'base_plan_sha256', 'routes', 'shared_after_sha256',
                'route_section', 'output_sha256_by_features'}
                and overlay['schema'] == 'akaine.native-7.1-production-overlay.v1'
                and overlay['application_version'] == '7.1.0' and overlay['version_code'] == 1209907
                and overlay['architecture'] == 'arm64-v8a' and overlay['environment'] == environment
                and overlay['package'] == PACKAGES[environment], 'Exact production native overlay identity required')
        require(overlay['base_plan_sha256'] == sha(base_raw), 'Production base native plan identity differs')
        require(overlay['routes'] == PRODUCTION_ROUTES and isinstance(overlay['shared_after_sha256'], str)
                and re.fullmatch('[0-9a-f]{64}', overlay['shared_after_sha256']) is not None,
                'Production native route policy differs')
        section = overlay['route_section']
        require(isinstance(section, dict) and set(section) in ({'bytes'}, {'bytes', 'sha256'})
                and type(section['bytes']) is int and 0 < section['bytes'] <= 1024
                and ('sha256' not in section or isinstance(section['sha256'], str)
                     and re.fullmatch('[0-9a-f]{64}', section['sha256']) is not None),
                'Reviewed production route-section extent/hash required')
        outputs = overlay['output_sha256_by_features']
        require(isinstance(outputs, dict) and all(isinstance(key, str) and isinstance(value, str)
                and re.fullmatch('[0-9a-f]{64}', value) is not None for key, value in outputs.items())
                and (not outputs or 'sha256' in section), 'Production output controls require independent route sealing')
        plan.update(environment=environment, package=PACKAGES[environment], routes=overlay['routes'],
                    output_sha256_by_features=outputs, base_plan_sha256=sha(base_raw))
        plan['shared_api']['production_after_sha256'] = overlay['shared_after_sha256']
        plan['sections'] = [{**{k: v for k, v in row.items() if k not in ('bytes', 'sha256')}, **section}
                            if row['name'] == '.routes' else row for row in plan['sections']]
    plan['input_plan_sha256'] = sha(selected_raw)
    return plan


def headers(raw):
    require(raw[:6] == b'\x7fELF\x02\x01' and len(raw) >= 64
            and struct.unpack_from('<H', raw, 18)[0] == 183, 'Little-endian AArch64 ELF64 required')
    phoff, shoff = struct.unpack_from('<QQ', raw, 32)
    phsize, phcount, shsize, shcount, names = struct.unpack_from('<5H', raw, 54)
    require(phsize == 56 and shsize == 64 and names < shcount
            and phoff + phcount * phsize <= len(raw)
            and shoff + shcount * shsize <= len(raw), 'ELF table bounds differ')
    programs = [struct.unpack_from('<II6Q', raw, phoff + i * phsize) for i in range(phcount)]
    sections = [struct.unpack_from('<II4QII2Q', raw, shoff + i * shsize) for i in range(shcount)]
    names_row = sections[names]
    require(names_row[4] + names_row[5] <= len(raw), 'ELF section-name table exceeds source')
    strings = raw[names_row[4]:names_row[4] + names_row[5]]
    named = {}
    for i, row in enumerate(sections):
        require(row[0] < len(strings), 'ELF section name offset differs')
        end = strings.find(b'\0', row[0])
        require(end >= 0, 'Unterminated ELF section name')
        name = strings[row[0]:end].decode('ascii')
        require(name not in named, 'Duplicate ELF section name')
        named[name] = (i, row)
    return phoff, programs, shoff, sections, named


def file_offset(raw, va, size):
    require(type(va) is int and type(size) is int and va >= 0 and size > 0, 'Invalid native span')
    matches = [row[2] + va - row[3] for row in headers(raw)[1]
               if row[0] == 1 and row[3] <= va and va + size <= row[3] + row[5]]
    require(len(matches) == 1 and matches[0] + size <= len(raw), 'Unique complete file-backed native span required')
    return matches[0]


def read_virtual(raw, va, size):
    at = file_offset(raw, va, size)
    return raw[at:at + size]


def branch(source, destination, *, link=False):
    delta = destination - source
    require(source % 4 == destination % 4 == 0 and -(1 << 27) <= delta < (1 << 27),
            'Branch alignment/range differs')
    return struct.pack('<I', (0x94000000 if link else 0x14000000) | ((delta // 4) & 0x3ffffff))


def requested_features(profile, plan, runtime_bindings=None):
    environment = identity(profile)
    require(plan.get('environment') == environment and plan.get('package') == profile['package'],
            'Native profile/plan environment identity differs')
    require(profile.get('source_core_sha256') == plan['source_core_sha256'], 'Profile/source native identity differs')
    native = profile.get('native', {})
    enabled = native.get('enabled_features')
    require(isinstance(enabled, list) and enabled and len(set(enabled)) == len(enabled),
            'Explicit unique native feature activation list required')
    for feature in enabled:
        state = plan['feature_readiness'].get(feature)
        require(state and state.get('authored') is True and state.get('hook_activation_reviewed') is True,
                'Native feature is not implementation-reviewed: ' + str(feature))
        runtime_module = state.get('requires_runtime_module')
        if runtime_module:
            reviewed = (runtime_bindings or {}).get('reviewed_modules', [])
            require(runtime_module in reviewed, 'Native feature requires a reviewed runtime module: ' + runtime_module)
    return enabled


def routes(profile, plan):
    environment = identity(profile)
    require(plan.get('environment') == environment and plan.get('package') == profile['package'],
            'Native profile/plan environment identity differs')
    values = profile.get('routes')
    require(isinstance(values, dict) and values == plan['routes'], 'Native route policy differs')
    require(profile.get('native', {}).get('routes') == {**values, 'shared_base': values['shared']},
            'Nested native route policy differs')
    return values


def shared_api_encoding(profile, plan, raw):
    environment = identity(profile)
    values = routes(profile, plan)
    encoding = profile.get('native', {}).get('shared_base_encoding')
    require(isinstance(encoding, dict), 'Reviewed bounded shared API encoding required')
    before, after = bytes.fromhex(encoding.get('before', '')), bytes.fromhex(encoding.get('after', ''))
    shared = plan['shared_api']
    require(len(before) == len(after) == shared['bytes'] == encoding.get('extent_bytes')
            and before.hex() == shared['before'] and sha(after) == shared[environment + '_after_sha256']
            and number(encoding.get('virtual_address', -1)) == number(shared['va'])
            and number(encoding.get('file_offset', -1)) == file_offset(raw, number(shared['va']), shared['bytes'])
            and encoding.get('decoded') == values['shared'], 'Shared API extent/preimage/environment differs')
    return before, after


def fresh_output(path):
    path = Path(path).absolute()
    require(not path.exists(), 'Fresh native output directory required')
    require(not path.resolve().is_relative_to(REPO.resolve()), 'Native build output must remain outside the repository')
    for ancestor in (path, *path.parents):
        require(not ancestor.is_symlink() and not (ancestor.exists()
                and getattr(ancestor.stat(), 'st_file_attributes', 0) & 1024), 'Native output junction/symlink rejected')
    path.mkdir(parents=True)
    return path


def tool(llvm, name, arguments, output):
    executable = Path(llvm) / name
    require(executable.is_file(), 'Required NDK tool unavailable: ' + name)
    try:
        result = subprocess.run([str(executable), *map(str, arguments)], capture_output=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError('Native tool failed or timed out: ' + name) from None
    if result.returncode:
        (output / (name + '.failure.log')).write_bytes(result.stdout + result.stderr)
        raise RuntimeError('Native tool failed: ' + name + '; inspect the external build diagnostic')
    return result.stdout


def compile_gates(llvm, output, profile, plan, runtime_bindings=None):
    output = Path(output)
    stage_routes = routes(profile, plan)
    declarations = '\n'.join(f'route_{name}_uri: .asciz {json.dumps(stage_routes[name])}'
                             for name in ('login', 'aggregate', 'bundle')) + '\n'
    (output / 'route_strings.inc').write_text(declarations, encoding='utf-8', newline='\n')
    source_hash = sha(ASSEMBLY_PATH.read_bytes())
    replay_hash = sha(REPLAY_ASSEMBLY_PATH.read_bytes())
    expected_source = plan.get('assembly_sha256')
    if expected_source:
        require(source_hash == expected_source, 'Authored assembly source hash differs')
    require(replay_hash == plan['replay_assembly_sha256'], 'Replay assembly source hash differs')
    linked = {name: number(value) for name, value in plan['link_symbols'].items()}
    linked['owned_mailbox'] = number(plan['layout']['owned_mailbox_va'])
    linked['toggle_mailbox'] = number(plan['layout']['toggle_mailbox_va'])
    for name, value in (runtime_bindings or {}).get('symbols', {}).items():
        require(name in linked and number(value) == linked[name], 'Reviewed native symbol differs: ' + name)
    base = number(plan['layout']['insert_file_offset'])
    starts = {section['name']: base + number(section['offset']) for section in plan['sections']}
    tool(llvm, 'clang.exe', ['--target=aarch64-linux-android24', '-I', output, '-c', ASSEMBLY_PATH,
                            '-o', output / 'gates.o'], output)
    tool(llvm, 'clang.exe', ['--target=aarch64-linux-android24', '-c', REPLAY_ASSEMBLY_PATH,
                            '-o', output / 'replay.o'], output)
    tool(llvm, 'ld.lld.exe', ['--entry=route_login_gate',
                            *[f'--section-start={name}={va:#x}' for name, va in starts.items()],
                            *[f'--defsym={name}={value:#x}' for name, value in linked.items()],
                            output / 'gates.o', output / 'replay.o', '-o', output / 'gates.elf'], output)
    symbols = {}
    raw_symbols = tool(llvm, 'llvm-nm.exe', ['--defined-only', '--format=posix', output / 'gates.elf'], output).decode()
    for line in raw_symbols.splitlines():
        match = re.fullmatch(r'(\S+)\s+\S\s+([0-9a-fA-F]+)(?:\s+[0-9a-fA-F]+)?', line)
        if match: symbols[match[1]] = int(match[2], 16)
    sections = []
    for row in plan['sections']:
        name = row['name']; target = output / (name.removeprefix('.') + '.bin')
        tool(llvm, 'llvm-objcopy.exe', ['-O', 'binary', '--only-section=' + name, output / 'gates.elf', target], output)
        data = target.read_bytes()
        require(0 < len(data) <= row['maximum_bytes'], 'Authored section exceeds declared region: ' + name)
        if 'sha256' in row:
            require(sha(data) == row['sha256'] and len(data) == row['bytes'], 'Authored compiled section differs: ' + name)
        sections.append({'name': name, 'va': starts[name], 'bytes': data})
    require(sha(ASSEMBLY_PATH.read_bytes()) == source_hash, 'Authored assembly changed during compilation')
    require(sha(REPLAY_ASSEMBLY_PATH.read_bytes()) == replay_hash, 'Replay assembly changed during compilation')
    return sections, symbols, source_hash


def extend_elf(stock, sections, layout):
    phoff, programs, shoff, section_rows, named = headers(stock)
    insert = number(layout['insert_file_offset']); space = number(layout['insert_size'])
    require(space > 0 and space % 0x4000 == 0 and insert < shoff, 'Native extension placement differs')
    require(insert + space <= number(layout['next_load_va']), 'Executable extension overlaps following virtual segment')
    require(named['.bss'][1][3] == number(layout['bss_va'])
            and named['.bss'][1][5] == number(layout['bss_bytes']), 'Original BSS shape differs')
    mailbox_end = number(layout['toggle_mailbox_va']) + number(layout['mailbox_total_bytes'])
    require(number(layout['toggle_mailbox_va']) == number(layout['bss_va']) + number(layout['bss_bytes'])
            and number(layout['owned_mailbox_va']) == number(layout['toggle_mailbox_va']) + 128,
            'Mailbox must extend the exact BSS tail without overlap')
    insertion = bytearray(space); occupied = set(); executable_end = insert
    for section in sections:
        begin, data = section['va'], section['bytes']; end = begin + len(data)
        require(insert <= begin < end <= insert + space, 'Compiled native section is outside extension')
        span = set(range(begin, end)); require(not occupied.intersection(span), 'Compiled native sections overlap')
        occupied.update(span); insertion[begin - insert:end - insert] = data; executable_end = max(executable_end, end)
    require(occupied, 'An empty executable extension is not a native build')
    result = bytearray(stock[:insert] + insertion + stock[insert:]); edits = []; rx_count = rw_count = 0
    for index, row in enumerate(programs):
        at = phoff + index * 56
        if row[2] >= insert and row[5]:
            struct.pack_into('<Q', result, at + 8, row[2] + space)
            edits.append({'offset': at + 8, 'bytes': 8, 'reason': 'Move original file-backed program data'})
        if row[0] == 1 and row[1] == 5 and row[3] == number(layout['rx_va']):
            require(row[2] == 0 and row[5] == row[6] == number(layout['rx_bytes']) == insert,
                    'Original executable segment differs')
            struct.pack_into('<QQ', result, at + 32, executable_end, executable_end); rx_count += 1
            edits.append({'offset': at + 32, 'bytes': 16, 'reason': 'Map only compiled executable extension'})
        if row[0] == 1 and row[3] == number(layout['rw_va']):
            require(row[6] == number(layout['rw_memory_bytes']) and row[3] + row[6] == number(layout['toggle_mailbox_va']),
                    'Original writable segment tail differs')
            struct.pack_into('<Q', result, at + 40, mailbox_end - row[3]); rw_count += 1
            edits.append({'offset': at + 40, 'bytes': 8, 'reason': 'Append zero-initialized runtime mailboxes'})
    require(rx_count == rw_count == 1, 'Unique executable and final writable segments required')
    struct.pack_into('<Q', result, 40, shoff + space)
    edits.append({'offset': 40, 'bytes': 8, 'reason': 'Move section table file offset'})
    for index, row in enumerate(section_rows):
        at = shoff + space + index * 64
        if row[4] >= insert:
            struct.pack_into('<Q', result, at + 24, row[4] + space)
            edits.append({'offset': at + 24, 'bytes': 8, 'reason': 'Move section data file offset'})
        if row[1] == 8 and row[3] == number(layout['bss_va']):
            struct.pack_into('<Q', result, at + 32, mailbox_end - row[3])
            edits.append({'offset': at + 32, 'bytes': 8, 'reason': 'Include appended mailbox in BSS section'})
    return result, edits


def apply_operations(result, stock, operations, symbols):
    occupied = set(); changes = []
    for row in operations:
        va = number(row['va']); before = bytes.fromhex(row['before'])
        if 'pointer_symbol' in row:
            require(len(before) == 8 and 'branch_symbol' not in row and 'after' not in row,
                    'Relocation addend requires one exact pointer operation')
            after = struct.pack('<Q', symbols[row['pointer_symbol']])
        else:
            after = (branch(va, symbols[row['branch_symbol']], link=row.get('link', False))
                     if 'branch_symbol' in row else bytes.fromhex(row['after']))
        require(before and len(before) == len(after), 'Native operation size differs: ' + row['label'])
        source = file_offset(stock, va, len(before)); destination = file_offset(result, va, len(before))
        require(stock[source:source + len(before)] == before and result[destination:destination + len(before)] == before,
                'Native preimage differs: ' + row['label'])
        span = set(range(destination, destination + len(after)))
        require(not occupied.intersection(span), 'Native operations overlap')
        occupied.update(span); result[destination:destination + len(after)] = after
        changes.append({'label': row['label'], 'va': hex(va), 'offset': destination,
                        'before': before.hex(), 'after': after.hex()})
    return changes


def verify_preservation(stock, result, layout, metadata, operations):
    insert = number(layout['insert_file_offset']); space = number(layout['insert_size'])
    require(len(result) == len(stock) + space, 'Native output length differs')
    normalized = bytearray(result[:insert] + result[insert + space:])
    for edit in metadata:
        at, size = edit['offset'], edit['bytes']
        old_at = at - space if at >= insert + space else at
        normalized[old_at:old_at + size] = stock[old_at:old_at + size]
    for row in operations:
        at = file_offset(stock, number(row['va']), len(bytes.fromhex(row['before'])))
        normalized[at:at + len(bytes.fromhex(row['before']))] = bytes.fromhex(row['before'])
    require(bytes(normalized) == stock, 'Undeclared original native byte changed')
    old_sections, new_sections = headers(stock)[4], headers(result)[4]
    evidence = {}
    for name in ('.eh_frame', '.eh_frame_hdr'):
        a, b = old_sections[name][1], new_sections[name][1]
        before, after = stock[a[4]:a[4] + a[5]], result[b[4]:b[4] + b[5]]
        require(before == after and a[3] == b[3] and a[5] == b[5], 'Original unwind section changed: ' + name)
        evidence[name] = sha(before)
    return evidence


def build(stock_core, llvm, output, profile, runtime_bindings=None):
    engine_hash = sha(Path(__file__).read_bytes())
    replay_hash = sha(REPLAY_ASSEMBLY_PATH.read_bytes())
    environment = identity(profile)
    selected_plan = plan_path(environment)
    plan = load_plan(environment=environment); plan_hash = plan['input_plan_sha256']
    base_plan_hash = plan.get('base_plan_sha256', plan_hash)
    enabled = requested_features(profile, plan, runtime_bindings)
    raw = bytes(stock_core) if isinstance(stock_core, (bytes, bytearray)) else Path(stock_core).read_bytes()
    require(sha(raw) == plan['source_core_sha256'] and len(raw) == plan['source_core_bytes'],
            'Exact unmodified APKPure 7.1 ARM64 core required')
    before, after = shared_api_encoding(profile, plan, raw)
    shared = plan['shared_api']
    output = fresh_output(output)
    sections, symbols, source_hash = compile_gates(llvm, output, profile, plan, runtime_bindings)
    result, metadata = extend_elf(raw, sections, plan['layout'])
    operations = [row for row in plan['branch_operations'] + plan.get('direct_operations', []) if row['feature'] in enabled]
    operations.append({'label': 'shared-' + environment + '-api-base', 'va': shared['va'], 'before': before.hex(), 'after': after.hex()})
    changes = apply_operations(result, raw, operations, symbols)
    unwind = verify_preservation(raw, result, plan['layout'], metadata, operations)
    key = '+'.join(sorted(enabled))
    expected_output = plan.get('output_sha256_by_features', {}).get(key)
    if expected_output:
        require(sha(result) == expected_output, 'Reviewed native output identity differs')
    require(sha(selected_plan.read_bytes()) == plan_hash and sha(PLAN_PATH.read_bytes()) == base_plan_hash
            and sha(ASSEMBLY_PATH.read_bytes()) == source_hash
            and sha(REPLAY_ASSEMBLY_PATH.read_bytes()) == replay_hash
            and sha(Path(__file__).read_bytes()) == engine_hash,
            'Native authored input changed during build')
    target = output / 'libcocos2dcpp.so'; target.write_bytes(result)
    receipt = {'schema': 'akaine.native-7.1-build.v1', 'status': 'INTERNAL_' + environment.upper() + '_NATIVE_MILESTONE_STATIC_BUILD',
               'application_version': '7.1.0', 'environment': environment, 'package': profile['package'],
               'source_core_sha256': sha(raw), 'native_core_sha256': sha(result), 'native_bytes': len(result),
               'native_plan_sha256': plan_hash, 'assembly_sha256': source_hash, 'replay_assembly_sha256': replay_hash,
               'engine_sha256': engine_hash, 'enabled_features': enabled,
               'dormant_compiled_features': [f for f in plan['feature_readiness'] if f not in enabled],
               'compiled_sections': [{'name': s['name'], 'va': hex(s['va']), 'bytes': len(s['bytes']), 'sha256': sha(s['bytes'])} for s in sections],
               'symbols': {k: hex(v) for k, v in symbols.items()}, 'mailboxes': {k: plan['layout'][k] for k in ('toggle_mailbox_va', 'owned_mailbox_va')},
               'authored_addresses': {old: hex(symbols[symbol]) for old, symbol in plan.get('authored_address_symbols', {}).items()},
               'operations': changes, 'elf_metadata_changes': metadata, 'unwind_sha256': unwind,
               'undeclared_original_native_bytes_unchanged': True, 'complete_v36_equivalent': False,
               'output_identity_sealed': bool(expected_output) and bool(plan.get('assembly_sha256')) and all('sha256' in r for r in plan['sections']),
               'runtime_accepted': False, 'device_or_server_actions': False}
    if environment == 'production':
        receipt['base_native_plan_sha256'] = base_plan_hash
    (output / 'BUILD_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return target, receipt
