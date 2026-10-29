"""Bounded existing frame collector; no CLI polls or audio recorder in the window."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(os.environ["AKAINE_WORKSPACE"]).resolve()
OUT = Path('D:/AkaineBuilds/prod-rebase-20261025/performance-20261025')
ADB = 'W:/Not at home/drives/E/_organized/platform/android/Sdk/platform-tools/adb.exe'
HOSTS = {
    'v34': Path('D:/AkaineBuilds/prod-rebase-20261025/source/scripts/akaine_cli/akaine_stag.py'),
    'prod': ROOT/'work/prod-cli-speed-v9-20261022/client/akaine_prod.py',
}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    target, mode, label = sys.argv[1:]
    assert target in HOSTS and mode in ('high', 'cap60')
    assert label.replace('_', '').isalnum()
    serial = 'emulator-5556' if target == 'v34' else 'emulator-5558'
    OUT.mkdir(exist_ok=True)
    assert not (OUT/label).exists()
    sys.path.insert(0, str(HOSTS[target].parent))
    cli = load('matched_performance_host', HOSTS[target])
    adb = cli.Adb(ADB, serial)
    client = cli.Client(adb, 30)
    before = client.execute('status')
    assert before['ok'], before.get('error')
    state = before['state']
    assert state['gameplay'] and state['song_id'] == 'amega_daybreakfrontline' and state['difficulty'] == 2
    assert state['navigation']['paused'] is False and state['skill']['gameplay']['partner']['id'] == 0
    assert state['anomaly_replay'] is False
    expected = dict(audio_preset=0, highspeed_int=10, active_offset_ms=0, sfx_int=0,
                    high_framerate_v2=(mode == 'high'), performancemode_v2=False)
    assert all(state['settings'][k] == v for k, v in expected.items())
    devices = adb.call(['devices'], 10).stdout.decode().splitlines()
    assert sum(line.startswith('emulator-') for line in devices) == 1
    assert b'77cbb080a049c630dba3c5234c3480bd74df6dbf53189cb397982e5b1aeb2d32' in adb.call(
        ['shell', 'run-as', 'akai.arc.lmao', 'sha256sum', 'files/dl/amega_daybreakfrontline'], 15).stdout
    collector_path = ROOT/'work/emu-finish-20261025/capture_long.py'
    analyzer_path = ROOT/'work/perf-20261023/analyze_frames.py'
    assert hashlib.sha256(collector_path.read_bytes()).hexdigest() == '37c0873407fd296401b73985c8ab354994d4d4b616a39fb7c6c54ed55ed77d6f'
    assert hashlib.sha256(analyzer_path.read_bytes()).hexdigest() == 'cfc65c017987a3e9510602b7de0f2ffd2ba87011befddcde9dded1b597dfb207'
    capture = load('existing_frame_collector', collector_path)
    capture.SERIAL, capture.ROOT = serial, OUT
    original = capture.shell
    def shell(command, timeout=15):
        if command.startswith('simpleperf stat '):
            result = subprocess.run([ADB, '-s', serial, 'shell', command], capture_output=True, timeout=timeout)
            return result.stdout.decode(errors='replace') if result.returncode == 0 else 'CPU_COUNTERS_UNAVAILABLE\n'
        return original(command, timeout)
    capture.shell = shell
    mem_before = original('dumpsys meminfo akai.arc.lmao')
    capture.capture(label, seconds=30, interval_seconds=.25)
    # The legacy V9 host does not reset Client's deadline between calls.
    after = cli.Client(adb, 30).execute('status')
    assert after['ok'] and after['state']['gameplay'] and after['state']['navigation']['paused'] is False
    assert after['state']['song_id'] == state['song_id'] and after['state']['difficulty'] == 2
    assert after['session'] == before['session']
    mem_after = original('dumpsys meminfo akai.arc.lmao')
    report = load('existing_frame_analyzer', analyzer_path).analyze_path(OUT/label)
    report['complete_rolling_coverage'] = not report['non_overlapping_snapshot_pairs']
    assert report['complete_rolling_coverage'], 'Frame ring-buffer coverage gap; metrics not accepted'
    (OUT/label/'FRAME_STATS.json').write_text(json.dumps(report, indent=2)+'\n')
    (OUT/label/'CONTROL_BEFORE.json').write_text(json.dumps(before, indent=2)+'\n')
    (OUT/label/'CONTROL_AFTER.json').write_text(json.dumps(after, indent=2)+'\n')
    (OUT/label/'MEM_BEFORE.txt').write_text(mem_before)
    (OUT/label/'MEM_AFTER.txt').write_text(mem_after)
    print(json.dumps({'status': 'MATCHED_GAMEPLAY_FRAME_WINDOW_VERIFIED', 'target': target, 'mode': mode,
                      'label': label, 'refresh_hz': report['refresh_hz'], 'metrics': report['metrics'],
                      'complete_rolling_coverage': True, 'microphone_or_note_input': False}))


if __name__ == '__main__':
    main()
