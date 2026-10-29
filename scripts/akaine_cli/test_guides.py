"""Single-step native guide orchestration; no device, coordinates or consent."""
import contextlib
import copy
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import akaine_stag as cli
from test_akaine_stag import FakeAdb


def state(context="a" * 16):
    return {"screen": "song_select", "gameplay": False,
            "song_selection": {"song_id": "testify", "difficulty": 2, "selected_difficulty": 2},
            "ui": {"context": context, "modal_present": False, "reason": None, "actions": [],
                   "overlays": [], "overlay_scan_complete": True,
                   "overlay_coverage": list(cli.OVERLAY_COVERAGE), "guide_metadata_version": 1,
                   "onboarding_settings_ready": False, "note_speed_modal_ready": False},
            "advanced_guide": {"available": False, "can_skip": False, "reason": "not_present",
                               "priority": "unavailable", "song_id": None, "difficulty": None}}


def overlay(identifier="pack_selection_hint", **changes):
    item = {"kind": "tutorial", "id": identifier, "active": True, "visible": True,
            "opacity": 255, "blocks_input": True, "step_index": 1, "pending_steps": 3,
            "advance_ready": True, "can_advance": True, "can_set_speed": False,
            "owner_validated": True, "callback_owned": True, "listener_registered": True,
            "listener_paused": False, "listener_enabled": True, "listener_swallow": True}
    return {**item, **changes}


def hint(context="a" * 16, action=True, **changes):
    value = state(context)
    value["ui"].update(reason="input_blocked", overlays=[overlay(**changes)])
    if action:
        value["ui"]["actions"] = [{"token": "pack_hint_continue." + context,
                                   "name": cli.UI_LABELS["pack_hint_continue"], "enabled": True}]
    return value


def advanced():
    value = state()
    value["ui"]["modal_present"] = True
    value["advanced_guide"].update(available=True, can_skip=True, reason=None,
                                   priority="single_modal", song_id="testify", difficulty=2)
    return value


class GuideAdb(FakeAdb):
    """Reuse actual wire, deadline and lock fixture with a bounded response script."""
    def __init__(self, steps):
        super().__init__()
        self.steps = copy.deepcopy(steps)

    def run(self, arguments, input, stdout, stderr, timeout, check):
        script = " ".join(arguments)
        if self.pending and "head -c" in script and "response.json" in script:
            expected, response = self.steps.pop(0)
            assert tuple(self.pending[4:]) == expected, (self.pending[4:], expected)
            self.response_override = response
        return super().run(arguments, input, stdout, stderr, timeout, check)


def response(value, **changes):
    return {"state": value, **changes}


class GuideStatusTests(unittest.TestCase):
    def test_legacy_ui_stays_supported_but_guide_requires_explicit_metadata(self):
        for missing in ("guide_metadata_version", "advanced_guide"):
            value = state()
            (value["ui"] if missing == "guide_metadata_version" else value).pop(missing)
            cli.validate_ui(value)
            with self.subTest(missing=missing), self.assertRaises(cli.CliError) as caught:
                cli.guide_status(value)
            self.assertEqual(caught.exception.code, "UNSUPPORTED_GUIDE_METADATA")
        value = hint()
        for key in cli.GUIDE_FIELDS:
            value["ui"]["overlays"][0].pop(key)
        cli.validate_ui(value)
        with self.assertRaises(cli.CliError) as caught:
            cli.guide_status(value)
        self.assertEqual(caught.exception.code, "UNSUPPORTED_GUIDE_METADATA")

    def test_partial_or_ill_typed_workflow_metadata_fails_closed(self):
        for key in cli.GUIDE_FIELDS:
            value = hint()
            value["ui"]["overlays"][0].pop(key)
            with self.subTest(missing=key), self.assertRaises(cli.CliError):
                cli.guide_status(value)
        invalid = [("step_index", True), ("step_index", -1), ("step_index", 4097),
                   ("pending_steps", False), ("pending_steps", -1), ("pending_steps", 129)]
        invalid += [(key, 1) for key in cli.GUIDE_FIELDS - {"step_index", "pending_steps"}]
        for key, wrong in invalid:
            value = hint(**{key: wrong})
            with self.subTest(field=key, value=wrong), self.assertRaises(cli.CliError):
                cli.guide_status(value)
        for key in ("onboarding_settings_ready", "note_speed_modal_ready"):
            for wrong in (None, 0, 1, "true"):
                value = state(); value["ui"][key] = wrong
                with self.subTest(field=key, value=wrong), self.assertRaises(cli.CliError):
                    cli.guide_status(value)

    def test_hint_readiness_and_pending_steps_do_not_imply_completion(self):
        value = hint()
        result = cli.guide_status(value)
        self.assertEqual(result["status"], "action")
        self.assertEqual(result["action"], {"command": "ui", "argument": "pack_hint_continue." + "a" * 16})
        self.assertFalse(result["may_continue_play"])
        value = hint(action=False, advance_ready=False, can_advance=False, pending_steps=2)
        self.assertEqual(cli.guide_status(value)["status"], "wait")
        value = hint(action=False)
        self.assertEqual(cli.guide_status(value)["status"], "blocked")
        value = hint(action=False, active=False, blocks_input=False, advance_ready=False,
                     can_advance=False, pending_steps=0)
        self.assertEqual(cli.guide_status(value)["status"], "wait")
        self.assertEqual(cli.guide_status(state())["status"], "none")

    def test_hint_action_requires_owned_ready_callback(self):
        for key in ("can_advance", "owner_validated", "callback_owned", "advance_ready"):
            with self.subTest(field=key), self.assertRaises(cli.CliError):
                cli.guide_status(hint(**{key: False}))

    def test_unknown_ambiguous_and_incomplete_guides_block(self):
        value = hint(action=False, identifier="unknown_progression_guide")
        self.assertEqual(cli.guide_status(value)["reason"], "unknown_progression_guide")
        value = hint(action=False)
        value["ui"]["overlays"].append(overlay("main_menu_hint"))
        self.assertEqual(cli.guide_status(value)["reason"], "competing_guide_or_modal")
        value = state(); value["ui"]["overlay_scan_complete"] = False
        self.assertEqual(cli.guide_status(value)["reason"], "overlay_scan_incomplete")

    def test_advanced_guide_has_exact_selection_and_explicit_priority(self):
        value = advanced()
        result = cli.guide_status(value)
        self.assertEqual(result["action"], {"command": "play_guide", "argument": "testify"})
        self.assertTrue(result["may_continue_play"])
        for field, wrong in (("song_id", "other"), ("difficulty", 1), ("difficulty", True),
                             ("priority", "unproven"), ("reason", "input_blocked")):
            value = advanced(); value["advanced_guide"][field] = wrong
            with self.subTest(field=field), self.assertRaises(cli.CliError):
                cli.guide_status(value)
        for changes in ({}, {"active": False, "blocks_input": False}):
            value = advanced(); value["ui"]["overlays"] = [overlay(**changes)]
            value["advanced_guide"].update(can_skip=False, priority="unproven",
                                            reason="pack_hint_priority_unproven")
            result = cli.guide_status(value)
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["reason"], "pack_hint_priority_unproven")
            self.assertIsNone(result["action"])
            value["advanced_guide"].update(can_skip=True, priority="single_modal", reason=None)
            with self.assertRaises(cli.CliError):
                cli.guide_status(value)

    def test_note_speed_requires_exact_modal_and_owned_continuation(self):
        value = state()
        value["ui"].update(modal_present=True, note_speed_modal_ready=True,
            overlays=[overlay("note_speed_setup", can_advance=False, can_set_speed=True)])
        result = cli.guide_status(value)
        self.assertEqual(result["action"], {"command": "play_set_speed", "argument": "testify"})
        self.assertTrue(result["may_continue_play"])
        variants = []
        for key in ("can_set_speed", "owner_validated", "callback_owned"):
            other = copy.deepcopy(value); other["ui"]["overlays"][0][key] = False; variants.append(other)
        for key in ("modal_present", "note_speed_modal_ready"):
            other = copy.deepcopy(value); other["ui"][key] = False; variants.append(other)
        other = copy.deepcopy(value); other.pop("song_selection"); variants.append(other)
        for other in variants:
            self.assertEqual(cli.guide_status(other)["status"], "wait")

    def test_only_typed_onboarding_stages_and_exact_settings_can_advance(self):
        for stage, action in (("welcome", "onboarding_setup"), ("offset_setup", "onboarding_cancel"),
                              ("offset_skip_confirmation", "onboarding_skip")):
            value = state(); value["screen"] = "main_menu"
            value["ui"].update(modal_present=True, onboarding_stage=stage,
                actions=[{"token": action + "." + "a" * 16, "name": cli.UI_LABELS[action], "enabled": True}])
            self.assertEqual(cli.guide_status(value)["kind"], action)
        value = state(); value["screen"] = "main_menu"
        value["settings_control"] = {"open": True, "can_close": True}
        self.assertEqual(cli.guide_status(value)["status"], "none")
        value["ui"]["onboarding_settings_ready"] = True
        self.assertEqual(cli.guide_status(value)["action"], {"command": "settings", "argument": "close"})
        for malformed in (None, [], False, "open"):
            value["settings_control"] = malformed
            with self.subTest(control=malformed), self.assertRaises(cli.CliError) as caught:
                cli.guide_status(value)
            self.assertEqual(caught.exception.code, "PROTOCOL_ERROR")


class GuideClientTests(unittest.TestCase):
    def assert_requests(self, device, expected):
        self.assertEqual([tuple(item[4:]) for item in device.requests], expected)
        self.assertFalse(device.locked)
        scripts = [" ".join(call[0]) for call in device.calls]
        self.assertEqual(sum("mkdir -m 700" in item for item in scripts), 1)
        self.assertEqual(sum("rmdir" in item for item in scripts), 1)

    def test_status_reads_native_state_without_dispatching_action(self):
        device = GuideAdb([(("ui", "list"), response(hint()))])
        result = device.client().execute("guide", "status")
        self.assertTrue(result["ok"], result)
        self.assertIsNone(result["guide"]["performed"])
        self.assertEqual(result["guide"]["operation"], "status")
        self.assert_requests(device, [("ui", "list")])

    def test_one_ack_advances_one_step_and_does_not_claim_finished(self):
        first = hint()
        after = hint("b" * 16, step_index=2, pending_steps=2)
        action = ("ui", "pack_hint_continue." + "a" * 16)
        device = GuideAdb([(("ui", "list"), response(first)),
                           (("ui", "list"), response(first)), (action, response(after))])
        result = device.client().execute("guide", "next")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["guide"]["performed"], {"command": action[0], "argument": action[1]})
        self.assertEqual(result["guide"]["status"], "action")
        self.assertEqual(result["state"]["ui"]["overlays"][0]["pending_steps"], 2)
        self.assert_requests(device, [("ui", "list"), ("ui", "list"), action])
        self.assertEqual(device.steps, [])

    def test_stale_context_or_changed_decision_sends_no_action(self):
        for fresh, code in ((hint("b" * 16), "STALE_UI_CONTEXT"),
                            (hint(action=False, advance_ready=False, can_advance=False), "GUIDE_STATE_CHANGED")):
            device = GuideAdb([(("ui", "list"), response(hint())),
                               (("ui", "list"), response(fresh))])
            result = device.client().execute("guide", "next")
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"]["code"], code)
            self.assert_requests(device, [("ui", "list"), ("ui", "list")])

    def test_refreshes_share_one_deadline_and_timeout_never_starts_an_action(self):
        device = GuideAdb([(("ui", "list"), response(hint())),
                           (("ui", "list"), response(hint()))])
        device.transport_delay = 0.05
        result = device.client(timeout=1).execute("guide", "next")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "TIMEOUT")
        self.assertTrue(device.requests)
        self.assertTrue(all(tuple(item[4:]) == ("ui", "list") for item in device.requests))
        self.assert_requests(device, [("ui", "list")] * len(device.requests))

    def test_unknown_modal_terms_download_and_ordinary_play_never_auto_dispatch(self):
        values = [state()]
        values[0]["ui"]["actions"] = [{"token": "main_music." + "a" * 16, "name": "Music", "enabled": True}]
        for name in ("terms", "download", "unknown"):
            value = state(); value["ui"]["modal_present"] = True
            value["test_modal_kind"] = name  # Public metadata carries no authorizing guide action.
            values.append(value)
        value = hint(action=False, identifier="unknown_progression_guide"); values.append(value)
        for value in values:
            device = GuideAdb([(("ui", "list"), response(value))])
            result = device.client().execute("guide", "next")
            self.assertTrue(result["ok"], result)
            self.assertIsNone(result["guide"]["performed"])
            self.assertIsNone(result["guide"]["action"])
            self.assert_requests(device, [("ui", "list")])

    def test_notification_requests_os_prompt_once_and_reports_effect_without_grant(self):
        value = hint(action=False, identifier="notification_permission_guide")
        value["screen"] = "main_menu"
        value["ui"]["actions"] = [{"token": "notification_hint_continue." + "a" * 16,
            "name": cli.UI_LABELS["notification_hint_continue"], "enabled": True}]
        after = state("b" * 16); after["screen"] = "main_menu"
        action = ("ui", "notification_hint_continue." + "a" * 16)
        device = GuideAdb([(("ui", "list"), response(value)),
                           (("ui", "list"), response(value)), (action, response(after))])
        result = device.client().execute("guide", "next")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["guide"]["effect"], "requests_android_notification_permission")
        self.assertEqual(result["guide"]["performed"], {"command": action[0], "argument": action[1]})
        self.assert_requests(device, [("ui", "list"), ("ui", "list"), action])
        self.assertFalse(any("pm grant" in " ".join(call[0]) for call in device.calls))

    def test_failed_native_action_is_not_retried_or_reported_performed(self):
        action = ("ui", "pack_hint_continue." + "a" * 16)
        device = GuideAdb([(("ui", "list"), response(hint())), (("ui", "list"), response(hint())),
                           (action, response(hint(), ok=False, error={"code": "INPUT_BLOCKED", "message": "Fixture blocked."}))])
        result = device.client().execute("guide", "next")
        self.assertFalse(result["ok"])
        self.assertIsNone(result["guide"]["performed"])
        self.assertEqual(result["guide"]["attempted"]["command"], "ui")
        self.assert_requests(device, [("ui", "list"), ("ui", "list"), action])

    def test_advanced_skip_continues_only_existing_request_without_ordinary_play(self):
        before = advanced()
        device = GuideAdb([(("ui", "list"), response(before)), (("ui", "list"), response(before)),
                           (("play_guide", "testify"), response(state("b" * 16)))])
        result = device.client().execute("guide", "next")
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["guide"]["may_continue_play"])
        self.assertEqual(result["guide"]["status"], "none")
        self.assert_requests(device, [("ui", "list"), ("ui", "list"), ("play_guide", "testify")])

    def test_parser_exposes_only_status_and_single_next(self):
        for action in ("status", "next"):
            with patch.object(cli, "Client") as client, contextlib.redirect_stdout(io.StringIO()):
                client.return_value.execute.return_value = {"ok": True}
                self.assertEqual(cli.main(["--serial", "emulator-5556", "guide", action]), 0)
                self.assertEqual(client.return_value.execute.call_args.args[:2], ("guide", action))
        with patch.object(cli, "Client") as client, contextlib.redirect_stdout(io.StringIO()):
            self.assertNotEqual(cli.main(["--serial", "emulator-5556", "guide", "finish-all"]), 0)
            client.assert_not_called()


class NativeGuideFixtureTests(unittest.TestCase):
    def test_actual_advanced_guide_guards_with_disposable_synthetic_pins(self):
        compiler = shutil.which(os.environ.get("CXX", "g++"))
        if not compiler:
            self.skipTest("Installed host C++ compiler required; no dependency is installed by this test")
        runtime = Path(__file__).resolve().parents[2] / "patches/arcaea-7.0.255-arm64/runtime"
        headers = ("semantic/play/guide/play_guide.h", "semantic/play/confirm/play_confirm.h")
        fixture = "onboarding/test_advanced_guide.cpp"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (*headers, fixture):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((runtime / name).read_bytes())
            for folder, filename, name, offset in (
                    ("guide", "play_guide_pins.h", "CLI_PLAY_GUIDE_PINS", "0x60"),
                    ("confirm", "play_confirm_pins.h", "CLI_PLAY_DOWNLOAD_PINS", "0x50")):
                (root / "semantic/play" / folder / filename).write_text(
                    "#pragma once\nstatic const unsigned char fixture_" + name + "[] = {0xa5, 0x5a};\n"
                    "static const CliPin " + name + "[] = {{" + offset + ", fixture_" + name + ", 2}};\n",
                    encoding="utf-8")
            binary = root / "test-advanced-guide"
            compiled = subprocess.run([compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                str(root / fixture), "-o", str(binary)], capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS advanced guide", result.stdout)
            self.assertIn("synthetic pin bytes", result.stdout)


if __name__ == "__main__":
    unittest.main()
