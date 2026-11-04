"""Prepare a candidate 7.1 source adapter; unresolved authored bindings block compilation."""
from pathlib import Path
import hashlib
import json
import re
import shutil

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
HEX = re.compile(r'\b0x[0-9a-fA-F]+\b')
SETTINGS_INSTANCE_SLOT = 0x1c04ca0
FIELD_EDITS = {
    'semantic/native/anomaly_monitor_mod.cpp': (
        ('bool initialize_toggle() {', 'bool initialize_toggle(ToggleMailbox* candidate) {'),
        ('toggle_mailbox = reinterpret_cast<ToggleMailbox*>(module.base + TOGGLE_MAILBOX_VA);\n'
         '    ToggleMailbox zero_mailbox = {};\n'
         '    if (memcmp(toggle_mailbox, &zero_mailbox, sizeof(zero_mailbox)) != 0)',
         'auto* published = reinterpret_cast<ToggleMailbox*>(module.base + TOGGLE_MAILBOX_VA);\n'
         '    ToggleMailbox zero_mailbox = {};\n'
         '    if (memcmp(published, &zero_mailbox, sizeof(zero_mailbox)) != 0)'),
        ('    toggle_mailbox->disabled = enabled ? 0 : 1;',
         '    toggle_mailbox = candidate;\n'
         '    toggle_mailbox->disabled = enabled ? 0 : 1;'),
        ('if (!preference_ready || !pthread_equal(owner, pthread_self()) || !toggle_mailbox) return 1;',
         'if (!preference_ready || state != State::Ready || !pthread_equal(owner, pthread_self()) || !toggle_mailbox) return 1;'),
        ('void frame() {',
         'bool initialize_bridges() {\n'
         '    ToggleMailbox candidate = {};\n'
         '    if (!initialize_toggle(&candidate) || !initialize_official_bridge() || !initialize_mod_bridge()) {\n'
         '        preference_ready = false;\n'
         '        toggle_mailbox = nullptr;\n'
         '        return false;\n'
         '    }\n'
         '    auto* published = reinterpret_cast<ToggleMailbox*>(module.base + TOGGLE_MAILBOX_VA);\n'
         '    Address getter = candidate.getter;\n'
         '    candidate.getter = 0;\n'
         '    memcpy(published, &candidate, sizeof(candidate));\n'
         '    toggle_mailbox = published;\n'
         '    __atomic_store_n(&published->getter, getter, __ATOMIC_RELEASE);\n'
         '    return true;\n'
         '}\n\nvoid frame() {'),
        ('(!initialize_toggle() || !initialize_official_bridge() || !initialize_mod_bridge())',
         '!initialize_bridges()'),
        ('void sample_scene() {',
         'void reject_bridge() {\n'
         '    state = State::Rejected;\n'
         '    preference_ready = false;\n'
         '    if (toggle_mailbox) __atomic_store_n(&toggle_mailbox->getter, Address(0), __ATOMIC_RELEASE);\n'
         '}\n\nvoid sample_scene() {'),
        ('state = State::Rejected;\n'
         '        __android_log_print(ANDROID_LOG_ERROR, TAG, "diagnostic_disabled reason=director_read_bounds");',
         'reject_bridge();\n'
         '        __android_log_print(ANDROID_LOG_ERROR, TAG, "diagnostic_disabled reason=director_read_bounds");'),
        ('state = State::Rejected;\n'
         '        __android_log_print(ANDROID_LOG_ERROR, TAG, "diagnostic_disabled reason=director_vtable_guard");',
         'reject_bridge();\n'
         '        __android_log_print(ANDROID_LOG_ERROR, TAG, "diagnostic_disabled reason=director_vtable_guard");'),
        ('if (state == State::Ready && !initialize_bridges()) state = State::Rejected;',
         'if (state == State::Ready && !initialize_bridges()) reject_bridge();'),
        ('state = State::Rejected;\n    }\n    if (state != State::Ready) return;',
         'reject_bridge();\n    }\n    if (state != State::Ready) return;'),
        ('Address vtable = 0, getter = 0, setter = 0;\n'
         '    if (!process_readable(settings_instance, sizeof(Address))) return false;',
         'Address vtable = 0, getter = 0, setter = 0, current = 0;\n'
         f'    if (!static_pointer(module.base + {hex(SETTINGS_INSTANCE_SLOT)}, &current)\n'
         '        || !current || current != settings_instance) return false;\n'
         '    if (!process_readable(settings_instance, sizeof(Address))) return false;'),
        ('#include <pthread.h>', '#include <pthread.h>\n#include "sfx_bridge.h"'),
        ('void frame() {', 'void frame(JNIEnv* sfx_env) {'),
        ('        if (state == State::Ready && !initialize_bridges()) reject_bridge();',
         '        if (state == State::Ready && !initialize_bridges()) reject_bridge();\n'
         '        if (state == State::Ready && !sfx_bridge71::initialize(sfx_env)) {\n'
         '            __android_log_print(ANDROID_LOG_ERROR, "AkaineSfx", "bridge_rejected reason=%s", sfx_bridge71::reason);\n'
         '            reject_bridge();\n'
         '        }'),
        ('Java_low_moe_AnomalyMonitor_frameNative(JNIEnv*, jclass) {\n    frame();',
         'Java_low_moe_AnomalyMonitor_frameNative(JNIEnv* env, jclass) {\n    frame(env);'),
    ),
    'semantic/result/result_state.h': (
        ('override_score = h.get<unsigned char>(result + 0xb1)', 'override_score = h.get<unsigned char>(result + 0xb5)'),
        ('alternate_score = h.get<unsigned char>(result + 0xb0)', 'alternate_score = h.get<unsigned char>(result + 0xb4)'),
        ('zero_health_clear = h.get<unsigned char>(result + 0xb3)', 'zero_health_clear = h.get<unsigned char>(result + 0xb7)'),
    ),
    'semantic/owned/owned_pack_module.cpp': (
        ('reserved && ordered_count <= 64', 'reserved && ordered_count <= 100'),
        ('manager + 0x288', 'manager + 0x3a8'),
        ('bounded_shadow=64', 'bounded_shadow=100'),
        ('ph.p_vaddr == 0x1ba4920 && ph.p_filesz == 0x400b0\n'
         '                    && ph.p_memsz == 0x5e920',
         'ph.p_vaddr == OWNED_RW_SEGMENT_VA && ph.p_filesz == OWNED_RW_FILE_SIZE\n'
         '                    && ph.p_memsz == OWNED_RW_MEMORY_SIZE'),
    ),
    'semantic/owned/dynamic_owned_store.h': (
        ('std::min({size_t{64}, capacity, value->ordered.size()})', 'std::min({size_t{100}, capacity, value->ordered.size()})'),
    ),
    'semantic/update/bundle_controls.h': (
        ('    if (length < 9 || length >= sizeof(out) || !h.readable(data, length + 1)) return false;\n'
         '    const char* text = reinterpret_cast<const char*>(data);\n'
         '    if (memcmp(text, "7.0.255.", 8) || text[length] || text[8] == \'0\') return false;\n'
         '    for (Size i = 8; i < length; ++i) if (text[i] < \'0\' || text[i] > \'9\') return false;',
         '    if (length < 7 || length > 15 || length >= sizeof(out) || !h.readable(data, length + 1)) return false;\n'
         '    const char* text = reinterpret_cast<const char*>(data);\n'
         '    if (memcmp(text, "7.1.0.", 6) || text[length] || text[6] == \'0\') return false;\n'
         '    for (Size i = 6; i < length; ++i) if (text[i] < \'0\' || text[i] > \'9\') return false;'),
    ),
    'semantic/overlays/overlay_state.h': (
        ('    Address node = 0, listener = 0, callback = 0, gate = 0, banner = 0;',
         '    Address node = 0, listener = 0, callback = 0, gate = 0, banner = 0;\n'
         '    Address advance_invoke = 0;'),
        ('inline View capture(Reader& h, Address scene, const char* klass) {',
         '#include "pack_tutorial.h"\n\ninline View capture(Reader& h, Address scene, const char* klass) {'),
        ('if (type == module.base + 0x1b20180 || type == module.base + 0x1b453b0) {',
         'if (type == module.base + 0x1b20180 || type == module.base + 0x1b453b0\n'
         '            || type == module.base + pack_tutorial71::VTABLE) {'),
        ('                    : progression(h, scene, current.node, current.visible, current.running, item))) {',
         '                    : type == module.base + pack_tutorial71::VTABLE\n'
         '                    ? pack_tutorial71::capture(h, scene, current.node, current.visible, current.running, item)\n'
         '                    : progression(h, scene, current.node, current.visible, current.running, item))) {'),
        ('    call.call<void>(0x1934b7c, item.callback);',
         '    if (item.advance_invoke) return pack_tutorial71::advance(h, item);\n'
         '    call.call<void>(0x1934b7c, item.callback);'),
        ('        || old.step_index != item.step_index || old.pending_steps != item.pending_steps) return "STALE_UI_CONTEXT";',
         '        || old.step_index != item.step_index || old.pending_steps != item.pending_steps\n'
         '        || old.advance_invoke != item.advance_invoke || old.gate != item.gate) return "STALE_UI_CONTEXT";'),
        (r'\"overlay_coverage\":[\"progression_guide\",\"note_speed_setup\"]',
         r'\"overlay_coverage\":[\"progression_guide\",\"note_speed_setup\",\"category_tutorial\",\"partner_tutorial\"]'),
    ),
    'semantic/native/cli_core.h': (
        ('"pack_hint_continue", "main_hint_continue"',
         '"pack_hint_continue", "partner_hint_continue", "main_hint_continue"'),
    ),
    'semantic/native/cli_ui_native.h': (
        ('        if (!tree.has_modal && overlay_cli::can_advance(result.overlays)) {',
         '        if ((!tree.has_modal || overlay_cli::pack_tutorial71::partner_modal_only(h, scene, tree, result.overlays))\n'
         '            && overlay_cli::can_advance(result.overlays)) {'),
        ('                : !strcmp(item.id, "main_menu_hint")',
         '                : !strcmp(item.id, "partner_selection_hint")\n'
         '                ? CliUiAction{"partner_hint_continue", "Continue partner selection guide", item.node, item.callback}\n'
         '                : !strcmp(item.id, "main_menu_hint")'),
    ),
    'semantic/native/cli_bridge.h': (
        ('bool guide_progressed(const overlay_cli::View& before, const overlay_cli::View& after) {',
         'bool guide_progressed(const overlay_cli::View& before, const overlay_cli::View& after) {\n'
         '    if (before.count == 1 && before.items[0].advance_invoke == overlay_cli::pack_tutorial71::TOUCH_INVOKE)\n'
         '        return overlay_cli::pack_tutorial71::progressed(before, after);'),
        ('!strncmp(pending.argument, "pack_hint_continue.", 19) || !strncmp(pending.argument, "main_hint_continue.", 19)',
         '!strncmp(pending.argument, "pack_hint_continue.", 19) || !strncmp(pending.argument, "partner_hint_continue.", 22)\n'
         '                || !strncmp(pending.argument, "main_hint_continue.", 19)'),
        ('!strcmp(action.name, "pack_hint_continue") || !strcmp(action.name, "main_hint_continue")',
         '!strcmp(action.name, "pack_hint_continue") || !strcmp(action.name, "partner_hint_continue")\n'
         '            || !strcmp(action.name, "main_hint_continue")'),
        ('        if (!strcmp(request.argument, "open")) return character.dialog && character.select_callback && !character.blocked && !character.reason;',
         '        if (!strcmp(request.argument, "open")) {\n'
         '            if (character.dialog && character.select_callback && !character.blocked && !character.reason) return true;\n'
         '            Reader confirmation;\n'
         '            return overlay_cli::pack_tutorial71::character_open_completed(confirmation, value.scene, pending_scene,\n'
         '                value.ready, value.transition, value.ui, character);\n'
         '        }'),
    ),
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def transform(text, mappings, edits=()):
    for before, after in edits:
        if text.count(before) != 1:
            raise ValueError('Owner-specific source preimage differs')
        text = text.replace(before, after, 1)
    # Only ELF VA keys exist in this map; object offsets and size constants are excluded.
    return HEX.sub(lambda match: hex(mappings.get(int(match[0], 16), int(match[0], 16))), text)


def load_bindings(path=None):
    document = json.loads(Path(path or HERE / 'bindings.json').read_text(encoding='utf-8'))
    if (document.get('schema') != 'akaine.native-bindings.v1' or document.get('target_application') != '7.1.0'
            or document.get('target_core_sha256') != '849a7b1418ba389c007b0b2793510eb8e163b1268e8734b561a83b6c11c0773c'):
        raise ValueError('Exact reviewed 7.1 binding inventory required')
    mappings = {}
    for row in document['mappings']:
        old, new = int(row['old'], 16), int(row['new'], 16)
        if old < 0x400000 or new < 0x400000 or old in mappings or row['kind'] not in ('function_va', 'data_va'):
            raise ValueError('Duplicate or non-ELF binding in callable/data map')
        mappings[old] = new
    return document, mappings


def bridge_identity(text, environment):
    if environment not in ('staging', 'production'):
        raise ValueError('Exact runtime environment required')
    before = r'\"environment\":\"production\",\"package\":\"akai.arc.lmao\",\"pid\":'
    after = r'\"environment\":\"production\",\"package\":\"akai.arc.lmao\",\"application_version\":\"7.1.0\",\"pid\":'
    if text.count(before) != 1:
        raise ValueError('Exact bridge identity preimage required')
    text = text.replace(before, after, 1)
    if environment == 'staging':
        text = text.replace('akai.arc.lmao', 'akai.arc.lmao.staging').replace('production', 'staging')
    return text


def prepare(source_root, output, *, authored_addresses=None, environment='staging'):
    if environment not in ('staging', 'production'):
        raise ValueError('Exact runtime environment required')
    source_root, output = Path(source_root).absolute(), Path(output).absolute()
    for path in (source_root, output):
        for parent in (path, *path.parents):
            if parent.is_symlink() or parent.exists() and getattr(parent.stat(), 'st_file_attributes', 0) & 1024:
                raise ValueError('Source/output links and junctions are not allowed')
    if output.exists() or any(output.resolve().is_relative_to(root.resolve()) for root in (source_root, REPO)):
        raise ValueError('Fresh external runtime output required')
    binding_document, mapping = load_bindings()
    for old, new in (authored_addresses or {}).items():
        old, new = int(old, 0) if isinstance(old, str) else old, int(new, 0) if isinstance(new, str) else new
        if old in mapping or old < 0x400000 or new < 0x400000:
            raise ValueError('Authored address overlaps upstream binding or is not an ELF VA')
        mapping[old] = new
    lock = json.loads((source_root / 'SOURCE_INPUTS.json').read_text(encoding='utf-8'))
    declared = json.loads((HERE / 'source-inputs.json').read_text(encoding='utf-8'))['files']
    expected_lock = {row['target']: row['sha256'] for row in declared}
    if len(expected_lock) != len(declared) or lock != expected_lock:
        raise ValueError('Prepared source manifest differs from the committed source inventory')
    for relative, expected in lock.items():
        path = source_root / relative
        linked = any(parent.is_symlink() or parent.exists() and getattr(parent.stat(), 'st_file_attributes', 0) & 1024
                     for parent in (path, *path.parents))
        if linked or not path.is_file() or digest(path) != expected:
            raise ValueError('Prepared baseline source changed')
    tutorial_source = HERE / 'pack_tutorial.h'
    tutorial_raw = tutorial_source.read_bytes()
    tutorial_sha = hashlib.sha256(tutorial_raw).hexdigest()
    output.mkdir(parents=True)
    changes, unresolved = {}, []
    for relative, expected in lock.items():
        source, target = source_root / relative, output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if relative.startswith('semantic/') and source.suffix in ('.h', '.cpp'):
            before = source.read_text(encoding='utf-8')
            after = transform(before, mapping, FIELD_EDITS.get(relative, ()))
            if relative.endswith('native/cli_bridge.h'):
                after = bridge_identity(after, environment)
            for line, text in enumerate(after.splitlines(), 1):
                for token in HEX.finditer(text.split('//', 1)[0]):
                    value = int(token[0], 16)
                    if 0x782a50 <= value < 0x783000 or 0x1a7d4d0 <= value < 0x1a7e6a4 or 0x1c03140 <= value < 0x1c03240:
                        unresolved.append({'file': relative, 'line': line, 'old_authored_va': token[0]})
            target.write_text(after, encoding='utf-8', newline='\n')
            if after != before: changes[relative] = digest(target)
        else:
            shutil.copyfile(source, target)
    if any(digest(source_root / relative) != expected for relative, expected in lock.items()):
        raise ValueError('Baseline changed during runtime preparation')
    tutorial = output / 'semantic/overlays/pack_tutorial.h'
    tutorial.write_bytes(tutorial_raw)
    if digest(tutorial_source) != tutorial_sha or digest(tutorial) != tutorial_sha:
        raise ValueError('Typed tutorial source changed during runtime preparation')
    changes['semantic/overlays/pack_tutorial.h'] = tutorial_sha
    receipt = {'schema': 'akaine.port71.runtime-source-candidate.v1', 'upstream_binding_count': len(binding_document['mappings']),
               'environment': environment, 'application_version': '7.1.0',
               'applied_authored_mappings': len(authored_addresses or {}), 'changed_sources': changes,
               'unresolved_authored_references': unresolved, 'generated_pin_headers_pending': True,
               'all_abi_reviewed': False, 'compile_allowed': False, 'runtime_accepted': False,
               'limits': ['ELF VA adaptation and exact owner-field edits do not establish all ABI/lifetimes.',
                          'Actual compiled gate symbols and fresh generated pin headers are required before compilation.']}
    (output / 'PORT_RUNTIME_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return receipt
