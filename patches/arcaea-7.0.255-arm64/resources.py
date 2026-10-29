"""Guarded Android manifest/resources and current Mod layout transformations."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import zipfile

MANIFEST_SHA = 'c03e7fab98cd32c24ee426781d6601735646610886e2b8f8e2b9da2f64cf85c8'
RESOURCES_SHA = 'f2435512da1ff6d398a726c12063279f0a6eaf2d7d3216df3ef4afb565daadfa'
PACKAGE = 'akai.arc.lmao'
ANDROID = 'http://schemas.android.com/apk/res/android'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def chunks(blob, expected_kind):
    kind, header, total = struct.unpack_from('<HHI', blob)
    require(kind == expected_kind and header >= 8 and total == len(blob), 'Resource root header differs')
    rows, at = [], header
    while at < total:
        kind, size_header, size = struct.unpack_from('<HHI', blob, at)
        require(size_header >= 8 and size >= size_header and at + size <= total, 'Resource chunk bounds differ')
        rows.append((kind, blob[at:at + size]))
        at += size
    require(at == total, 'Resource chunks do not cover root')
    return rows


def read_pool(data):
    kind, header, total, count, styles, flags, start, style_start = struct.unpack_from('<HHI5I', data)
    require(kind == 1 and header == 28 and total == len(data) and styles == style_start == 0,
            'Unstyled standard string pool required')
    require(start == header + count * 4, 'String pool offset table differs')
    values = []
    for index in range(count):
        at = start + struct.unpack_from('<I', data, header + index * 4)[0]
        require(at < total, 'String pool item is outside chunk')
        if flags & 0x100:
            def length(offset):
                value = data[offset]
                return (((value & 127) << 8) | data[offset + 1], offset + 2) if value & 128 else (value, offset + 1)
            units, at = length(at)
            size, at = length(at)
            value = data[at:at + size].decode('utf-8')
            require(data[at + size] == 0 and len(value.encode('utf-16le')) // 2 == units, 'UTF8 string terminator/length differs')
        else:
            size = struct.unpack_from('<H', data, at)[0]
            require(size < 0x8000, 'Extended UTF16 string is not part of this baseline')
            value = data[at + 2:at + 2 + size * 2].decode('utf-16le')
            require(data[at + 2 + size * 2:at + 4 + size * 2] == b'\0\0', 'UTF16 terminator differs')
        values.append(value)
    return values, flags


def write_pool(values, flags):
    encoded, offsets = bytearray(), []
    def length(value):
        require(value < 0x8000, 'String is too long for the pinned pool')
        return bytes((0x80 | (value >> 8), value & 255)) if value >= 128 else bytes((value,))
    for value in values:
        offsets.append(len(encoded))
        units = len(value.encode('utf-16le')) // 2
        if flags & 0x100:
            data = value.encode('utf-8')
            encoded += length(units) + length(len(data)) + data + b'\0'
        else:
            require(units < 0x8000, 'String is too long for the pinned pool')
            encoded += struct.pack('<H', units) + value.encode('utf-16le') + b'\0\0'
    encoded += bytes((-len(encoded)) % 4)
    start = 28 + 4 * len(values)
    return struct.pack('<HHI5I', 1, 28, start + len(encoded), len(values), 0, flags, start, 0) + struct.pack('<' + str(len(offsets)) + 'I', *offsets) + encoded


def patch_manifest(blob):
    require(sha(blob) == MANIFEST_SHA, 'Exact APKEditor-merged APKPure manifest required')
    rows = chunks(blob, 3)
    require(sum(kind == 1 for kind, _ in rows) == sum(kind == 0x180 for kind, _ in rows) == 1, 'Unique manifest pools required')
    values, flags = read_pool(next(data for kind, data in rows if kind == 1))
    require(len(values) == 200 and flags == 0 and 'debuggable' not in values, 'Manifest string baseline differs')
    rewritten = []
    for value in values:
        if value == 'moe.low.arc' or value.startswith('moe.low.arc.'):
            value = PACKAGE + value[len('moe.low.arc'):]
        elif value == 'cct.moe.low.arc':
            value = 'cct.' + PACKAGE
        rewritten.append(value)
    require(sum(a != b for a, b in zip(values, rewritten)) == 8, 'Manifest package-string count differs')
    scheme_index, debug_index = len(rewritten), len(rewritten) + 1
    rewritten += ['fb664034082680649', 'debuggable']
    resource = next(data for kind, data in rows if kind == 0x180)
    require(len(resource) == 172, 'Manifest resource map baseline differs')
    ids = list(struct.unpack_from('<41I', resource, 8))
    ids += [0] * (debug_index - len(ids)) + [0x0101000F]
    new_resource = struct.pack('<HHI', 0x180, 8, 8 + len(ids) * 4) + struct.pack('<' + str(len(ids)) + 'I', *ids)
    application_count = scheme_count = 0
    result = []
    for kind, data in rows:
        if kind == 1:
            data = write_pool(rewritten, flags)
        elif kind == 0x180:
            data = new_resource
        elif kind == 0x102:
            namespace, name = struct.unpack_from('<II', data, 16)
            attr_start, attr_size, count, *_ = struct.unpack_from('<6H', data, 24)
            require(attr_size == 20, 'Manifest attribute stride differs')
            start = 16 + attr_start
            attrs = [data[start + 20 * index:start + 20 * (index + 1)] for index in range(count)]
            for index, attr in enumerate(attrs):
                attr_namespace, attr_name, raw, size, res0, attr_type, value = struct.unpack('<IIIHBBI', attr)
                if values[attr_name] == 'scheme' and attr_type == 1:
                    require(attr_namespace < len(values) and values[attr_namespace] == ANDROID, 'Scheme namespace differs')
                    attrs[index] = struct.pack('<IIIHBBI', attr_namespace, attr_name, scheme_index, 8, 0, 3, scheme_index)
                    scheme_count += 1
            if values[name] == 'application':
                require(count == 9 and application_count == 0, 'Application attribute baseline differs')
                resource_ids = [ids[struct.unpack_from('<I', attr, 4)[0]] for attr in attrs]
                require(resource_ids == sorted(resource_ids) and 0x0101000F not in resource_ids, 'Application resource order differs')
                position = next(index for index, value in enumerate(resource_ids) if value > 0x0101000F)
                attrs.insert(position, struct.pack('<IIIHBBI', values.index(ANDROID), debug_index, 0xFFFFFFFF, 8, 0, 0x12, 0xFFFFFFFF))
                application_count += 1
            changed = bytearray(data[:start] + b''.join(attrs) + data[start + count * 20:])
            struct.pack_into('<I', changed, 4, len(changed))
            struct.pack_into('<H', changed, 28, len(attrs))
            data = bytes(changed)
        result.append(data)
    require(application_count == scheme_count == 1, 'Exactly one application and Facebook scheme change required')
    output = struct.pack('<HHI', 3, 8, 8 + sum(map(len, result))) + b''.join(result)
    require(len(chunks(output, 3)) == len(rows), 'Manifest element set changed')
    return output


def patch_resources(blob):
    require(sha(blob) == RESOURCES_SHA, 'Exact APKEditor-merged APKPure resources required')
    rows = chunks(blob, 2)
    require([kind for kind, _ in rows] == [1, 0x200], 'Single-package resource baseline differs')
    values, flags = read_pool(rows[0][1])
    require(len(values) == 576 and flags == 0x100 and values.count('Arcaea') == 1, 'Application label baseline differs')
    values[values.index('Arcaea')] = 'AkaineXD'
    pool = write_pool(values, flags)
    package = bytearray(rows[1][1])
    require(package[12:268].decode('utf-16le').rstrip('\0') == 'moe.low.arc', 'Resource package name differs')
    package[12:268] = PACKAGE.encode('utf-16le').ljust(256, b'\0')
    require(bytes(package[268:]) == rows[1][1][268:], 'Resource tables changed')
    header = bytearray(blob[:12])
    struct.pack_into('<I', header, 4, 12 + len(pool) + len(package))
    return bytes(header) + pool + package


def build_resources(stock_apk, output):
    output = Path(output)
    require(not output.exists(), 'Fresh managed resource output required')
    output.mkdir(parents=True)
    with zipfile.ZipFile(stock_apk) as archive:
        source_manifest, source_resources = archive.read('AndroidManifest.xml'), archive.read('resources.arsc')
    manifest, resources = patch_manifest(source_manifest), patch_resources(source_resources)
    replacements = {}
    for name, data in (('AndroidManifest.xml', manifest), ('resources.arsc', resources)):
        target = output / name
        target.write_bytes(data)
        replacements[name] = target
    return replacements, {'status': 'FINITE_STOCK_MANAGED_RESOURCE_PATCHED', 'source_manifest_sha256': sha(source_manifest),
        'output_manifest_sha256': sha(manifest), 'source_resources_sha256': sha(source_resources),
        'output_resources_sha256': sha(resources), 'unrelated_resource_xml_changed': False,
        'resource_ids_and_resource_values_except_app_label_unchanged': True,
        'package': PACKAGE, 'application_label': 'AkaineXD', 'debuggable_for_semantic_cli': True}



# The Mod layouts are generated from the original sidebar and owned artwork.
PIN = '5e63d7c0ebe491480ffcbc65d7333ac481d52cdc6440feaa8230602c5fc7abdb'
ART_PIN = '5e53987e1f542ed1107e4eea73ec150475341a0f03616950dd0ac73c0ab1526f'
EXPECTED = {
    'assets/layouts/songselect/PackListModMenu.csb': 'f119b1a51824fdc3651883d119cc85e8462c0fd918161e15faef8010fcbb7293',
    'assets/layouts/songselect/ModDividerNativeFrame.csb': '2e11c82033d86f0e0dff63ab28069e04e23fc7b87d33289159f6973bd5fed5cd',
    'assets/img/1080/divider_mod_v8.png': ART_PIN,
}

class Reader:
    def __init__(self, data):
        self.data = data

    def unpack(self, fmt, offset):
        assert 0 <= offset <= len(self.data) - struct.calcsize(fmt)
        return struct.unpack_from(fmt, self.data, offset)[0]

    def u16(self, p): return self.unpack('<H', p)
    def u32(self, p): return self.unpack('<I', p)
    def i32(self, p): return self.unpack('<i', p)

    def field(self, table, index):
        if not table: return 0
        vt = table - self.i32(table)
        size = self.u16(vt)
        at = 4 + index * 2
        return table + self.u16(vt + at) if at < size and self.u16(vt + at) else 0

    def pointer(self, table, index):
        p = self.field(table, index)
        return p + self.u32(p) if p else 0

    def string_at(self, p):
        if not p: return ''
        n = self.u32(p)
        assert p + 4 + n < len(self.data) and self.data[p + 4 + n] == 0
        return self.data[p + 4:p + 4 + n].decode('utf-8')

    def string(self, table, index):
        return self.string_at(self.pointer(table, index))

    def vector(self, table, index):
        p = self.pointer(table, index)
        if not p: return []
        return [p + 4 + i * 4 + self.u32(p + 4 + i * 4) for i in range(self.u32(p))]

    def pair(self, table, index):
        p = self.field(table, index)
        return tuple(struct.unpack_from('<ff', self.data, p)) if p else None

    def scalar(self, table, index, fmt, default):
        p = self.field(table, index)
        return self.unpack(fmt, p) if p else default

    def nodes(self):
        result = {}
        def visit(node, parent):
            kind = self.string(node, 0)
            data = self.pointer(self.pointer(node, 2), 0)
            widget = data if kind == 'Node' else self.pointer(data, 0)
            name = self.string(widget, 0)
            path = parent + '/' + name
            assert path not in result
            row = {'node': node, 'data': data, 'widget': widget, 'kind': kind,
                'name': name, 'position': self.pair(widget, 7), 'scale': self.pair(widget, 8),
                'anchor': self.pair(widget, 9), 'size': self.pair(widget, 11),
                'actionTag': self.scalar(widget, 1, '<i', 0), 'tag': self.scalar(widget, 6, '<i', 0)}
            if kind == 'Text': row['text'] = self.string(data, 4)
            if kind == 'Button':
                row['normal'] = self.string(self.pointer(data, 1), 0)
                row['pressed'] = self.string(self.pointer(data, 2), 0)
            result[path] = row
            for child in self.vector(node, 1): visit(child, path)
        visit(self.pointer(self.u32(0), 3), '')
        return result


def sidebar(source):
    assert len(source) == 14708 and sha(source) == PIN
    old = Reader(source)
    nodes = old.nodes()
    root = old.u32(0)
    root_node = old.pointer(root, 3)
    bar = nodes['/Node/barButtons']['node']
    button5 = nodes['/Node/barButtons/button5']
    accent = nodes['/Node/barButtons/accentBottom']
    root_children = old.vector(root_node, 1)
    bar_children = old.vector(bar, 1)
    assert len(bar_children) == 10
    assert [nodes['/Node/barButtons/button' + str(i)]['name'] for i in range(1, 6)] == ['button1', 'button2', 'button3', 'button4', 'button5']

    # A short new root/ancestor spine precedes two untouched-format source copies.
    # This preserves unknown 2.1.0.0 fields and shared forward vtables/strings.
    # Only the second copy's button5 subtree is reachable as new button6.
    prefix = bytearray(4)
    def align(n):
        while len(prefix) % n: prefix.append(0)

    def clone_table(table):
        vt = table - old.i32(table)
        vsize, osize = old.u16(vt), old.u16(vt + 2)
        align(2)
        new_vt = len(prefix)
        prefix.extend(source[vt:vt + vsize])
        align(4)
        new_table = len(prefix)
        prefix.extend(source[table:table + osize])
        struct.pack_into('<i', prefix, new_table, new_table - new_vt)
        return new_table

    def vector_placeholder(count):
        align(4)
        at = len(prefix)
        prefix.extend(struct.pack('<I', count) + bytes(4 * count))
        return at

    new_root = clone_table(root)
    new_root_node = clone_table(root_node)
    new_root_children = vector_placeholder(len(root_children))
    new_bar = clone_table(bar)
    new_bar_children = vector_placeholder(len(bar_children) + 1)
    align(4)
    original_base = len(prefix)
    clone_base = original_base + len(source)

    def reference(field, target):
        assert target > field and target - field < 2**32
        struct.pack_into('<I', prefix, field, target - field)

    def table_references(old_table, new_table, count, replacements):
        for index in range(count):
            old_field = old.field(old_table, index)
            if not old_field: continue
            new_field = new_table + old_field - old_table
            reference(new_field, replacements.get(index, original_base + old.pointer(old_table, index)))

    table_references(root, new_root, 6, {3: new_root_node})
    table_references(root_node, new_root_node, 4, {1: new_root_children})
    table_references(bar, new_bar, 4, {1: new_bar_children})
    for i, child in enumerate(root_children):
        reference(new_root_children + 4 + i * 4, new_bar if child == bar else original_base + child)
    for i, child in enumerate(bar_children):
        reference(new_bar_children + 4 + i * 4, original_base + child)
    reference(new_bar_children + 4 + len(bar_children) * 4, clone_base + button5['node'])
    struct.pack_into('<I', prefix, 0, new_root)
    result = prefix + source + source
    patches = []
    def patch(at, data, label):
        before = bytes(result[at:at + len(data)])
        result[at:at + len(data)] = data
        patches.append({'offset': at, 'before_hex': before.hex(), 'after_hex': data.hex(), 'label': label})

    patch(original_base + old.field(accent['widget'], 7) + 4, struct.pack('<f', -830), 'accentBottom Y')
    name_at = old.pointer(button5['widget'], 0)
    assert old.string_at(name_at) == 'button5'
    patch(clone_base + name_at + 4, b'button6', 'new button name')
    patch(clone_base + old.field(button5['widget'], 7) + 4,
        struct.pack('<f', button5['position'][1] - 95), 'new button Y')
    text = nodes['/Node/barButtons/button5/text']
    text_at = old.pointer(text['data'], 4)
    assert old.string_at(text_at) == 'Side Story'
    patch(clone_base + text_at, struct.pack('<I', 3) + b'Mod\0', 'new label text')
    marker = nodes['/Node/barButtons/button5/new']
    patch(clone_base + old.field(marker['widget'], 8), struct.pack('<ff', 0, 0), 'new badge scale hidden')
    used_actions = {row['actionTag'] for row in nodes.values()}
    used_tags = {row['tag'] for row in nodes.values()}
    for i, row in enumerate([button5, text, marker]):
        action = 0x70000000 + i
        tag = 700000 + i
        assert action not in used_actions and tag not in used_tags
        patch(clone_base + old.field(row['widget'], 1), struct.pack('<i', action), 'new subtree unique actionTag')
        patch(clone_base + old.field(row['widget'], 6), struct.pack('<i', tag), 'new subtree unique tag')

    new = Reader(result)
    after = new.nodes()
    expected_paths = set(nodes) | {'/Node/barButtons/button6', '/Node/barButtons/button6/text', '/Node/barButtons/button6/new'}
    assert set(after) == expected_paths
    for path, before in nodes.items():
        now = after[path]
        for key, value in before.items():
            if key in ('node', 'data', 'widget'): continue
            if path == '/Node/barButtons/accentBottom' and key == 'position': value = (before['position'][0], -830.0)
            assert now[key] == value, (path, key, now[key], value)
    mod = after['/Node/barButtons/button6']
    assert mod['position'] == (40.0, button5['position'][1] - 95)
    assert mod['normal'] == button5['normal'] and mod['pressed'] == button5['pressed']
    assert after['/Node/barButtons/button6/text']['text'] == 'Mod'
    assert after['/Node/barButtons/button6/new']['scale'] == (0, 0)
    assert len(new.vector(new_bar, 1)) == 11
    # Invert every bounded patch and require the preserved payloads byte-for-byte.
    normalized = bytearray(result)
    for item in patches:
        start = item['offset']
        normalized[start:start + len(bytes.fromhex(item['before_hex']))] = bytes.fromhex(item['before_hex'])
    assert normalized[original_base:clone_base] == source
    assert normalized[clone_base:] == source
    # New table spine has only forward references to valid original-format data.
    assert new.string(new_root, 0) == old.string(root, 0) == '2.1.0.0'
    for row in after.values():
        assert 0 < row['node'] < len(result) and 0 < row['widget'] < len(result)
    for number in range(2, 7):
        row = after['/Node/barButtons/button' + str(number)]
        at = new.field(row['widget'], 7)
        struct.pack_into('<f', result, at + 4, -270.0 - 85.0 * (number - 1))
    return bytes(result)


def divider(source):
    assert hashlib.sha256(source).hexdigest() == PIN
    old = Reader(source)
    nodes = old.nodes()
    source_root = old.u32(0)
    root = nodes['/Node']
    button = nodes['/Node/barButtons/button5']
    label = nodes['/Node/barButtons/button5/text']
    prefix = bytearray(4)

    def align(n):
        while len(prefix) % n:
            prefix.append(0)

    def clone(table):
        vt = table - old.i32(table)
        vsize, osize = old.u16(vt), old.u16(vt + 2)
        align(2)
        new_vt = len(prefix)
        prefix.extend(source[vt:vt + vsize])
        align(4)
        result = len(prefix)
        prefix.extend(source[table:table + osize])
        struct.pack_into('<i', prefix, result, result - new_vt)
        return result

    def string(text):
        align(4)
        result = len(prefix)
        raw = text.encode('utf-8')
        prefix.extend(struct.pack('<I', len(raw)) + raw + b'\0')
        return result

    file_root = clone(source_root)
    cloned = {}
    for key, row in [('root', root), ('backing', button), ('label', label)]:
        options = old.pointer(row['node'], 2)
        new_node, new_options = clone(row['node']), clone(options)
        data = row['data']
        new_data = clone(data)
        new_widget = new_data if row['kind'] == 'Node' else clone(row['widget'])
        cloned[key] = {'node': new_node, 'options': new_options, 'data': new_data,
                       'widget': new_widget, 'old_options': options, 'old': row}
        if key == 'root':
            align(4)
            vector = len(prefix)
            prefix.extend(struct.pack('<III', 2, 0, 0))
    align(4)
    empty_vector = len(prefix)
    prefix.extend(struct.pack('<I', 0))
    names = {name: string(value) for name, value in [('root', 'ModDividerNativeFrame'), ('backing', 'mod_backing'), ('label', 'mod_label')]}
    art_resource = clone(old.pointer(button['data'], 2))
    text = string('')
    art_path = string('img/1080/divider_mod_v8.png')
    align(4)
    source_base = len(prefix)

    def ref(field, target):
        assert target > field
        struct.pack_into('<I', prefix, field, target - field)

    def refs(old_table, new_table, fields, replacements=None):
        for index in fields:
            field = old.field(old_table, index)
            if field:
                ref(new_table + field - old_table,
                    (replacements or {}).get(index, source_base + old.pointer(old_table, index)))

    def omit(table, index):
        vt = table - struct.unpack_from('<i', prefix, table)[0]
        if 4 + 2 * index < struct.unpack_from('<H', prefix, vt)[0]:
            struct.pack_into('<H', prefix, vt + 4 + 2 * index, 0)

    def put(row, index, fmt, *values):
        at = old.field(row['old']['widget'], index)
        assert at
        struct.pack_into(fmt, prefix, row['widget'] + at - row['old']['widget'], *values)

    refs(old.pointer(button['data'], 2), art_resource, [0, 1], {0: art_path})
    refs(source_root, file_root, range(6), {3: cloned['root']['node']})
    for key, row in cloned.items():
        prior = row['old']
        refs(prior['node'], row['node'], range(4), {1: vector if key == 'root' else empty_vector, 2: row['options']})
        refs(row['old_options'], row['options'], [0], {0: row['data']})
        if key == 'backing':
            pressed = art_resource
            empty_title = source_base + old.pointer(prior['data'], 6)
            assert old.string(prior['data'], 6) == ''
            refs(prior['data'], row['data'], range(7), {0: row['widget'], 1: pressed, 2: pressed, 3: pressed, 5: empty_title})
        elif key == 'label':
            refs(prior['data'], row['data'], [0, 1, 2, 4], {0: row['widget'], 4: text})
            at = old.field(prior['data'], 3)
            struct.pack_into('<i', prefix, row['data'] + at - prior['data'], 26)
        refs(prior['widget'], row['widget'], [0, 16, 17, 18, 19, 20], {0: names[key]})
        omit(row['widget'], 20)
        omit(row['widget'], 15)
        put(row, 8, '<ff', 1, 1)
        put(row, 9, '<ff', 0.5, 0.5)
    put(cloned['root'], 7, '<ff', 0, 0)
    put(cloned['root'], 11, '<ff', 110, 457)
    for key in ('backing', 'label'):
        put(cloned[key], 7, '<ff', 55, 228.5)
        put(cloned[key], 2, '<ff', 0, 0)
    put(cloned['backing'], 11, '<ff', 725, 2170)
    put(cloned['backing'], 8, '<ff', 110 / 480, 457 / 2068)
    put(cloned['backing'], 7, '<ff', 55 + (725 / 2 - 374) * 110 / 480, 228.5 - (2170 / 2 - 1034) * 457 / 2068)
    backing = cloned['backing']
    for index, fmt, values in [(11, '<B', (0,)), (10, '<ff', (725, 2170))]:
        at = old.field(backing['old']['data'], index)
        assert at
        struct.pack_into(fmt, prefix, backing['data'] + at - backing['old']['data'], *values)
    ref(vector + 4, cloned['backing']['node'])
    ref(vector + 8, cloned['label']['node'])
    struct.pack_into('<I', prefix, 0, file_root)
    result = bytes(prefix) + source
    parsed = Reader(result)
    tree = parsed.nodes()
    assert set(tree) == {'/ModDividerNativeFrame', '/ModDividerNativeFrame/mod_backing', '/ModDividerNativeFrame/mod_label'}
    assert tree['/ModDividerNativeFrame']['anchor'] == (0.5, 0.5)
    assert tree['/ModDividerNativeFrame']['size'] == (110, 457)
    assert tree['/ModDividerNativeFrame/mod_label']['text'] == ''
    assert tree['/ModDividerNativeFrame/mod_backing']['normal'].endswith('divider_mod_v8.png')
    assert parsed.string(tree['/ModDividerNativeFrame/mod_backing']['data'], 5) == ''
    # This exact CSLoader dereferences the child vector even on leaf nodes.
    for row in tree.values():
        assert parsed.pointer(row['node'], 1), 'Explicit empty child vector required'
    assert result[source_base:] == source
    return result


def build_assets(stock_apk, output, artwork):
    """Generate exactly the current Mod additions, with no accepted APK payload input."""
    stock_apk, artwork, output = map(Path, (stock_apk, artwork, output))
    for path in (stock_apk, artwork):
        if path.is_symlink() or not path.is_file():
            raise ValueError('Regular stock APK and original owned artwork are required')
    if output.exists() or output.is_symlink():
        raise ValueError('Mod asset output must be fresh')
    for parent in output.absolute().parents:
        if parent.is_symlink() or parent.exists() and getattr(parent.stat(), 'st_file_attributes', 0) & 1024:
            raise ValueError('Mod output symlink or junction is not allowed')
    art = artwork.read_bytes()
    if sha(art) != ART_PIN:
        raise ValueError('Original owned Mod artwork differs')
    with zipfile.ZipFile(stock_apk) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate APK members are not allowed')
        source = archive.read('assets/layouts/songselect/PackListSidebar.csb')
    if len(source) != 14708 or sha(source) != PIN:
        raise ValueError('Original stock sidebar differs')
    generated = {
        'assets/layouts/songselect/PackListModMenu.csb': sidebar(source),
        'assets/layouts/songselect/ModDividerNativeFrame.csb': divider(source),
        'assets/img/1080/divider_mod_v8.png': art,
    }
    if any(sha(data) != EXPECTED[name] for name, data in generated.items()):
        raise ValueError('Generated Mod layout/artwork identity differs')
    paths = {}
    for name, data in generated.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
        paths[name] = target
    receipt = {'status': 'STOCK_GENERATED_MOD_ASSETS_VERIFIED', 'source_sidebar_sha256': PIN,
               'asset_sha256': dict(EXPECTED), 'commercial_assets_copied_into_public_source': False,
               'accepted_APK_used_as_build_input': False, 'runtime_accepted': False}
    return paths, receipt
