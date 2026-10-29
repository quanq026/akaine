"""Read ELF unwind tables and direct ARM64 BL sites without executing target code."""
from bisect import bisect_right
import json
from pathlib import Path
import runpy
import struct

HERE = Path(__file__).resolve().parent
Elf = runpy.run_path(str(HERE / 'broad/native/compare_core.py'))['Elf']


class UnwindMap:
    def __init__(self, elf):
        self.elf = elf
        header = elf.named['.eh_frame_hdr']
        self.base = header['address']
        data = elf.bytes(self.base, header['size'])
        assert data[:4] == bytes([1, 0x1b, 3, 0x3b])
        count = struct.unpack_from('<I', data, 8)[0]
        assert 12 + count * 8 <= len(data)
        self.rows = [(self.base + start, self.base + fde) for start, fde in struct.iter_unpack('<ii', data[12:12 + count * 8])]
        self.starts = [r[0] for r in self.rows]
        assert self.starts == sorted(self.starts)

    def containing(self, address):
        index = bisect_right(self.starts, address) - 1
        if index < 0:
            return None
        start, fde = self.rows[index]
        data = self.elf.bytes(fde, 16)
        assert data is not None
        length, cie_pointer, relative_start, span = struct.unpack('<IIii', data)
        assert length >= 12 and cie_pointer > 0 and span > 0
        assert fde + 8 + relative_start == start
        if not start <= address < start + span:
            return None
        return {'start':hex(start), 'end':hex(start + span), 'span':span, 'fde':hex(fde)}


def branch_target(word, pc):
    if word & 0xfc000000 != 0x94000000:
        return None
    immediate = word & 0x3ffffff
    if immediate & 0x2000000:
        immediate -= 0x4000000
    return pc + immediate * 4


def main():
    assert branch_target(0x94000002, 0x1000) == 0x1008
    assert branch_target(0x97ffffff, 0x1000) == 0xffc
    assert branch_target(0x14000002, 0x1000) is None
    elf = Elf(Path('D:/AkaineResearch/aurora-static-20261022/native/aurora-libcocos2dcpp.so').read_bytes())
    unwind = UnwindMap(elf)
    addresses = [0x7d6770,0x7ec49c,0x7ec7f0,0x7ec8a0,0x83cc50,0x9022c4,0x12fd70c,0x14d0208,0x177655c,0x189a150,0x193f2ac,0x19a717c,0x16f1ec8,0xf8056c,0x15a90c4,0x868e54]
    rows = [{'address':hex(address), 'unwind_function':unwind.containing(address)} for address in addresses]
    targets = {0xf8056c,0x15a90c4,0x868e54}
    text = elf.named['.text']
    calls = []
    data = elf.bytes(text['address'], text['size'])
    for index,(word,) in enumerate(struct.iter_unpack('<I', data)):
        pc = text['address'] + index * 4
        target = branch_target(word,pc)
        if target in targets:
            calls.append({'site':hex(pc),'target':hex(target),'caller_unwind_function':unwind.containing(pc)})
    output = HERE / 'final-static-20261023/core'
    output.mkdir(parents=True,exist_ok=True)
    result = {'status':'STATIC_UNWIND_AND_DIRECT_CALL_MAP','fde_table_entries':len(unwind.rows),'addresses':rows,'direct_call_sites':calls,'target_executed':False,'limits':['Function boundaries from original unwind records, not source semantics.','Only direct BL instructions in text; indirect calls and inlined bodies not enumerated.','No target replacement payloads or private data exported.']}
    (output / 'CORE_UNWIND_MAP.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
