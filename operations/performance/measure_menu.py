"""Compare native menu confirmation latency; elapsed time includes ADB and CLI."""
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
import measure_fps as common


def main():
    target = sys.argv[1]
    assert target in common.HOSTS
    out = common.OUT/(target.upper()+'_MENU')
    assert not out.exists()
    sys.path.insert(0, str(common.HOSTS[target].parent))
    cli = common.load('matched_menu_host', common.HOSTS[target])
    adb = cli.Adb(common.ADB, 'emulator-5556' if target == 'v34' else 'emulator-5558')
    client = cli.Client(adb, 30)
    catalogue = cli.catalogue.load(adb, cli.Deadline(30))
    base_ids = sorted(row['id'] for row in catalogue['songs'] if row.get('set') == 'base')
    assert base_ids
    out.mkdir()
    events = []
    def run(command, argument='none', measured=False):
        started = time.monotonic_ns()
        # V9's host deadline belongs to Client, so each operation needs a fresh client.
        result = cli.Client(adb, 30).execute(command, argument)
        elapsed = (time.monotonic_ns()-started)/1e6
        events.append({'command': command, 'argument': argument, 'elapsed_ms': elapsed,
                       'measured': measured, 'response': result})
        (out/'EVENTS.json').write_text(json.dumps(events, indent=2)+'\n')
        assert result['ok'], result.get('error')
        return result['state']
    state = run('status')
    assert state['screen'] == 'song_select' and state['character']['equipped_id'] == 0
    assert state['settings']['high_framerate_v2'] is True
    summaries = []
    for pack in ('base', 'all'):
        state = run('ui', 'list')
        tokens = [r['token'] for r in state['ui']['actions'] if r['enabled'] and r['token'].startswith('pack_open.')]
        assert len(tokens) == 1
        run('ui', tokens[0]); state = run('pack_select', pack)
        assert state['song_selection']['pack_id'] == pack and not state['song_selection']['pack_open']
        count = state['song_selection']['native_list_count']
        run('filter', 'open'); run('filter', 'reset'); run('filter', 'close')
        start = len(events)
        for cycle in range(3):
            run('reverse', '1', True); run('reverse', '0', True)
            run('filter', 'open')
            state = run('filter', cli.encode_query('Alice'), True)
            assert state['filter']['query'] == 'Alice'
            state = run('filter', 'reset', True)
            assert state['filter']['query'] == ''
            run('filter', 'close')
        measured = [r for r in events[start:] if r['measured']]
        grouped = {}
        for r in measured:
            key = r['command']+(' reset' if (r['command'], r['argument']) == ('filter', 'reset') else '')
            grouped.setdefault(key, []).append(r['elapsed_ms'])
        stats = {key: {'samples': len(values), 'median_ms': statistics.median(values),
                        'maximum_ms': max(values)} for key, values in grouped.items()}
        summaries.append({'pack': pack, 'native_list_count': count, 'cycles': 3, 'stats': stats})
    state = run('song_select', 'amega_daybreakfrontline')
    result = {'status': 'BOUNDED_MENU_CONFIRMATION_LATENCIES_RECORDED', 'target': target,
              'bundle': catalogue['version'], 'base_pack_all_ids': base_ids,
              'base_pack_all_ids_sha256': hashlib.sha256('\n'.join(base_ids).encode()).hexdigest(),
              'workloads': summaries, 'end_selection': state['song_selection'],
              'scope': 'Host call through native confirmation includes ADB, locking, polling and snapshot reads. Not pure native execution time.',
              'all_songs_same_workload': False, 'no_automatic_notes_or_synthetic_scores': True}
    (out/'SUMMARY.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
