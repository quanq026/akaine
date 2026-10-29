"""Add the finite News10 stage after a fresh authentic-production core rebuild."""
import copy
import json
from pathlib import Path
import shutil

import build_news_core
import build_prod_rebase_core as baseline
import build_release_profile as shared

PROD_APK_SHA = baseline.PROD_APK_SHA
PROD_CORE_SHA = baseline.PROD_CORE_SHA
STAGING_INPUT_SHA = baseline.STAGING_INPUT_SHA


def build(prod_apk, kit, output, llvm):
    kit, output = Path(kit), Path(output)
    shared.physical_output(output)
    output.mkdir(parents=True)
    # Only core sources/pins enter this view. No loader header is opened or copied.
    normal_kit = output / 'normal-kit'
    for name in ('retained-build', 'reset-baseline', 'integrity'):
        shutil.copytree(kit / name, normal_kit / name)
    for name in ('owned_gates.S', 'reset_gate.S'):
        target = normal_kit / 'semantic/owned' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(kit / 'semantic/owned' / name, target)
    for source, target in (
        (kit / 'news-baseline/semantic/owned/owned_core_pins.h', normal_kit / 'semantic/owned/owned_core_pins.h'),
        (kit / 'semantic/song-v9/cli_song_pins.h', normal_kit / 'semantic/song-v9/cli_song_pins.h'),
    ):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    normal, normal_pins, original = baseline.build(prod_apk, normal_kit, output / 'normal', llvm)
    core, pins, news = build_news_core.build(normal, normal_pins, kit / 'news/news_gates.S', output / 'news', llvm)
    for name, role in (('owned_core_pins.h', 'semantic/owned/owned_core_pins.h'),
                       ('cli_song_pins.h', 'semantic/song-v9/cli_song_pins.h')):
        if shared.digest(pins / name) != shared.digest(kit / role):
            raise ValueError('V36 regenerated final private pins differ')
    receipt = copy.deepcopy(original)
    receipt.update(core=str(core), core_sha256=shared.digest(core), private_pins=str(pins),
                   normal_core_provenance=original, news_extension=news,
                   builder_sha256=shared.digest(Path(__file__)))
    receipt['accounting'].update(final_core_sha256=shared.digest(core),
                                 freshly_rebuilt_normal_core_sha256=original['core_sha256'],
                                 news_extension=news)
    (output / 'BUILD_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8', newline='\n')
    return core, pins, receipt
