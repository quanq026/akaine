"""Generate exact-core runtime guards; address discovery is not ABI acceptance."""
from __future__ import annotations

from bisect import bisect_right
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import struct

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
spec = importlib.util.spec_from_file_location('port71_pin_native', HERE / 'native.py')
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)
HEX = re.compile(r'\b0x[0-9a-fA-F]+\b')
STOCK_SHA = '849a7b1418ba389c007b0b2793510eb8e163b1268e8734b561a83b6c11c0773c'
LAYOUT_SHA = '1559e79fe6d387c5e72b9dc00d618f969f8e85be03dc8e4f0f0ee481eea9e89b'
RELOCATION_FIELDS = {'PIN_toggle_operation_1': 0x1a88fe8, 'PIN_toggle_operation_2': 0x1add8a0}
TARGET_ABILITY_TYPES = ((0x1b27b70, '33CharacterAbilityIlithTrickOrTreat'),
                        (0x1b96220, '37CharacterAbilityStreamPaletteLinkPlay'))
TARGET_SETTINGS_CALLBACKS = (
    ('setter', 0x1aa3d08, 0x11041e8, 'replay_setting_setter_gate',
     'NSt6__ndk110__function6__funcIZN15SettingsLayerV221createMainContentBaseEbbE4$_27NS_9allocatorIS3_EEFviPNS_6vectorINS_12basic_stringIcNS_11char_traitsIcEENS4_IcEEEENS4_ISB_EEEEEEE'),
    ('getter', 0x1b06158, 0x19e0458, 'replay_setting_getter_gate',
     'NSt6__ndk110__function6__funcIZN15SettingsLayerV221createMainContentBaseEbbE4$_28NS_9allocatorIS3_EEFivEEE'),
)
SETTINGS_FUNCTIONS = (
    (0x11041e8, 472, '5e9fa39807f7dad0143c0600c3e10b584e5bd208ae2f2bffb03ff6049f7b01e9'),
    (0x19e0458, 32, '55ef5105b835dc8a4c9b29fa540f736789d2b4e23e965f127fb77318a3abc8e2'),
    (0x9be13c, 340, 'f87b183ade09c2ed7be29c35317171ad413dcf93844caddc483a8b28a3a83217'),
    (0x8eeb6c, 548, '0f9865e3966c5feb8f78403fa8d1b39e9e74faa5b882521ff4a41fd32a19f129'),
    (0x15d5a08, 76, 'f1843a080ac3458327d0a70d3058887657625ca4d85bd153dc95bd3abf755039'),
)
TARGET_CLI_CALLBACKS = (
    ('first_run_speed', 0x1b0e628, 0x14d5dd8, 340,
     '5642f65894a31a44e4d08e05500ab8bb701652b8236eb5b8e0389a4bc97c14fd',
     'NSt6__ndk110__function6__funcIZN15SongSelectScene12songSelectedE18SongDifficultyPair8GameModeP7MapStepbbE5$_106NS_9allocatorIS7_EEFviEEE'),
    ('speed_release', 0x1b5d288, 0x153f61c, 16,
     'f5102cca40aa9d0668a48a77eb306e56e27c7d36d6de445d6a47bedba0263325',
     'NSt6__ndk110__function6__funcIZN21HighspeedSettingLayer4initEbiE3$_5NS_9allocatorIS3_EEFvPN7cocos2d3RefENS6_2ui6Widget14TouchEventTypeEEEE'),
    ('skill_seal', 0x1b3dc40, 0x14e0058, 96,
     'e9a679f1cadc0eaaebb33ace1b2cb694202d2813958902a0395932e777375e9d',
     'NSt6__ndk110__function6__funcIZN24PartnerSelectDialogASide4initEvE4$_14NS_9allocatorIS3_EEFvPN7cocos2d3RefEEEE'),
    ('advanced_guide_skip', 0x1afe870, 0x1986270, 68,
     'b562340b12641020a8b6b9ebe5994efde9dffd53673447f3d91033242ef75720',
     'NSt6__ndk110__function6__funcIZN15SongSelectScene34showAdvancedTutorialDialogIfNeededEP4Song15DifficultyClassP7MapStep8GameModeE5$_137NS_9allocatorIS9_EEFvP11DialogLayerEEE'),
)
PACK_TUTORIAL_FUNCTIONS = (
    (0xad0d78, 796, '08bc2805f0f12e835a44e7b67f7fa04d16fe8054af0f31e718982527b08d58df'),
    (0x1a72018, 512, '7556e5a92eadb303dc581d7e60dec15ed677a9eefbef767761621f27a488770e'),
    (0x1357a7c, 792, 'e4ff5e5f704ab6f81841ba227151bdbf7b720c757fbe7db67f40d841e5342469'),
    (0xd3dc88, 420, '51bd33e995154d598454ec4628eb930a65765486bcd9d89ed6fa46cd0301d7dc'),
    (0x85ef60, 336, '81757271a4b023bcfaebc00b9dd35496903184c63a9ca7f9c167fdb80f46bfff'),
    (0x10c2440, 352, '3a716bb8c4db2047ab39b27cf6f65f6a55118e42fa0a805dcc2bc35fb774f130'),
    (0x1a2bc70, 96, '84f8aa0413cd82ee3f5d0b0a770ededf72a57714fb7fbb69c6dd51711770b697'),
    (0x16c6bb8, 388, '082ee6f6a2d7b12c9215b8288ac28d09f21084e9037866fa275f696f92cd473d'),
    (0x1113d68, 8, '5103ba3de080c52a046485f800433848701faa49ab8f60241a80987ca249d7ac'),
    (0x15c8178, 888, 'e7e402bc1b6a81672f4caca39e1a96ec14e61059c1ef86452792378e4a83f122'),
    (0x7b03f4, 1032, '02a125e67f13bfb1cdd96e153cd54dad84b5503bb3d78fa084ef8d7f68ec61ef'),
    (0x7bad64, 472, '0127b16b291eb8b41725b195bb31eafb20ad0c32b1c4a451fd0e9e46c7b90c05'),
    (0x1377e48, 22184, '86a10be45b3c3c511d904008d714fdde6b020e0aae57bdb7faeb2b5d97fa6813'),
)
PACK_TUTORIAL_CALLBACK_RTTI = (
    'NSt6__ndk110__function6__funcIZZN18TutorialGuideLayer4initENS_6vectorINS_12basic_stringIc'
    'NS_11char_traitsIcEENS_9allocatorIcEEEENS7_IS9_EEEENS_8functionIFvPS2_EEEENK3$_1clEfEUlPN7cocos2d3Ref'
    'ENSH_2ui6Widget14TouchEventTypeEE_NS7_ISN_EEFvSJ_SM_EEE')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def number(value):
    require(type(value) in (int, str), 'Exact integer or hexadecimal value required')
    return int(value, 0) if isinstance(value, str) else value


def safe_path(value):
    path = PurePosixPath(value)
    require(path.as_posix() == value and not path.is_absolute() and '..' not in path.parts
            and '\\' not in value and ':' not in value and value.startswith('semantic/')
            and value.endswith('.h'), 'Unsafe generated header path')
    return path


def unlinked(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() or p.exists() and getattr(p.stat(), 'st_file_attributes', 0) & 1024
                    for p in (path, *path.parents)), 'Links and junctions are not allowed')
    return path.resolve()


def mask_pin_rows(text):
    for pattern, replacement in (
        (r'\{(0x[0-9a-fA-F]+),([A-Za-z_][A-Za-z0-9_]*),sizeof\(\2\)\}',
         lambda m: '{@@ADDRESS_' + m[2] + '@@,' + m[2] + ',sizeof(' + m[2] + ')}'),
        (r'\{(0x[0-9a-fA-F]+),sizeof\(([A-Za-z_][A-Za-z0-9_]*)\),\2\}',
         lambda m: '{@@ADDRESS_' + m[2] + '@@,sizeof(' + m[2] + '),' + m[2] + '}'),
    ):
        text = re.sub(pattern, replacement, text)
    return text


def function_ranges(raw):
    """Exact target encoding: sorted data-relative table and pcrel sdata4 FDEs."""
    sections = native.headers(raw)[4]
    row = sections['.eh_frame_hdr'][1]
    at, size, base = row[4], row[5], row[3]
    require(raw[at:at + 4] == b'\x01\x1b\x03\x3b' and size >= 12, 'Unwind encoding differs')
    count = struct.unpack_from('<I', raw, at + 8)[0]
    require(12 + count * 8 == size and count > 0, 'Unwind table bounds differ')
    result = {}
    for index in range(count):
        start_delta, fde_delta = struct.unpack_from('<ii', raw, at + 12 + index * 8)
        start, fde = base + start_delta, base + fde_delta
        offset = native.file_offset(raw, fde, 16)
        length, _, delta, span = struct.unpack_from('<IIiI', raw, offset)
        require(12 <= length < 2_000_000 and start == fde + 8 + delta and 0 < span < 2_000_000
                and start not in result, 'FDE range differs')
        native.file_offset(raw, fde, length + 4)
        native.file_offset(raw, start, span)
        result[start] = span
    require(list(result) == sorted(result), 'Unwind function table is not ordered')
    return result


def relocation_records(raw):
    result = {}
    for _, row in native.headers(raw)[4].values():
        if row[1] != 4:
            continue
        require(row[9] == 24 and row[5] % 24 == 0 and row[4] + row[5] <= len(raw), 'RELA bounds differ')
        for offset in range(row[4], row[4] + row[5], 24):
            target, info, addend = struct.unpack_from('<QQq', raw, offset)
            require(target not in result, 'Duplicate relocation destination')
            result[target] = {'offset': offset, 'type': info & 0xffffffff, 'addend': addend}
    return result


def target_metadata(raw, receipt):
    _, programs, _, _, sections = native.headers(raw)
    mailboxes = [number(receipt['mailboxes'][name]) for name in ('toggle_mailbox_va', 'owned_mailbox_va')]
    writable = [(index, row) for index, row in enumerate(programs) if row[0] == 1 and row[1] & 2
                and all(row[3] + row[5] <= address and address + 128 <= row[3] + row[6] for address in mailboxes)]
    require(len(writable) == 1 and mailboxes[1] == mailboxes[0] + 128, 'Unique appended mailbox segment required')
    rw_index, rw = writable[0]
    executable = [(index, row) for index, row in enumerate(programs) if row[0] == 1 and row[1] & 1]
    require(len(executable) == 1 and executable[0][1][3] == 0, 'Unique VA-zero RX segment required')
    rx_index, rx = executable[0]
    notes = [row for row in programs if row[0] == 4]
    require(len(notes) == 1, 'Unique note segment required')
    note = notes[0]
    build = sections['.note.gnu.build-id'][1]
    require(build[1] == 7 and build[5] == 36, 'Exact GNU build-id note required')
    data = raw[build[4]:build[4] + build[5]]
    require(data[:16] == struct.pack('<III', 4, 20, 3) + b'GNU\0', 'Twenty-byte GNU build-id required')
    require(sha(data[16:]) == '5e8149731f9c6edec72bc3cbd3cda5f299f940cc988791662f7005ace9f1c840',
            'Original APKPure7.1 build-id differs')
    phoff = struct.unpack_from('<Q', raw, 32)[0]
    constants = {'TOGGLE_MAILBOX_VA': mailboxes[0], 'TOGGLE_RW_SEGMENT_VA': rw[3],
                 'TOGGLE_RW_FILE_SIZE': rw[5], 'TOGGLE_RW_MEMORY_SIZE': rw[6], 'OWNED_RX_END': rx[3] + rx[6]}
    return {'constants': constants, 'owned_constants': {'OWNED_RW_SEGMENT_VA': rw[3],
            'OWNED_RW_FILE_SIZE': rw[5], 'OWNED_RW_MEMORY_SIZE': rw[6]},
            'build_id_offset': build[4] + 16, 'rx_size_offset': phoff + rx_index * 56 + 32,
            'rw_memory_offset': phoff + rw_index * 56 + 40, 'note_va': note[3], 'note_bytes': note[5]}


def target_ability_rows(raw, relocations):
    def relative(address):
        row = relocations.get(address)
        require(row and row['type'] == 1027, 'Ability RTTI/getter must use a relative relocation')
        return row['addend']
    for table, name in TARGET_ABILITY_TYPES:
        typeinfo = relative(table - 8)
        string = relative(typeinfo + 8)
        require(native.read_virtual(raw, string, len(name) + 1) == name.encode() + b'\0', 'Target ability RTTI differs')
        require(relative(table + 0x58) == 0x11bc238, 'Target ability base getter differs')
    require(sha(native.read_virtual(raw, 0x11bc238, 52)) == '51251be5725a9c9b691827b910d1c5e5ff70d05dd97aa23f7d1df6a4063fe083',
            'Shared target ability getter bytes differ')
    return ''.join('    {' + hex(table) + ',' + json.dumps(name) + '},\n' for table, name in TARGET_ABILITY_TYPES)


def target_settings_rows(raw, relocations, functions, receipt):
    for address, size, expected in SETTINGS_FUNCTIONS:
        require(functions.get(address) == size and sha(native.read_virtual(raw, address, size)) == expected,
                'Settings native function preimage/FDE differs')

    def relative(address):
        row = relocations.get(address)
        require(row and row['type'] == 1027, 'Settings callback must use a relative relocation')
        return row['addend']

    require(relative(0x1ac3020) == 0x8eeb6c and relative(0x1ac3050) == 0x9be13c,
            'Settings storage virtual methods differ')
    rows = []
    for role, table, original, symbol, name in TARGET_SETTINGS_CALLBACKS:
        typeinfo = relative(table - 8)
        string = relative(typeinfo + 8)
        require(native.read_virtual(raw, string, len(name) + 1) == name.encode() + b'\0',
                'Settings callback RTTI owner/signature differs')
        expected = number(receipt['symbols'][symbol]) if 'replay' in receipt['enabled_features'] else original
        invoke = relative(table + 0x30)
        require(invoke == expected, 'Settings callback invoke target differs')
        rows.append({'role': role, 'vtable': hex(table), 'invoke': hex(invoke),
                     'signature_owner_verified': True, 'runtime_lifetime_verified': False})
    return rows


def target_cli_rows(raw, relocations, functions):
    def relative(address):
        row = relocations.get(address)
        require(row and row['type'] == 1027, 'CLI callback must use a relative relocation')
        return row['addend']
    rows = []
    for role, table, invoke, size, expected, name in TARGET_CLI_CALLBACKS:
        typeinfo = relative(table - 8)
        string = relative(typeinfo + 8)
        require(native.read_virtual(raw, string, len(name) + 1) == name.encode() + b'\0'
                and relative(table + 0x30) == invoke, 'CLI callback owner/invoke differs: ' + role)
        require(functions.get(invoke) == size and sha(native.read_virtual(raw, invoke, size)) == expected,
                'CLI callback preimage/FDE differs: ' + role)
        rows.append({'role': role, 'vtable': hex(table), 'invoke': hex(invoke),
                     'signature_owner_verified': True, 'runtime_lifetime_verified': False})
    return rows


def pack_tutorial_header(raw, relocations, functions):
    for table, name in ((0x1abcc10, '18TutorialGuideLayer'), (0x1b994e8, PACK_TUTORIAL_CALLBACK_RTTI),
                        (0x1af6790, '19PartnerSelectDialog'), (0x1b324a0, '24PartnerSelectDialogASide'),
                        (0x1b4f128, '24PartnerSelectDialogBSide')):
        info = relocations.get(table - 8)
        require(info and info['type'] == 1027, 'Pack tutorial RTTI relocation differs')
        string = relocations.get(info['addend'] + 8)
        require(string and string['type'] == 1027
                and native.read_virtual(raw, string['addend'], len(name) + 1) == name.encode() + b'\0',
                'Pack tutorial RTTI owner/signature differs')
    invoke = relocations.get(0x1b994e8 + 0x30)
    require(invoke and invoke['type'] == 1027 and invoke['addend'] == 0x85ef60,
            'Pack tutorial callback invoke differs')
    init = relocations.get(0x1b324a0 + 0x4d8)
    require(init and init['type'] == 1027 and init['addend'] == 0x1377e48,
            'Partner tutorial owner init differs')
    arrays, rows = [], []
    for index, (address, size, expected) in enumerate(PACK_TUTORIAL_FUNCTIONS):
        data = native.read_virtual(raw, address, size)
        require(functions.get(address) == size and sha(data) == expected, 'Pack tutorial preimage/FDE differs')
        name = 'CLI_PACK_TUTORIAL_' + str(index)
        arrays.append('inline constexpr unsigned char ' + name + '[] = {' + ','.join(hex(b) for b in data) + '};\n')
        rows.append('{' + hex(address) + ',' + name + ',sizeof(' + name + ')},\n')
    return ''.join(arrays) + 'inline constexpr CliPin CLI_PACK_TUTORIAL_PINS[] = {\n' + ''.join(rows) + '};\n'


def receipt_environment(receipt):
    environment = receipt.get('environment')
    require(isinstance(environment, str) and environment in native.PACKAGES
            and receipt.get('package') == native.PACKAGES[environment], 'Native receipt environment/package identity differs')
    return environment


def validate_inputs(core, receipt, layout_raw):
    require(sha(layout_raw) == LAYOUT_SHA, 'Committed baseline pin layout differs')
    receipt_environment(receipt)
    require(receipt.get('schema') == 'akaine.native-7.1-build.v1'
            and receipt.get('source_core_sha256') == STOCK_SHA
            and receipt.get('application_version') == '7.1.0'
            and receipt.get('native_core_sha256') == sha(core) and receipt.get('native_bytes') == len(core)
            and receipt.get('undeclared_original_native_bytes_unchanged') is True, 'Native receipt/core identity differs')
    require(receipt.get('compiled_sections'), 'Authored section inventory required')
    for section in receipt['compiled_sections']:
        require(sha(native.read_virtual(core, number(section['va']), section['bytes'])) == section['sha256'],
                'Authored section bytes differ')
    for name, expected in receipt.get('unwind_sha256', {}).items():
        require(name in ('.eh_frame', '.eh_frame_hdr'), 'Unexpected unwind section')
        row = native.headers(core)[4][name][1]
        require(sha(core[row[4]:row[4] + row[5]]) == expected, 'Unwind identity differs')
    layout = json.loads(layout_raw)
    headers = layout['headers'] + [layout['owned_header']]
    require(len(headers) == 27 and sum(len(h['pins']) for h in headers) == 506, 'Complete506-pin inventory required')
    require(len({str(safe_path(h['path'])) for h in headers}) == 27, 'Duplicate header path')
    return headers


def reviewed_overrides(raw, receipt, mapping, all_pins, functions):
    """Retarget integrity guards only; this does not accept callable ABI bindings."""
    environment = receipt_environment(receipt)
    routes = native.load_plan(environment=environment)['routes']
    official = 'semantic/native/pins_official.h:'
    result = {}
    for identity, size in (
        (official + 'PIN_userdefault_get_instance', 76),
        (official + 'PIN_mod_visual_b38580', 8),
        ('semantic/character/character_pins.h:CHARACTER_PIN_17', 200),
    ):
        address = mapping[number(all_pins[identity]['address'])]
        require(functions.get(address) == size, 'Reviewed upstream FDE span differs: ' + identity)
        result[identity] = {'address': address, 'bytes': size,
                            'reason': 'Guard the complete exact 7.1 FDE instead of the old function extent; ABI acceptance remains separate.'}

    sections = {row['name']: row for row in receipt['compiled_sections']}
    require(len(sections) == len(receipt['compiled_sections']), 'Duplicate authored section')
    # Old overlapping caves no longer describe the new layout. These arrays are
    # integrity-only: covering the complete section also covers every old subguard.
    for symbol, name in (
        ('PIN_toggle_operation_5', '.replay_gates'),
        ('PIN_mod_fallbacks', '.mod_gates'),
        ('PIN_mod_v2_op_15', '.mod_gates'),
        ('PIN_mod_v2_op_16', '.mod_gates'),
    ):
        require(name in sections, 'Reviewed authored section missing: ' + name)
        section = sections[name]
        require(type(section['bytes']) is int and section['bytes'] > 0, 'Invalid authored section extent')
        result[official + symbol] = {'address': number(section['va']), 'bytes': section['bytes'],
                                     'reason': 'Guard the entire compiled ' + name + ' section instead of an overlapping 7.0 cave; no callable binding changes.'}

    for index, route in enumerate(('login', 'aggregate', 'bundle')):
        identity = 'semantic/native/cli_pins.h:CLI_ROUTE_' + str(index)
        symbol = 'route_' + route + '_uri'
        require(symbol in receipt['symbols'], 'Authored route symbol missing: ' + symbol)
        expected = routes[route].encode('ascii') + b'\0'
        address, size = number(receipt['symbols'][symbol]), len(expected)
        section = sections.get('.routes')
        require(section and number(section['va']) <= address
                and address + size <= number(section['va']) + section['bytes'],
                'Authored route symbol exceeds its section: ' + symbol)
        data = native.read_virtual(raw, address, size)
        require(data == expected, 'Complete authored route literal required: ' + symbol)
        result[identity] = {'address': address, 'bytes': size,
                            'reason': 'Guard the complete ' + environment + ' route literal at its linked symbol.'}
    return result


def prepare(core, native_receipt, source_root, output, *, overrides=None, authored_addresses=None):
    """Write all27headers only when every506pin and template has an explicit target."""
    engine_raw = Path(__file__).read_bytes()
    core, native_receipt, source_root, output = map(unlinked, (core, native_receipt, source_root, output))
    require(not output.exists() and not output.is_relative_to(REPO) and not output.is_relative_to(source_root),
            'Fresh external pin output required')
    raw, receipt_raw = core.read_bytes(), native_receipt.read_bytes()
    receipt = json.loads(receipt_raw)
    layout_path = unlinked(source_root / 'pin-layout.json')
    layout_raw = layout_path.read_bytes()
    headers = validate_inputs(raw, receipt, layout_raw)
    binding_path = HERE / 'bindings.json'
    binding_raw = binding_path.read_bytes()
    bindings = json.loads(binding_raw)
    require(bindings.get('schema') == 'akaine.native-bindings.v1' and bindings.get('target_core_sha256') == STOCK_SHA,
            'Exact7.1 binding inventory required')
    mapping = {number(row['old']): number(row['new']) for row in bindings['mappings']}
    require(len(mapping) == len(bindings['mappings']) == 677
            and all(row['kind'] in ('function_va', 'data_va') for row in bindings['mappings'])
            and all(k >= 0x400000 and v >= 0x400000 for k, v in mapping.items()),
            'Complete upstream ELF address inventory required')
    require(mapping.get(0x1acf880) == 0x1afe870, 'Advanced guide Skip owner binding differs')
    authored = {number(old): number(new) for old, new in receipt.get('authored_addresses', {}).items()}
    for old, new in (authored_addresses or {}).items():
        old, new = number(old), number(new)
        require(old not in authored or authored[old] == new, 'Authored address differs from native receipt')
        authored[old] = new
    for old, new in authored.items():
        old, new = number(old), number(new)
        require(old not in mapping and old >= 0x400000 and new >= 0x400000, 'Authored binding overlaps upstream')
        mapping[old] = new
    all_pins = {h['path'] + ':' + p['symbol']: p for h in headers for p in h['pins']}
    require(len(all_pins) == 506 and set(overrides or {}) <= all_pins.keys(), 'Unknown or duplicate pin override')
    for item in (overrides or {}).values():
        require(isinstance(item, dict) and set(item) == {'address', 'bytes', 'reason'}
                and isinstance(item['reason'], str) and item['reason'].strip(), 'Reviewed override address/bytes/reason required')
    metadata, relocations, functions = target_metadata(raw, receipt), relocation_records(raw), function_ranges(raw)
    settings_callbacks = target_settings_rows(raw, relocations, functions, receipt)
    cli_callbacks = target_cli_rows(raw, relocations, functions)
    tutorial_pins = pack_tutorial_header(raw, relocations, functions)
    reviewed = reviewed_overrides(raw, receipt, mapping, all_pins, functions)
    require(set(reviewed) <= all_pins.keys() and not set(reviewed).intersection(overrides or {}),
            'Reviewed pin overrides cannot be missing or replaced')
    overrides = {**reviewed, **(overrides or {})}
    starts = list(functions)
    pending, rendered, records = [], {}, []
    for header in headers:
        text = '\n'.join(header['template']) + '\n'
        pin_addresses = {}
        for pin in header['pins']:
            identity = header['path'] + ':' + pin['symbol']
            symbol, size = pin['symbol'], pin['bytes']
            require(re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', symbol) is not None
                    and text.count('@@' + symbol + '@@') == 1, 'Unique pin placeholder required')
            override = (overrides or {}).get(identity)
            old = number(pin['address']) if 'address' in pin else None
            file_at = None
            if override:
                address, size = number(override['address']), override['bytes']
            elif symbol == 'EXPECTED_BUILD_ID':
                address, file_at = None, metadata['build_id_offset']
            elif header['path'] == 'semantic/native/pins_official.h' and symbol in RELOCATION_FIELDS:
                relocated = relocations.get(mapping[RELOCATION_FIELDS[symbol]])
                require(relocated and relocated['type'] == 1027, 'Settings callback relative relocation required')
                file_at = relocated['offset'] + 16
                address = file_at  # The first LOAD maps file offsets at VA zero.
                require(native.file_offset(raw, address, size) == file_at, 'Relocation field file/VA identity differs')
            elif header['path'] == 'semantic/native/pins_official.h' and symbol in ('PIN_toggle_operation_0', 'PIN_official_operation_0'):
                address = metadata['rw_memory_offset']
            elif header['path'] == 'semantic/owned/owned_core_pins.h' and symbol == 'reset_extra_pin_1':
                address = metadata['rx_size_offset']
            elif header['path'] == 'semantic/owned/owned_core_pins.h' and symbol == 'owned_pin_9':
                address, size = metadata['note_va'], metadata['note_bytes']
            elif old in mapping:
                address = mapping[old]
            else:
                pending.append({'pin': identity, 'reason': 'unmapped_authored_pin', 'old_address': hex(old) if old else None})
                continue
            require(type(size) is int and 0 < size <= len(raw), 'Invalid pin byte count')
            if address is not None:
                native.file_offset(raw, address, size)
                position = bisect_right(starts, address) - 1
                if position >= 0 and starts[position] <= address < starts[position] + functions[starts[position]]:
                    end = starts[position] + functions[starts[position]]
                    if address + size > end:
                        pending.append({'pin': identity, 'reason': 'pin_crosses_target_fde', 'address': hex(address),
                                        'bytes': size, 'maximum_bytes': end - address})
                        continue
                pin_addresses[symbol] = address
            if file_at is None:
                file_at = native.file_offset(raw, address, size)
            data = raw[file_at:file_at + size]
            require(len(data) == size, 'Pin exceeds native file')
            records.append({'pin': identity, 'address': hex(address) if address is not None else None,
                            'file_offset': file_at, 'bytes': size, 'sha256': sha(data),
                            **({'override_reason': override['reason']} if override else {})})
            text = text.replace('@@' + symbol + '@@', ','.join(hex(value) for value in data))
        # Pin rows can differ despite sharing an old authored region.
        text = mask_pin_rows(text)
        for name, value in metadata['constants'].items():
            text = re.sub(r'(\b' + name + r'\s*=\s*)0x[0-9a-fA-F]+', r'\g<1>@@CONSTANT_' + name + '@@', text)
        missing_literals = set()
        def replace_address(match):
            value = int(match[0], 16)
            if value < 0x400000:
                return match[0]
            if value not in mapping:
                missing_literals.add(match[0])
                return match[0]
            return hex(mapping[value])
        text = HEX.sub(replace_address, text)
        for symbol, address in pin_addresses.items():
            text = text.replace('@@ADDRESS_' + symbol + '@@', hex(address))
        for name, value in metadata['constants'].items():
            text = text.replace('@@CONSTANT_' + name + '@@', hex(value))
        for value in sorted(missing_literals):
            pending.append({'header': header['path'], 'reason': 'unmapped_template_address', 'old_address': value})
        if '@@' in text:
            pending.append({'header': header['path'], 'reason': 'unresolved_template_placeholder'})
        if header['path'] == 'semantic/owned/owned_core_pins.h':
            text += ''.join('inline constexpr uintptr_t ' + name + ' = ' + hex(value) + ';\n'
                            for name, value in metadata['owned_constants'].items())
        if header['path'] == 'semantic/controls/skill_pins.h':
            marker = 'inline constexpr SkillAbilityType SKILL_ABILITY_TYPES[] = {'
            require(text.count(marker) == 1, 'Unique skill ability allowlist required')
            before, separator, after = text.rpartition('};')
            require(separator and not after.strip(), 'Skill allowlist must end the generated header')
            text = before + target_ability_rows(raw, relocations) + separator + after
        if header['path'] == 'semantic/overlays/overlay_pins.h':
            text += tutorial_pins
        # These pointers are loader-relocated; compare RELA addends, not raw slots.
        for slot, destination in re.findall(r'\{(0x[0-9a-fA-F]+),(0x[0-9a-fA-F]+)\}', text):
            relocation = relocations.get(int(slot, 16))
            if not relocation or relocation['type'] != 1027 or relocation['addend'] != int(destination, 16):
                pending.append({'header': header['path'], 'reason': 'relocated_pointer_differs', 'slot': slot,
                                'expected_addend': destination, 'actual_addend': hex(relocation['addend']) if relocation else None})
        rendered[header['path']] = text
    result = {'schema': 'akaine.port71.pin-generation.v1', 'core_sha256': sha(raw),
              'application_version': receipt['application_version'], 'environment': receipt['environment'],
              'package': receipt['package'],
              'engine_sha256': sha(engine_raw),
              'native_receipt_sha256': sha(receipt_raw), 'baseline_layout_sha256': sha(layout_raw),
              'bindings_sha256': sha(binding_raw),
              'pin_count': 506, 'resolved_pin_count': len(records), 'header_count': 27,
              'reviewed_override_count': len(reviewed),
              'settings_callbacks': settings_callbacks,
              'cli_callbacks': cli_callbacks,
              'pack_tutorial_extra_pin_count': len(PACK_TUTORIAL_FUNCTIONS),
              'headers_generated': not pending, 'all_abi_reviewed': False, 'runtime_accepted': False,
              'pending': pending, 'pins': records,
              'header_sha256': {path: sha(value.encode()) for path, value in rendered.items()} if not pending else {}}
    require(core.read_bytes() == raw and native_receipt.read_bytes() == receipt_raw
            and layout_path.read_bytes() == layout_raw and binding_path.read_bytes() == binding_raw
            and Path(__file__).read_bytes() == engine_raw,
            'Input changed during pin generation')
    output.mkdir(parents=True)
    if not pending:
        for path, value in rendered.items():
            target = output / safe_path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value, encoding='utf-8', newline='\n')
    (output / 'PIN_RECEIPT.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result
