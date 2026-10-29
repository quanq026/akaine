"""Lossless USB transport from the verified full-base spans; no deployment."""
import base64
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile

SOURCE = Path('D:/AkaineBuilds/prod-aurora-original-base25-20261026')
ALIAS = '7.0.255-staging-prod18-aurora-original-base25-20261026'
MANIFEST_SHA = '6e079c075bfa7d412fff06f188d26191656496599e28288722f3cfb58ac23891'
OUT = Path('D:/AkaineBuilds/prod-rebase-20261025/usb-install-base25-20261026')


def safe_name(name):
    value = PurePosixPath(name)
    assert name and not value.is_absolute() and value.as_posix() == name
    assert '..' not in value.parts and '\\' not in name and ':' not in name
    assert all(ord(c) >= 32 for c in name)


class Span:
    def __init__(self, stream, offset, size):
        self.stream, self.left = stream, size
        self.digest = hashlib.sha256()
        stream.seek(offset)

    def read(self, size):
        data = self.stream.read(min(size, self.left))
        assert data or not self.left, 'Short source span'
        self.left -= len(data)
        self.digest.update(data)
        return data


class Writer:
    def __init__(self, stream):
        self.stream, self.digest = stream, hashlib.sha256()

    def write(self, data):
        self.digest.update(data)
        return self.stream.write(data)


def info(name, size):
    safe_name(name)
    value = tarfile.TarInfo(name)
    value.size, value.mode, value.mtime = size, 0o600, 0
    return value


def main():
    raw = (SOURCE/(ALIAS+'.json')).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MANIFEST_SHA
    manifest = json.loads(raw)
    assert manifest['previousVersionNumber'] is None and manifest['removed'] == []
    assert manifest['versionNumber'] == '7.0.255.25' and len(manifest['added']) == 20903
    assert not OUT.exists()
    parts = [SOURCE/f'{ALIAS}_{i}.cb' for i in range(manifest['totalPartitions'])]
    before = [(p.stat().st_size, p.stat().st_mtime_ns) for p in parts]
    OUT.mkdir()
    target = OUT/'base25-usb.tar'
    sums = []
    streams = [p.open('rb') for p in parts]
    try:
        with target.open('xb') as destination:
            writer = Writer(destination)
            with tarfile.open(fileobj=writer, mode='w|', format=tarfile.USTAR_FORMAT) as archive:
                for row in manifest['added']:
                    name = 'active/'+row['path']
                    span = Span(streams[row['partIndex']], row['byteOffset'], row['length'])
                    archive.addfile(info(name, row['length']), span)
                    digest = span.digest.hexdigest()
                    assert span.left == 0 and base64.b64encode(bytes.fromhex(digest)).decode() == row['sha256HashBase64Encoded']
                    sums.append(digest+'  '+name+'\n')
                archive.addfile(info('meta.cb', len(raw)), io.BytesIO(raw))
                sums.append(MANIFEST_SHA+'  meta.cb\n')
                checksum = ''.join(sums).encode('utf-8')
                archive.addfile(info('SHA256SUMS', len(checksum)), io.BytesIO(checksum))
            archive_sha = writer.digest.hexdigest()
    finally:
        for stream in streams:
            stream.close()
    assert before == [(p.stat().st_size, p.stat().st_mtime_ns) for p in parts]
    expected = {'active/'+r['path'] for r in manifest['added']} | {'meta.cb', 'SHA256SUMS'}
    with tarfile.open(target) as archive:
        members = archive.getmembers()
        assert len(members) == len(expected) and {m.name for m in members} == expected
        assert all(m.isfile() and not m.issym() and not m.islnk() for m in members)
    receipt = dict(status='LOSSLESS_USB_TRANSPORT_VERIFIED', file=str(target), sha256=archive_sha,
                   bytes=target.stat().st_size, manifest_sha256=MANIFEST_SHA,
                   active_files=20903, members=len(expected), source_span_hashes_verified=True,
                   compressed=False, media_transformed=False, native_download_flow_proven=False)
    (OUT/'TRANSPORT_RECEIPT.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
