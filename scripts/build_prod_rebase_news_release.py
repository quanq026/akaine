"""V36 sibling bindings; reuse the five-payload engine without changing V34/V35."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path

import build_news_core
import build_prod_rebase_news_core as news_core
import build_prod_rebase_release as release

PROFILE = release.ROOT / 'patches/arcaea-7.0.255-arm64/prod-rebase-news-v36-source-lock.json'
CHECKOUT = PROFILE.with_name('prod-rebase-news-v36-checkout-sources.json')
PLAN = PROFILE.with_name('prod-rebase-news-v36-plan.json')


@contextmanager
def bindings():
    previous = release.PROFILE, release.CHECKOUT, release.PLAN, release.build_prod_rebase_core, release.ACTIVE_MODULES
    release.PROFILE, release.CHECKOUT, release.PLAN = PROFILE, CHECKOUT, PLAN
    release.build_prod_rebase_core = news_core
    release.ACTIVE_MODULES = (*release.ACTIVE_MODULES, build_news_core, news_core)
    try:
        yield
    finally:
        release.PROFILE, release.CHECKOUT, release.PLAN, release.build_prod_rebase_core, release.ACTIVE_MODULES = previous


def verify(lock, paths):
    rows = release.verify(lock, paths)
    release.verify_active_inputs(lock, paths, (Path(__file__),))
    return rows


class PayloadsReady(Exception):
    """Internal stop after existing five-payload/asset checks, before APK assembly."""


def payloads_only(lock, paths, output):
    output = Path(output)
    original = release.build_android_client.build
    captured = {}

    def stop_before_apk(base, plan, kit, target):
        expected = release.expected_payloads(lock)
        actual = {name: release.digest(Path(kit) / 'final/payload' / name) for name in expected}
        if actual != expected or Path(target).exists():
            raise ValueError('V36 payload stop contract differs')
        captured.update(payload_sha256=actual, base_APK_sha256=release.digest(base))
        raise PayloadsReady()

    release.build_android_client.build = stop_before_apk
    try:
        release.build(lock, paths, output)
    except PayloadsReady:
        verify(lock, paths)
        result = dict(status='FIVE_SOURCE_PAYLOADS_MATCH_NO_APK_ASSEMBLED',
                      source_lock_sha256=release.digest(PROFILE), checkout_map_sha256=release.digest(CHECKOUT),
                      core_provenance=json.loads((output / 'core/BUILD_RECEIPT.json').read_bytes()),
                      APK_assembled=False, signed=False, device_or_server_actions=False, **captured)
        (output / 'PAYLOADS_ONLY_RECEIPT.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
        return result
    finally:
        release.build_android_client.build = original
    raise ValueError('Existing release engine did not reach the payload stop')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('verify', 'payloads', 'build'))
    parser.add_argument('--local-paths', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    with bindings():
        lock = json.loads(PROFILE.read_bytes())
        paths = release.bound_paths(lock, json.loads(args.local_paths.read_bytes())['paths'])
        verify(lock, paths)
        if args.mode == 'verify':
            result = dict(status='V36_NEWS_SOURCE_INPUTS_VERIFIED', APK_assembled=False)
        else:
            if args.output is None:
                parser.error('A fresh physical-D output is required')
            result = payloads_only(lock, paths, args.output) if args.mode == 'payloads' else release.build(lock, paths, args.output)
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
