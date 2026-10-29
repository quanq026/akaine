"""Install the reviewed USB cache on one explicit device; retain rollback data."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ADB = 'W:/Not at home/drives/E/_organized/platform/android/Sdk/platform-tools/adb.exe'
PACKAGE = 'akai.arc.lmao'
TRANSPORT = Path('D:/AkaineBuilds/prod-rebase-20261025/usb-install-base25-20261026')
REMOTE = '/data/local/tmp/akaine-usb-base25-20261026.tar'
INCOMING = 'usb25-incoming-20261026'
ROLLBACK = 'cb-before-usb25-20261026'
AUDIT = 'usb25-audit-20261026'


def main():
    serial = sys.argv[1]
    assert serial in ('HA2BMMN3', 'emulator-5556')
    receipt = json.loads((TRANSPORT/'TRANSPORT_RECEIPT.json').read_bytes())
    assert receipt['status'] == 'LOSSLESS_USB_TRANSPORT_VERIFIED' and receipt['active_files'] == 20903
    assert receipt['sha256'] == 'd943bc7985168aa544182ce1f8119b9bd5ade20c8a4228921a961640ebcef600'
    assert receipt['bytes'] == 4556697600 and receipt['members'] == 20905
    assert receipt['manifest_sha256'] == '6e079c075bfa7d412fff06f188d26191656496599e28288722f3cfb58ac23891'
    archive = Path(receipt['file'])
    assert archive.is_file() and not archive.is_symlink() and archive.stat().st_size == receipt['bytes']
    record = dict(serial=serial, status='STARTING', old_cache_deleted=False,
                  native_updater_or_aggregate_download_proven=False, transport_sha256=receipt['sha256'])
    target = HERE/(serial+'_USB_INSTALL.json')
    assert not target.exists(), 'Inspect prior operation state; no automatic mutation retry'
    def save(phase):
        record['status'] = phase
        target.write_text(json.dumps(record, indent=2)+'\n')
        print(json.dumps({'serial': serial, 'phase': phase}), flush=True)
    def call(*args, timeout=30):
        result = subprocess.run([ADB, '-s', serial, *args], capture_output=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError('ADB operation failed; inspect current state, do not retry blindly')
        return result.stdout.decode(errors='replace').strip()
    def shell(script, timeout=30):
        return call('shell', '-T', 'run-as', PACKAGE, 'sh', '-c', shlex.quote('set -eu; '+script), timeout=timeout)
    if serial.startswith('emulator-'):
        assert call('shell', 'getprop', 'ro.boot.qemu.avd_name') == 'akaine_cli_stage_20261020'
    else:
        assert call('shell', 'getprop', 'ro.product.model') == 'TB710FU'
    apk = call('shell', 'pm', 'path', PACKAGE).removeprefix('package:')
    assert call('shell', 'sha256sum', apk).split()[0] == '2f4705230db06034d520b57ca0836bba424cbd7f9a6c6c79e42d92be06c23b4c'
    free = int(call('shell', 'df', '-k', '/data').splitlines()[-1].split()[3])*1024
    assert free > receipt['bytes']*2 + 1024**3
    call('shell', 'am', 'force-stop', PACKAGE)
    assert not call('shell', 'sh', '-c', shlex.quote('pidof '+PACKAGE+' || true'))
    shell('test ! -L files; if test ! -d files; then mkdir -m 700 files; fi; '
          'test -d files; test "$(stat -c %u files)" = "$(id -u)"; '
          'test "$(stat -c %g files)" = "$(id -g)"; '
          'mode=$(stat -c %a files); test $((0$mode & 2)) -eq 0; cd files; '
          f'test ! -e {INCOMING}; test ! -L {INCOMING}; test ! -e {ROLLBACK}; test ! -L {ROLLBACK}; '
          f'test ! -e {AUDIT}; test ! -L {AUDIT}; test ! -L cb; '
          'if test -e cb; then test -d cb; fi')
    assert call('shell', 'sh', '-c', shlex.quote(f'if test -e {REMOTE} || test -L {REMOTE}; then echo exists; fi')) == ''
    save('PUSHING_LOSSLESS_ARCHIVE')
    call('push', str(archive), REMOTE, timeout=1200)
    call('shell', 'chmod', '644', REMOTE)
    assert call('shell', 'sha256sum', REMOTE, timeout=300).split()[0] == receipt['sha256']
    save('ARCHIVE_HASH_VERIFIED_EXTRACTING_NEW_TREE')
    shell(f'cd files; mkdir -m 700 {INCOMING}; cd {INCOMING}; tar -xof {REMOTE}', timeout=1200)
    save('VERIFYING_EVERY_EXTRACTED_FILE')
    observed = shell(f'cd files/{INCOMING}; '
        'if sha256sum -c SHA256SUMS > VERIFY.log 2>&1; then '
        'test "$(wc -l < SHA256SUMS)" -eq 20904; '
        'test "$(find active -type f | wc -l)" -eq 20903; '
        'test -z "$(find active -type l -print -quit)"; '
        'echo ALL_FILES_VERIFIED; else tail -n 8 VERIFY.log; exit 3; fi', timeout=1200)
    assert observed == 'ALL_FILES_VERIFIED'
    assert shell(f'cd files/{INCOMING}; sha256sum meta.cb').split()[0] == receipt['manifest_sha256']
    save('EXTRACTED_TREE_VERIFIED_SWITCH_PENDING')
    call('shell', 'am', 'force-stop', PACKAGE)
    assert not call('shell', 'sh', '-c', shlex.quote('pidof '+PACKAGE+' || true'))
    script = f'''test -d files; test ! -L files; cd files
test -d {INCOMING}/active; test -f {INCOMING}/meta.cb; test ! -L {INCOMING}
test ! -e {ROLLBACK}; test ! -L {ROLLBACK}; test ! -e {AUDIT}; test ! -L {AUDIT}; test ! -L cb
mkdir -m 700 {AUDIT}
mv {INCOMING}/SHA256SUMS {INCOMING}/VERIFY.log {AUDIT}/
trap 'if test -d {ROLLBACK} && test ! -L {ROLLBACK} && test ! -e cb && test ! -L cb; then mv {ROLLBACK} cb; fi' EXIT
if test -e cb; then test -d cb; mv cb {ROLLBACK}; fi
test ! -e cb
mv {INCOMING} cb
trap - EXIT
echo CACHE_SWITCH_COMMITTED
'''
    assert shell(script) == 'CACHE_SWITCH_COMMITTED'
    record.update(manifest_sha256=receipt['manifest_sha256'], version='7.0.255.25', files_verified=20903,
                  old_cache_retained=bool(shell(f'if test -d files/{ROLLBACK}; then echo yes; fi')),
                  rollback_relative_path='files/'+ROLLBACK, full_source_data_quality_preserved=True)
    save('LOCAL_BUNDLE25_CACHE_INSTALLED_COLD_NATIVE_ACCEPTANCE_PENDING')
    call('shell', 'rm', '-f', REMOTE)
    record['transport_temp_removed'] = True
    save('LOCAL_INSTALL_COMPLETE_NATIVE_START_PENDING')


if __name__ == '__main__':
    main()
