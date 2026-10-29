"""Verify the historical source archive offline; never imports deployment code."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    provenance = json.loads((HERE / 'PROVENANCE.json').read_bytes())
    code = provenance['deployed_source_files']
    assert len(code) == 12
    assert set(p.relative_to(HERE).as_posix() for p in (HERE / 'server-overlay').rglob('*.py')) == set(code)
    exact = sanitized = compiled = 0
    for name, row in {**code, **provenance['archive_files']}.items():
        path = HERE / name
        assert path.resolve().is_relative_to(HERE) and not path.is_symlink()
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row['archive_sha256'], name
        if path.suffix == '.py':
            compile(raw, name, 'exec'); compiled += 1
        if name in code:
            if row['byte_identical_to_deployed_source']:
                assert row['archive_sha256'] == row['deployed_sha256']; exact += 1
            else:
                assert name == 'server-overlay/core/config_manager.py'
                tree = ast.parse(raw)
                owner = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Config')
                assignments = {n.targets[0].id: n.value for n in owner.body if isinstance(n, ast.Assign)}
                for key in ('SECRET_KEY', 'LINKPLAY_TCP_SECRET_KEY'):
                    assert ast.literal_eval(assignments[key]) == ''
                assert row['allowed_AST_difference'] == ['Config.LINKPLAY_TCP_SECRET_KEY literal redacted', 'Config.SECRET_KEY literal redacted']
                sanitized += 1
    spec = importlib.util.spec_from_file_location('repository_content_policy', ROOT / 'scripts/ci_public_repo_check.py')
    policy = importlib.util.module_from_spec(spec); spec.loader.exec_module(policy)
    files = [p for p in HERE.rglob('*') if p.is_file()]
    for path in files:
        assert path.name != 'config.py' and not path.name.startswith('.env')
        assert path.suffix.lower() not in policy.FORBIDDEN_SUFFIXES
        assert path.stat().st_size <= policy.MAX_BYTES
        raw = path.read_bytes()
        assert not policy.PRIVATE_KEY.search(raw) and not policy.AWS_ACCESS_KEY.search(raw) and not policy.R2_ACCESS_KEY.search(raw)
        assert not policy.hardcoded_python_secret(path, raw), path.relative_to(HERE)
    print(json.dumps({'status': 'PASS', 'deployed_sources': len(code), 'byte_identical_sources': exact,
        'sanitized_config_manager': sanitized, 'compiled_python_sources': compiled,
        'scoped_repository_content_check_files': len(files), 'network_or_deployment': False}))


if __name__ == '__main__':
    main()
