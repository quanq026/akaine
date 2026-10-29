"""Read cached ELF/ZIP bytes; never load a target library or run target code."""
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile

HERE = Path(__file__).resolve().parent
STUDY = HERE.parents[1]
WORK = STUDY.parent
APK = Path('W:/Not at home/drives/D/From 15_10/akaine-development-20261012/outputs/AkaineXD-7.0.255-prod-cli-skill-v9-20261022.apk')
AURORA = Path('D:/AkaineResearch/aurora-static-20261022/native/aurora-libcocos2dcpp.so')


class Elf:
    def __init__(self, raw):
        self.raw = raw
        assert raw[:6] == b'\x7fELF\x02\x01'
        offset = struct.unpack_from('<Q', raw, 40)[0]
        size, count, names = struct.unpack_from('<HHH', raw, 58)
        assert size == 64 and offset + count * size <= len(raw)
        headers = [struct.unpack_from('<IIQQQQIIQQ', raw, offset + i * size) for i in range(count)]
        strings = headers[names]
        strings = raw[strings[4]:strings[4] + strings[5]]
        self.sections = []
        for h in headers:
            name = strings[h[0]:].split(b'\0', 1)[0].decode()
            self.sections.append(dict(name=name, type=h[1], flags=h[2], address=h[3], offset=h[4], size=h[5], link=h[6], entry=h[9]))
        self.named = {s['name']: s for s in self.sections}

    def bytes(self, address, size):
        for s in self.sections:
            if s['type'] != 8 and s['address'] <= address and address + size <= s['address'] + s['size']:
                at = s['offset'] + address - s['address']
                return self.raw[at:at + size]
        return None

    def functions(self):
        table = self.named['.dynsym']
        strings = self.sections[table['link']]
        strings = self.raw[strings['offset']:strings['offset'] + strings['size']]
        assert table['entry'] == 24
        rows = []
        for at in range(table['offset'], table['offset'] + table['size'], 24):
            name, info, _, section, address, size = struct.unpack_from('<IBBHQQ', self.raw, at)
            if section and info & 15 == 2:
                name = strings[name:].split(b'\0', 1)[0].decode(errors='replace')
                rows.append(dict(name=name, address=address, size=size))
        return rows


def main():
    aurora = Elf(AURORA.read_bytes())
    with zipfile.ZipFile(APK) as archive:
        akaine = Elf(archive.read('lib/arm64-v8a/libcocos2dcpp.so'))
    sha = lambda data: hashlib.sha256(data).hexdigest()
    assert sha(aurora.raw) == '3eaca4e6dabb3395f276f8915698d57675757d0df0970e716b23a3dc201c79be'
    assert sha(akaine.raw) == 'f2729d67166faa1fcee05601ea35d775548d3bfdc2f1a3d04777b082066b235d'

    headers = WORK / 'prod-cli-speed-v9-20261022/native'
    pins = []
    for path in headers.glob('*.h'):
        text = path.read_text(encoding='utf-8-sig')
        arrays = {name: bytes(int(v, 16) for v in re.findall(r'0x([0-9a-fA-F]+)', values))
                  for name, values in re.findall(r'unsigned char\s+(\w+)\[\]\s*=\s*\{([^}]*)\}', text)}
        for address, name in re.findall(r'\{(0x[0-9a-fA-F]+),\s*(\w+),\s*sizeof\(\2\)\}', text):
            data = arrays.get(name)
            if data:
                address = int(address, 16)
                pins.append(dict(address=address, size=len(data), name=name, file=str(path), akaine_bytes_match=akaine.bytes(address, len(data)) == data))

    diff = json.loads((STUDY / 'native/COCOS_BYTE_DIFF.json').read_text(encoding='utf-8-sig'))
    regions = []
    for r in diff['regions']:
        start, end = int(r['file_offset'], 16), int(r['end_offset'], 16)
        changed = [at for at in range(start, end) if aurora.raw[at] != akaine.raw[at]]
        assert len(changed) == r['changed_bytes']
        va = int(r['address'], 16) if r['address'] else None
        changed_va = [va + at - start for at in changed] if va is not None else []
        related = [p for p in pins if va is not None and p['akaine_bytes_match'] and any(p['address'] <= at < p['address'] + p['size'] for at in changed_va)]
        covered = sum(any(p['address'] <= at < p['address'] + p['size'] for p in related) for at in changed_va)
        regions.append({k:r[k] for k in ('file_offset','end_offset','span','changed_bytes','section','address')} | {
            'changed_bytes_covered_by_verified_akaine_pins':covered,
            'related_pins':[{k:p[k] for k in ('name','file','address','size')} for p in related]})

    functions = []
    akaine_funcs = {(r['name'], r['address'], r['size']) for r in akaine.functions()}
    for r in aurora.functions():
        key = (r['name'], r['address'], r['size'])
        a, b = aurora.bytes(r['address'],r['size']), akaine.bytes(r['address'],r['size'])
        functions.append(r | {'same_symbol_in_akaine':key in akaine_funcs, 'span_available':a is not None and b is not None, 'span_equal':a is not None and b is not None and a == b})

    libraries_a = json.loads((STUDY / 'native/AURORA_NATIVE_INVENTORY.json').read_text(encoding='utf-8-sig'))
    libraries_b = json.loads((STUDY / 'native/AKAINE_NATIVE_INVENTORY.json').read_text(encoding='utf-8-sig'))
    a = {r['name']:r for split in libraries_a['splits'] for r in split['native_libraries'] if r['name'].startswith('lib/')}
    b = {r['name']:r for r in libraries_b['native_libraries']}
    library_rows = [{'path':n, 'in_aurora':n in a, 'in_akaine':n in b, 'same_sha256':a[n]['sha256'] == b[n]['sha256'] if n in a and n in b else None, 'aurora_bytes':a.get(n,{}).get('bytes'), 'akaine_bytes':b.get(n,{}).get('bytes')} for n in sorted(a.keys() | b.keys())]

    text = aurora.named['.text']
    offset, size = text['offset'],text['size']
    changed_text = sum(x != y for x,y in zip(aurora.raw[offset:offset+size],akaine.raw[offset:offset+size]))
    result = {'status':'STATIC_CORE_CENSUS', 'target_executed':False, 'core_identities':{'aurora':sha(aurora.raw),'akaine':sha(akaine.raw)},
              'text_bytes':size,'text_changed_bytes':changed_text,'regions':regions,
              'text_changed_bytes_covered_by_verified_akaine_pins':sum(r['changed_bytes_covered_by_verified_akaine_pins'] for r in regions if r['section']=='.text'),
              'defined_dynamic_function_symbol_entries':len(functions), 'same_span_entries':sum(r['span_equal'] for r in functions),
              'unique_address_size_spans':len({(r['address'],r['size']) for r in functions}),
              'zero_size_symbol_entries':sum(r['size']==0 for r in functions),
              'changed_span_entries':[r for r in functions if not r['span_equal']],
              'cocos_jni_entries':[r for r in functions if r['name'].startswith('Java_org_cocos2dx')],
              'native_library_matrix':library_rows,
              'limits':['Unchanged file bytes do not exclude runtime hooks, data-dependent behavior or different downloaded content.', 'Dynamic symbol entries can alias/overlap and do not enumerate every internal game function.', 'Matching a current Akaine pin attributes overlap to a guarded code path, not proof of who originally authored the instruction.', 'No core disassembly, secret material or bypass constants are exported by this helper.']}
    assert sum(r['changed_bytes'] for r in regions) == 1536
    assert changed_text == sum(r['changed_bytes'] for r in regions if r['section']=='.text')
    (HERE/'CORE_CENSUS.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('status','text_bytes','text_changed_bytes','text_changed_bytes_covered_by_verified_akaine_pins','defined_dynamic_function_symbol_entries','same_span_entries')}))


if __name__ == '__main__':
    main()
