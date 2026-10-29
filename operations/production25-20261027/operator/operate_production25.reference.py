"""Prepare offline by default; apply requires a digest-bound independent PASS review."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import zlib

sys.dont_write_bytecode = True
HERE = Path(os.environ['AKAINE_PROD25_OPERATOR_DIR']).resolve()
BASE = HERE.parent
WORK = BASE.parent
CANONICAL = Path(__file__).resolve().parents[3]
MANIFEST = Path(os.environ['AKAINE_ORIGINAL25_MANIFEST']).resolve()
SELECTED_SHA = 'cb14fff35d83807c26f9337c5324e6b0b53eed5960e5837b991aace1e215aabd'
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def prepare():
    runtime = load('production25_runtime_offline', HERE / 'production25_runtime.py')
    raw = (HERE / 'SELECTED_PRODUCTION_DATA.json').read_bytes()
    assert sha(raw) == SELECTED_SHA, 'Selected Aurora-only data differs'
    data = json.loads(raw)
    live_raw = (BASE / 'LIVE_PREFLIGHT.json').read_bytes()
    live = json.loads(live_raw)
    assert live['read_only'] is True and live['instructions'] == {}
    assert data['source_preflight_sha256'] == sha(live_raw)
    prod, stage = (live['roots'][n] for n in ('production', 'staging'))
    assert prod['path'] == runtime.ROOT.as_posix() and stage['path'] == runtime.STAGE.as_posix()
    assert prod['safe_config']['SAVE_FULL_UNLOCK'] is True
    receipt = json.loads((HERE / 'CANDIDATE_FILES.json').read_bytes())
    tests = json.loads((HERE / 'CANDIDATE_TESTS.json').read_bytes())
    assert tests['status'] == 'PASS' and tests['failures'] == tests['errors'] == 0
    assert tests['candidate_files_receipt_sha256'] == sha((HERE / 'CANDIDATE_FILES.json').read_bytes())
    assert receipt['preflight_sha256'] == sha(live_raw)
    config = json.loads((HERE / 'CONFIG_ADDITIONS.json').read_bytes())
    code, guards = {}, {}
    for name, pin in receipt['files'].items():
        raw = (HERE / 'candidates' / name).read_bytes()
        assert sha(raw) == pin['candidate_sha256']
        assert pin['before_sha256'] == prod['hashes'].get(name)
        code[name] = base64.b64encode(raw).decode('ascii')
        source = CANONICAL / 'server' / name
        assert source.is_file(), 'Missing canonical dependency'
        guards[str(source)] = sha(source.read_bytes())
    for path in (CANONICAL / 'docs/rebase/NON_APK_LEDGER.json',
                 CANONICAL / 'docs/bundles/prod18-aurora-original25-online.json',
                 HERE / 'SELECTED_PRODUCTION_DATA.json', HERE / 'CONFIG_ADDITIONS.json',
                 HERE / 'CANDIDATE_FILES.json', HERE / 'CANDIDATE_TESTS.json', BASE / 'LIVE_PREFLIGHT.json'):
        guards[str(path)] = sha(path.read_bytes())
    publication_pins = json.loads((CANONICAL / 'docs/bundles/prod18-aurora-original25-online.json').read_bytes())['CDN_full_GET']
    expected_publication = []
    prefix = '7.0.255-staging-prod18-aurora-original-base25-20261026'
    for row in publication_pins:
        suffix = row['file'].removeprefix(prefix)
        assert suffix == '.json' or suffix in ['_' + str(i) + '.cb' for i in range(10)]
        expected_publication.append({'key': 'bundle/' + runtime.ALIAS + suffix, 'bytes': row['bytes'], 'sha256': row['sha256']})
    assert len(expected_publication) == 11
    p = {'alias': runtime.ALIAS, 'operation_id': datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-before-prod25'),
         'manifest': base64.b64encode(MANIFEST.read_bytes()).decode('ascii'), 'manifest_sha256': runtime.MANIFEST_SHA,
         'code': code, 'code_hashes': {n: v['candidate_sha256'] for n, v in receipt['files'].items()},
         'settings': config['config_assignments'], 'catalog': config['install_catalog'], 'data': data,
         'prod_hashes': prod['hashes'], 'stage_hashes': stage['hashes'], 'services': live['services'],
         'prod_manifests': {n: v['sha256'] for n, v in prod['manifests'].items()},
         'stage_manifests': {n: v['sha256'] for n, v in stage['manifests'].items()},
         'prod_api': live['local_bundle_API']['production']['0.0.0'], 'stage_api': live['local_bundle_API']['staging']['0.0.0'],
         'prod_charts': prod['chart_rows'], 'user_item_schema': prod['DB_schema']['user_item']}
    runtime.validate_parameters(p)
    params = json.dumps(p, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    assert len(params) < 16 * 1024 * 1024
    (HERE / 'OPERATION_PARAMETERS.json').write_bytes(params)
    plan = {'status': 'PREPARED_OFFLINE_INDEPENDENT_REVIEW_REQUIRED', 'operation_sha256': sha(Path(__file__).read_bytes()),
            'runtime_sha256': sha((HERE / 'production25_runtime.py').read_bytes()), 'parameters_sha256': sha(params),
            'test_source_sha256': sha((HERE / 'test_production25_operator.py').read_bytes()),
            'local_dependency_hashes': guards, 'publication_expected': expected_publication,
            'source_files': len(code), 'all_candidate_targets_including_catalog_config_metadata': 17,
            'new_chart_rows': 1532, 'stage_DB_copied': False, 'runtime_config_secrets_leave_server': False}
    (HERE / 'OPERATION_PLAN.json').write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: plan[k] for k in ('status', 'operation_sha256', 'runtime_sha256', 'parameters_sha256', 'source_files')}))
    return plan


def publication_gate(expected):
    publication = json.loads((BASE / 'BUNDLE_PUBLICATION.json').read_bytes())
    assert publication['status'] == 'NEW_IMMUTABLE_PRODUCTION_BUNDLE25_OBJECTS_READY_NOT_ACTIVATED'
    assert publication['alias'] == '7.0.255-prod-original-base25-20261027' and publication['version'] == '7.0.255.25'
    assert publication['manifest_sha256'] == '6e079c075bfa7d412fff06f188d26191656496599e28288722f3cfb58ac23891'
    assert publication['parts'] == 10 and publication['total_bytes'] == 4538288896
    assert publication['existing_objects_overwritten'] is False and publication['server_changed'] is False
    rows = publication['rows']
    assert len(rows) == 11 and len({r['key'] for r in rows}) == 11
    actual = {r['key']: {k: r[k] for k in ('key', 'bytes', 'sha256')} for r in rows}
    assert actual == {r['key']: r for r in expected} and all(r['CDN_full_GET_verified'] is True for r in rows)


def apply(review_path, review_sha):
    raw_review = review_path.read_bytes(); assert sha(raw_review) == review_sha
    review = json.loads(raw_review); assert review['status'] == 'PASS' and not review.get('findings')
    plan_raw = (HERE / 'OPERATION_PLAN.json').read_bytes(); plan = json.loads(plan_raw)
    assert review['plan_sha256'] == sha(plan_raw)
    for key, path in (('operation_sha256', Path(__file__)), ('runtime_sha256', HERE / 'production25_runtime.py'),
                      ('test_source_sha256', HERE / 'test_production25_operator.py'), ('parameters_sha256', HERE / 'OPERATION_PARAMETERS.json')):
        assert review[key] == plan[key] == sha(path.read_bytes()), 'Reviewed operation changed'
    tests_raw = (HERE / 'OPERATOR_TESTS.json').read_bytes(); tests = json.loads(tests_raw)
    assert review['tests_receipt_sha256'] == sha(tests_raw) and tests['status'] == 'PASS'
    assert tests['operation_sha256'] == plan['operation_sha256'] and tests['runtime_sha256'] == plan['runtime_sha256']
    for name, digest in plan['local_dependency_hashes'].items():
        assert sha(Path(name).read_bytes()) == digest, 'Canonical or local dependency changed'
    publication_gate(plan['publication_expected'])
    params = (HERE / 'OPERATION_PARAMETERS.json').read_bytes(); p = json.loads(params)
    p['parameter_content_sha256'] = sha(params)
    encoded = base64.b64encode(zlib.compress(json.dumps(p, ensure_ascii=True, separators=(',', ':')).encode(), 9)).decode()
    runtime = (HERE / 'production25_runtime.py').read_text(encoding='utf-8')
    payload = ('import base64,json,zlib\nP=json.loads(zlib.decompress(base64.b64decode(' + repr(encoded) + ')))\n' +
               runtime + '\nprint(json.dumps(run(P)))\n')
    compile(payload, '<independently-reviewed-production25>', 'exec')
    transport = load('reviewed_production25_transport', WORK / 'official32-prod-20261016/read_arghena_prod.py')
    transport.HERE = BASE
    with transport.connection('prod25-reviewed-promotion', production_write=True) as client:
        result = transport.execute(client, payload, timeout=300)
    (HERE / 'PRODUCTION_ACTIVATION.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('status', 'deployed', 'backup')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--dryrun', action='store_true')
    parser.add_argument('--review', type=Path)
    parser.add_argument('--review-sha256')
    args = parser.parse_args()
    if args.apply:
        assert args.review and args.review_sha256, 'Independent digest-bound review required'
        apply(args.review, args.review_sha256)
    else:
        prepare()
        if args.dryrun:
            subprocess.run([sys.executable, '-B', str(HERE / 'test_production25_operator.py')], check=True)
