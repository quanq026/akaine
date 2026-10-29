"""Execute the reviewed smali branches with synthetic clocks; no Android calls."""
from pathlib import Path
import math
import re
import struct
import unittest

HERE = Path(__file__).resolve().parent
PERIOD = 16_666_668


def signed(value):
    return (value + (1 << 63)) % (1 << 64) - (1 << 63)


def execute(name, interval, now, last, oversleep=0, sleep_error=False, video=False):
    source = (HERE / name).read_text()
    lines = [line.split('#', 1)[0].strip() for line in source.splitlines()]
    lines = [line for line in lines if line and not line.startswith('.')]
    labels = {line: index for index, line in enumerate(lines) if line.startswith(':')}
    registers = {'p0': 'renderer'}
    state = {'interval': interval, 'last': last, 'now': now, 'video': video, 'frames': 0,
             'render': 0, 'monitor': 0, 'texture': 0, 'sleep': []}
    pc, returned, steps = 0, None, 0
    while pc < len(lines):
        steps += 1
        if steps > 150: raise AssertionError('Unexpected loop in draw callback')
        line = lines[pc]; pc += 1
        if line.startswith(':'): continue
        op, *tail = line.split(' ', 1)
        args = [value.strip() for value in tail[0].split(',')] if tail else []
        if op in ('const-wide/16', 'const-wide/32', 'const-wide', 'const/4'):
            registers[args[0]] = int(args[1].rstrip('L'), 16)
        elif op == 'sget-wide': registers[args[0]] = state['interval']
        elif op == 'long-to-double': registers[args[0]] = float(registers[args[1]])
        elif op in ('cmp-long', 'cmpg-double'):
            left, right = registers[args[1]], registers[args[2]]
            if op == 'cmpg-double': right = struct.unpack('<d', struct.pack('<Q', right))[0]
            registers[args[0]] = (left > right) - (left < right)
        elif op in ('if-eqz', 'if-gtz', 'if-gez', 'if-lez', 'if-ltz'):
            value = registers[args[0]]
            branch = {'if-eqz': value == 0, 'if-gtz': value > 0, 'if-gez': value >= 0,
                      'if-lez': value <= 0, 'if-ltz': value < 0}[op]
            if branch: pc = labels[args[1]]
        elif op == 'goto': pc = labels[args[0]]
        elif op == 'move-result-wide': registers[args[0]] = returned
        elif op == 'move-wide': registers[args[0]] = registers[args[1]]
        elif op == 'move-exception': registers[args[0]] = 'synthetic sleep exception'
        elif op == 'long-to-int': registers[args[0]] = int(registers[args[1]])
        elif op == 'iget-wide': registers[args[0]] = state['last']
        elif op == 'iput-wide': state['last'] = registers[args[0]]
        elif op == 'iget': registers[args[0]] = state['frames']
        elif op == 'iput': state['frames'] = registers[args[0]]
        elif op == 'iget-boolean': registers[args[0]] = state['video']
        elif op == 'iput-boolean': state['video'] = bool(registers[args[0]])
        elif op == 'iget-object': registers[args[0]] = 'synthetic texture'
        elif op == 'add-int/lit8': registers[args[0]] = registers[args[1]] + int(args[2], 16)
        elif op in ('add-long/2addr', 'sub-long/2addr', 'div-long/2addr', 'rem-long/2addr'):
            left, right = registers[args[0]], registers[args[1]]
            value = {'add-long/2addr': lambda: signed(left + right), 'sub-long/2addr': lambda: signed(left - right),
                     'div-long/2addr': lambda: left // right, 'rem-long/2addr': lambda: left % right}[op]()
            registers[args[0]] = value
        elif op in ('sub-long', 'div-long'):
            left, right = registers[args[1]], registers[args[2]]
            registers[args[0]] = signed(left - right) if op == 'sub-long' else left // right
        elif op == 'invoke-static':
            target = line.split('}, ', 1)[1]
            if target.endswith('System;->nanoTime()J'): returned = state['now']
            elif 'Thread;->sleep' in target:
                names = line[line.index('{') + 1:line.index('}')].split(',')
                names = [value.strip() for value in names]
                milliseconds = registers[names[0]]
                nanos = registers[names[2]] if target.endswith('(JI)V') else 0
                assert milliseconds >= 0 and 0 <= nanos < 1_000_000
                state['sleep'].append((milliseconds, nanos))
                if sleep_error:
                    pc = labels[':cap60_sleep_error' if target.endswith('(JI)V') else ':catch_2e']
                else: state['now'] = signed(state['now'] + milliseconds * 1_000_000 + nanos + oversleep)
            elif target.endswith('Cocos2dxRenderer;->nativeRender()V'): state['render'] += 1
            elif target.endswith('AnomalyMonitor;->frame()V'): state['monitor'] += 1
            else: raise AssertionError('Unexpected static call: ' + target)
        elif op == 'invoke-virtual':
            assert line.endswith('SurfaceTexture;->updateTexImage()V'); state['texture'] += 1
        elif op == 'return-void': return state
        else: raise AssertionError('Unmodeled instruction: ' + line)
    raise AssertionError('Draw callback did not return')


class Cap60PacingTests(unittest.TestCase):
    def candidate(self, **values): return execute('onDrawFrame.smali', **values)

    def test_phase_carry_and_full_nanosecond_sleep_request(self):
        last = 100_000_000
        for unused in range(1000):
            now = signed(last + 8_333_333)
            result = self.candidate(interval=PERIOD, now=now, last=last, oversleep=300_000)
            self.assertEqual(result['last'], signed(last + PERIOD))
            self.assertEqual(result['sleep'], [(8, 333_335)])
            self.assertEqual((result['render'], result['monitor']), (1, 1))
            last = result['last']
        self.assertEqual(last, 100_000_000 + 1000 * PERIOD)

    def test_one_period_late_resets_without_catchup_render(self):
        for lag in (PERIOD, PERIOD * 1000):
            now = 100_000_000 + PERIOD + lag
            result = self.candidate(interval=PERIOD, now=now, last=100_000_000)
            self.assertEqual(result['last'], now)
            self.assertEqual(result['sleep'], [])
            self.assertEqual((result['render'], result['monitor']), (1, 1))
        almost = self.candidate(interval=PERIOD, now=100_000_000 + 2 * PERIOD - 1, last=100_000_000)
        self.assertEqual(almost['last'], 100_000_000 + PERIOD)

    def test_first_entry_after_fast_mode_stale_tick_is_bounded(self):
        result = self.candidate(interval=PERIOD, now=30_000_000_000, last=1)
        self.assertEqual(result['sleep'], [])
        self.assertEqual(result['last'], 30_000_000_000)
        self.assertEqual((result['render'], result['monitor']), (1, 1))

    def test_sleep_error_anchors_actual_time_and_preserves_video_update(self):
        result = self.candidate(interval=PERIOD, now=108_333_333, last=100_000_000, sleep_error=True, video=True)
        self.assertEqual(result['last'], 108_333_333)
        self.assertEqual((result['render'], result['monitor'], result['texture'], result['video']), (1, 1, 1, False))

    def test_noncanonical_intervals_are_exact_legacy_execution(self):
        for interval in (0, -1, 6_944_444, 8_333_334, 11_111_111, 16_666_666, 16_666_669, 33_333_336):
            for failure in (False, True):
                values = dict(interval=interval, now=108_333_333, last=100_000_000, oversleep=300_000, sleep_error=failure, video=True)
                self.assertEqual(self.candidate(**values), execute('baseline_onDrawFrame.smali', **values))

    def test_signed_monotonic_wrap_preserves_short_elapsed_interval(self):
        last = (1 << 63) - 10_000_000
        now = last + 2_000_000
        result = self.candidate(interval=PERIOD, now=now, last=last)
        self.assertEqual(result['last'], signed(last + PERIOD))
        self.assertEqual(result['sleep'], [(14, 666_668)])

    def test_template_preserves_original_regions_exactly(self):
        before = (HERE / 'baseline_onDrawFrame.smali').read_text()
        after = (HERE / 'onDrawFrame.smali').read_text()
        self.assertIn('const-wide/32 v2, 0xfe502c\n    cmp-long v4, v0, v2\n    if-eqz v4, :cap60_pacing', after)
        removed = re.sub(r'\n    :cap60_pacing\n.*?\n    \.line 143', '\n    .line 143', after, flags=re.S)
        removed = removed.replace('    .registers 10\n', '    .registers 6\n', 1)
        removed = removed.replace('\n    const-wide/32 v2, 0xfe502c\n    cmp-long v4, v0, v2\n    if-eqz v4, :cap60_pacing\n', '', 1)
        removed = re.sub(r'(AnomalyMonitor;->frame\(\)V)\n\s*goto :goto_3a\n(\s*\.line 143)', r'\1\n\2', removed)
        self.assertEqual([line for line in removed.splitlines() if line.strip()],
                         [line for line in before.splitlines() if line.strip()])
        self.assertEqual(after.count('->nativeRender()V'), 3)  # One on each mutually exclusive path.
        self.assertEqual(after.count('AnomalyMonitor;->frame()V'), 3)
        self.assertNotIn('getDisplayRefreshRate', after)
        self.assertNotIn('Choreographer', after)


if __name__ == '__main__': unittest.main()
