import contextlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import struct
import tempfile
import unittest
from unittest.mock import patch

import akaine_stag as cli


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeAdb:
    """A separate in-memory device, including real request bytes and lock ownership."""

    def __init__(self):
        self.clock = Clock()
        self.metadata = {"protocol": 1, "environment": "staging", "package": cli.PACKAGE,
                         "pid": 1234, "session": "1" * 32, "commands": ["status", "category", "ui", *sorted(cli.DOMAIN_COMMANDS)]}
        self.pid = "1234"
        self.files = {"bridge.json": json.dumps(self.metadata).encode()}
        self.locked = False
        self.calls = []
        self.requests = []
        self.pending = None
        self.respond = True
        self.response_session = None
        self.response_environment = "staging"
        self.restart_after_write = False
        self.lock_release_fails = False
        self.response_reads = 0
        self.stale_response_first = False
        self.log = b"10-20 10:00:00 AkaineCLI: state scene=song_select\n"
        self.date_output = b"1800000000123\n"
        self.response_override = {}
        self.transport_delay = 0
        self.ui_context = "a" * 16
        self.ui_actions = [("main_music", "Music", True)]
        self.ui_modal = False
        self.ui_reason = None
        self.ui_override = {}
        self.ui_action_error = None
        self.ui_context_stays = False
        self.credential_payload = None
        self.restart_after_credential = False
        self.login_terms_required = False
        self.sync_phase = None
        self.sync_error = None

    def run(self, arguments, input, stdout, stderr, timeout, check):
        assert arguments[:3] == ["fixture-adb", "-s", "emulator-5556"], arguments
        assert timeout > 0
        assert check is False
        self.calls.append((arguments, input, timeout))
        if timeout < self.transport_delay:
            self.clock.now += timeout
            raise subprocess.TimeoutExpired(arguments, timeout)
        self.clock.now += self.transport_delay
        command = arguments[3:]
        code, data = 0, b""
        if command == ["shell", "pidof", cli.PACKAGE]:
            data = self.pid.encode() + b"\n"
        elif command == ["shell", "date", "+%s%3N"]:
            data = self.date_output
        elif command == ["exec-out", "screencap", "-p"]:
            data = b"\x89PNG\r\n\x1a\nfixture"
        elif command[:2] == ["logcat", "-d"]:
            assert "--pid=1234" in command
            assert command[-6:] == list(cli.LOG_TAGS)
            data = self.log
        else:
            shell_v2 = command[:2] == ["shell", "-T"]
            remote = command[2:] if shell_v2 else command[1:]
            assert shell_v2 or command[0] == "exec-out", command
            assert remote[:4] == ["run-as", cli.PACKAGE, "sh", "-c"], remote
            # Model ADB's remote join, then POSIX shell tokenization: missing quotes
            # would turn the script into extra argv instead of one sh -c argument.
            remote_argv = shlex.split(" ".join(remote))
            assert len(remote_argv) == 5, remote_argv
            script = remote_argv[4]
            if script == "exit 7":
                code = 7
            elif script.startswith("mkdir -m 700 "):
                code = 1 if self.locked else 0
                self.locked = True
            elif script.startswith("rmdir "):
                code = 1 if self.lock_release_fails else 0
                if not code:
                    self.locked = False
            elif script.startswith("rm -f "):
                assert self.locked and "/credential " in script and "/credential.inflight && rmdir " in script
                self.files.pop("credential", None)
                self.files.pop("credential.tmp", None)
                self.files.pop("credential.inflight", None)
                code = 1 if self.lock_release_fails else 0
                if not code:
                    self.locked = False
            elif script.startswith(f"test -d {cli.DIRECTORY}") and "credential.tmp" in script:
                assert self.locked and "test ! -e" in script and "test ! -L" in script
                code = 1 if any(name in self.files for name in ("credential", "credential.tmp", "credential.inflight")) else 0
            elif script.startswith("umask 077; set -C;"):
                assert self.locked and "credential.tmp" in script and "mv -f" in script and "chmod 600" in script
                assert isinstance(input, bytearray) and len(input) <= 396
                self.credential_payload = bytes(input)
                self.files["credential"] = bytes(input)
                if self.restart_after_credential:
                    self.metadata["session"] = "2" * 32
                    self.files["bridge.json"] = json.dumps(self.metadata).encode()
            elif script.startswith("umask 077;"):
                assert self.locked
                assert b"\n" == input[-1:]
                assert len(input) <= 512
                fields = input.decode("ascii").strip().split(" ")
                assert len(fields) == 6 and fields[0] == "AKCLI1", fields
                assert cli.HEX_ID.fullmatch(fields[1]) and cli.HEX_ID.fullmatch(fields[2])
                assert fields[3].isdigit()
                assert (fields[4:] in (["status", "none"], ["category", "7"], ["category", "8"], ["ui", "list"]) or
                        (fields[4] == "ui" and cli.UI_TOKEN.fullmatch(fields[5])) or cli.domain_argument(fields[4], fields[5]))
                assert "cat >" in script and "chmod 600" in script and "mv -f" in script
                assert fields[1] not in script and fields[2] not in script
                self.requests.append(fields)
                self.pending = fields
                if self.restart_after_write:
                    self.metadata["session"] = "2" * 32
                    self.files["bridge.json"] = json.dumps(self.metadata).encode()
            elif "head -c" in script:
                filename = "bridge.json" if "bridge.json" in script else "response.json"
                assert f"test ! -L {cli.DIRECTORY}" in script
                if filename == "response.json":
                    self.response_reads += 1
                    if self.pending and self.respond and not (self.stale_response_first and self.response_reads == 1):
                        _, request_id, session, expires, action, argument = self.pending
                        # Fixture rejects the same protocol inputs the host must provide correctly.
                        if session == self.metadata["session"] and int(expires) > 1800000000123:
                            response = {"protocol": 1, "request_id": request_id,
                                        "session": self.response_session or session,
                                        "environment": self.response_environment,
                                        "command": action, "ok": True, "error": None,
                                        "state": {"screen": "song_select", "frame": 120,
                                                  "category": None if action != "category" else {
                                                      "section": int(argument), "name": "mod" if argument == "8" else "variety",
                                                      "selected_ordinal": 5 if argument == "8" else 4}}}
                            if action in ("song_select", "difficulty", "sort", "group", "reverse", "pack_select", "pack_close"):
                                song = {"song_id": "testify", "difficulty": 2, "selected_difficulty": 2,
                                        "sort": 1, "group": 0, "reverse": False, "native_list_count": 100,
                                        "pack_id": "all", "pack_open": False, "filter_open": False}
                                if action in ("song_select", "pack_select"):
                                    song["song_id" if action == "song_select" else "pack_id"] = argument
                                elif action in ("difficulty", "sort", "group"):
                                    song[action] = int(argument)
                                elif action == "reverse":
                                    song["reverse"] = argument == "1"
                                response["state"]["song_selection"] = song
                            elif action == "character":
                                response["state"]["character"] = {"available": True, "dialog_open": argument != "close",
                                    "reason": None, "equipped_id": int(argument) if argument.isdecimal() else 0,
                                    "preview_id": int(argument) if argument.isdecimal() else 0,
                                    "can_open": False, "can_select": True, "can_close": True,
                                    "owned_ids": [0, 1, 98]}
                            elif action == "account":
                                if argument == "fill":
                                    credential = self.files.pop("credential")
                                    assert credential[:8] == b"AKCRED1\n"
                                    assert credential[8:40].decode() == session
                                    assert credential[40:72].decode() == request_id
                                    username_size, password_size = struct.unpack_from("<HH", credential, 72)
                                    assert len(credential) == 76 + username_size + password_size
                                terms = argument == "login_open" and self.login_terms_required
                                response["state"]["account"] = {"kind": "login_terms_required" if terms else "login" if argument in ("login_open", "fill", "terms_accept") else "logged_out_menu",
                                    "signed_in": argument == "submit", "blocked": False, "can_open": False,
                                    "can_login_open": not terms and argument == "open", "can_fill": not terms and argument in ("login_open", "fill"),
                                    "can_submit": not terms and argument in ("login_open", "fill"), "can_accept_terms": terms}
                            elif action == "sync":
                                response["state"]["sync"] = {"phase": self.sync_phase or ("success" if argument == "download" else "ready"),
                                    "error_code": self.sync_error, "download_only": True, "can_download": argument == "status"}
                            if action == "ui":
                                if argument != "list" and not self.ui_action_error:
                                    if not self.ui_context_stays:
                                        self.ui_context = "b" * 16
                                    self.ui_actions = []
                                    response["state"]["screen"] = "song_select"
                                response["state"]["ui"] = {
                                    "context": self.ui_context,
                                    "actions": [{"token": name + "." + self.ui_context, "name": label, "enabled": enabled}
                                                for name, label, enabled in self.ui_actions],
                                    "modal_present": self.ui_modal, "reason": self.ui_reason,
                                    "overlays": [], "overlay_scan_complete": True, "overlay_coverage": list(cli.OVERLAY_COVERAGE),
                                    **self.ui_override}
                                if argument != "list" and self.ui_action_error:
                                    response.update(ok=False, error={"code": self.ui_action_error, "message": "Fixture UI error."})
                            response.update(self.response_override)
                            self.files[filename] = json.dumps(response).encode()
                            self.pending = None
                code = 0 if filename in self.files else 1
                data = self.files.get(filename, b"")
            else:
                raise AssertionError("Unexpected remote script: " + script)
            # Android's exec service returns only a raw byte stream, unlike shell v2.
            # Do not let the fixture give exec-out a nonexistent remote-status channel.
            if not shell_v2:
                code = 0
        return subprocess.CompletedProcess(arguments, code, data, b"hidden diagnostic credential")

    def client(self, timeout=10):
        return cli.Client(cli.Adb("fixture-adb", "emulator-5556", self.run), timeout,
                          self.clock, self.clock.sleep)


class ClientTests(unittest.TestCase):
    def test_replay_requires_the_requested_boolean_and_never_retries(self):
        for argument in ("0", "1"):
            for value in (False, True, None, 0, 1):
                device = FakeAdb()
                device.response_override = {"state": {"anomaly_replay": value}}
                result = device.client().execute("replay", argument)
                expected = type(value) is bool and value == (argument == "1")
                self.assertEqual(result["ok"], expected, result)
                self.assertEqual(len(device.requests), 1)
                self.assertFalse(device.locked)

    def test_play_requires_actual_gameplay_for_the_expected_song(self):
        valid = {"screen": "gameplay", "gameplay": True, "song_id": "testify", "difficulty": 3}
        for changes in ({}, {"gameplay": False}, {"song_id": "diein"}, {"screen": "song_select"},
                        {"difficulty": True}, {"difficulty": 5}, {"difficulty": None}):
            for command in ("play", "play_guide"):
                device = FakeAdb()
                device.response_override = {"state": {**valid, **changes}}
                result = device.client().execute(command, "testify")
                self.assertEqual(result["ok"], not changes, result)
                self.assertEqual(len(device.requests), 1)
                self.assertFalse(device.locked)

    def test_download_confirmation_requires_unblocked_song_selection(self):
        valid_ui = {"context": "a" * 16, "actions": [], "modal_present": False, "reason": None,
                    "overlays": [], "overlay_scan_complete": True, "overlay_coverage": list(cli.OVERLAY_COVERAGE)}
        valid = {"screen": "song_select", "song_selection": {"song_id": "testify", "difficulty": 3}, "ui": valid_ui}
        for changes in ({}, {"screen": "gameplay"}, {"song_selection": {"song_id": "diein", "difficulty": 3}},
                        {"ui": {**valid_ui, "modal_present": True}}, {"ui": {**valid_ui, "reason": "loading"}}):
            for command in ("play_download", "play_guide"):
                device = FakeAdb()
                device.response_override = {"state": {**valid, **changes}}
                result = device.client().execute(command, "testify")
                self.assertEqual(result["ok"], not changes, result)
                self.assertEqual(len(device.requests), 1)

    def test_new_controls_reject_invalid_arguments_before_adb(self):
        for command, argument in (("replay", "2"), ("replay", "off"), ("play", "../testify"), ("play", "testify 3"), ("play_download", "../testify")):
            device = FakeAdb()
            result = device.client().execute(command, argument)
            self.assertEqual(result["error"]["code"], "ARGUMENT_ERROR")
            self.assertFalse(device.calls)

    def test_new_controls_parser(self):
        replay = cli.make_parser().parse_args(["--serial", "emulator-5556", "settings", "anomaly-replay", "off"])
        self.assertEqual((replay.command, replay.setting, replay.value), ("settings", "anomaly-replay", "off"))
        play = cli.make_parser().parse_args(["--serial", "emulator-5556", "song", "play", "testify"])
        self.assertEqual((play.command, play.action, play.id), ("song", "play", "testify"))
        download = cli.make_parser().parse_args(["--serial", "emulator-5556", "song", "confirm-download", "testify"])
        self.assertEqual((download.command, download.action, download.id), ("song", "confirm-download", "testify"))
        guide = cli.make_parser().parse_args(["--serial", "emulator-5556", "song", "skip-advanced-guide", "testify"])
        self.assertEqual((guide.command, guide.action, guide.id), ("song", "skip-advanced-guide", "testify"))

    def test_sync_status_and_download_use_only_the_explicit_native_route(self):
        for argument in ("status", "download"):
            device = FakeAdb()
            client = device.client()
            result = client.execute("sync", argument)
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["state"]["sync"]["download_only"])
            self.assertEqual(device.requests[0][4:], ["sync", argument])
            self.assertEqual(client.dispatched, argument == "download")
            self.assertEqual(len(device.requests), 1)

    def test_sync_download_requires_success_and_never_retries_pending_or_failed(self):
        for phase in ("unavailable", "ready", "fetching", "applying", "failed"):
            device = FakeAdb()
            device.sync_phase = phase
            result = device.client().execute("sync", "download")
            self.assertEqual(result["error"]["code"], "PROTOCOL_ERROR")
            self.assertTrue(result["error"]["outcome_unknown"])
            self.assertFalse(result["error"]["automatic_retry"])
            self.assertEqual(len(device.requests), 1)

    def test_sync_status_accepts_each_native_phase_and_explicit_error_code(self):
        for phase in ("unavailable", "ready", "fetching", "applying", "success", "failed"):
            device = FakeAdb()
            device.sync_phase = phase
            device.sync_error = -1013 if phase == "failed" else None
            result = device.client().execute("sync", "status")
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["state"]["sync"]["phase"], phase)

    def test_sync_refuses_upload_force_and_arbitrary_arguments_before_adb(self):
        for argument in ("upload", "force", "download all", "download\nstatus", "none"):
            device = FakeAdb()
            result = device.client().execute("sync", argument)
            self.assertEqual(result["error"]["code"], "ARGUMENT_ERROR")
            self.assertFalse(device.calls)

    def test_sync_response_rejects_nonpublic_fields_and_malformed_flags(self):
        valid = {"phase": "ready", "error_code": None, "download_only": True, "can_download": True}
        for changes in ({"phase": "uploading"}, {"download_only": False}, {"download_only": 1}, {"can_download": 1},
                        {"error_code": True}, {"error_code": 2147483648}, {"token": "never-output"}):
            for command, argument in (("sync", "status"), ("status", "none")):
                device = FakeAdb()
                device.response_override = {"state": {"sync": {**valid, **changes}}}
                result = device.client().execute(command, argument)
                self.assertEqual(result["error"]["code"], "PROTOCOL_ERROR")
                self.assertNotIn("never-output", json.dumps(result))

    def test_sync_native_error_and_transport_timeout_do_not_retry_download(self):
        device = FakeAdb()
        device.response_override = {"ok": False, "error": {"code": "SYNC_FAILED", "message": "Cloud Sync Download failed."},
                                   "state": {"sync": {"phase": "failed", "error_code": 503, "download_only": True, "can_download": True}}}
        result = device.client().execute("sync", "download")
        self.assertEqual(result["error"]["code"], "SYNC_FAILED")
        self.assertEqual(result["state"]["sync"]["error_code"], 503)
        self.assertEqual(len(device.requests), 1)
        for argument in ("status", "download"):
            device = FakeAdb()
            device.respond = False
            result = device.client(timeout=1).execute("sync", argument)
            self.assertEqual(result["error"]["code"], "TIMEOUT")
            self.assertEqual(result["error"].get("outcome_unknown", False), argument == "download")
            if argument == "download":
                self.assertFalse(result["error"]["automatic_retry"])
            self.assertEqual(len(device.requests), 1)

    def test_sync_parser_exposes_status_and_download_only(self):
        for argument in ("status", "download"):
            with patch.object(cli, "Client") as client, contextlib.redirect_stdout(io.StringIO()):
                client.return_value.execute.return_value = {"ok": True}
                self.assertEqual(cli.main(["--serial", "emulator-5556", "sync", argument]), 0)
                self.assertEqual(client.return_value.execute.call_args.args[:2], ("sync", argument))
        for argument in ("upload", "--force"):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(cli.main(["--serial", "emulator-5556", "sync", argument]), 1)
            self.assertEqual(json.loads(output.getvalue())["error"]["code"], "ARGUMENT_ERROR")

    def test_native_domain_commands_round_trip_and_confirm_state(self):
        for command, argument in (("song_select", "diein"), ("difficulty", "4"), ("sort", "5"), ("group", "2"),
                                  ("reverse", "1"), ("pack_select", "xd_fan_album"), ("pack_select", "all"),
                                  ("pack_close", "none"), ("character", "status"), ("character", "list"),
                                  ("character", "open"), ("character", "98"), ("character", "close"),
                                  ("account", "status"), ("account", "open"), ("account", "login_open"), ("account", "submit")):
            with self.subTest(command=command, argument=argument):
                device = FakeAdb()
                client = device.client()
                result = client.execute(command, argument)
                self.assertTrue(result["ok"], result)
                self.assertEqual(device.requests[0][4:], [command, argument])
                self.assertEqual(client.dispatched, cli.mutation(command, argument))
                self.assertFalse(device.locked)

    def test_domain_rejects_bad_wire_arguments_before_adb(self):
        for command, argument in (("song_select", "x y"), ("song_select", "$(id)"), ("song_select", "a" * 65),
                                  ("pack_select", "../all"), ("pack_close", "all"), ("difficulty", "5"), ("sort", "6"),
                                  ("group", "-1"), ("reverse", "on"), ("character", "098"), ("character", "999999"),
                                  ("account", "delete_account"), ("account", "login-open")):
            device = FakeAdb()
            result = device.client().execute(command, argument)
            self.assertEqual(result["error"]["code"], "ARGUMENT_ERROR", (command, argument))
            self.assertFalse(device.calls)

    def test_domain_success_requires_matching_native_confirmation(self):
        for command, argument, state in (("song_select", "diein", {"song_selection": {"song_id": "testify"}}),
                                        ("difficulty", "4", {"song_selection": {"difficulty": True}}),
                                        ("pack_close", "none", {"song_selection": {"pack_open": True}}),
                                        ("reverse", "1", {"song_selection": {"reverse": 1}}),
                                        ("character", "98", {"character": {"equipped_id": 0}}),
                                        ("account", "submit", {"account": {"kind": "login", "signed_in": False,
                                         "blocked": False, "can_open": False, "can_login_open": False, "can_fill": True, "can_submit": True}})):
            device = FakeAdb()
            device.response_override = {"state": state}
            result = device.client().execute(command, argument)
            self.assertEqual(result["error"]["code"], "PROTOCOL_ERROR")
            self.assertTrue(result["error"]["outcome_unknown"])
            self.assertFalse(result["error"]["automatic_retry"])
            self.assertEqual(len(device.requests), 1)

    def test_domain_read_timeouts_are_not_marked_as_mutations(self):
        for command, argument in (("character", "status"), ("character", "list"), ("account", "status")):
            device = FakeAdb()
            device.respond = False
            result = device.client(timeout=1).execute(command, argument)
            self.assertEqual(result["error"]["code"], "TIMEOUT")
            self.assertNotIn("outcome_unknown", result["error"])

    def test_character_selection_confirms_preview_before_close_commits_equipped(self):
        device = FakeAdb()
        device.response_override = {"state": {"character": {"dialog_open": True, "preview_id": 98, "equipped_id": 0}}}
        result = device.client().execute("character", "98")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["state"]["character"]["equipped_id"], 0)
        device = FakeAdb()
        device.response_override = {"state": {"character": {"dialog_open": True, "preview_id": 0, "equipped_id": 98}}}
        result = device.client().execute("character", "98")
        self.assertEqual(result["error"]["code"], "PROTOCOL_ERROR")

    def test_login_open_reports_legal_terms_with_a_separate_user_operated_agreement(self):
        device = FakeAdb()
        device.login_terms_required = True
        result = device.client().execute("account", "login_open")
        self.assertTrue(result["ok"], result)
        terms = result["state"]["account"]
        self.assertEqual(terms["kind"], "login_terms_required")
        self.assertFalse(terms["can_open"])
        self.assertFalse(terms["can_login_open"])
        self.assertFalse(terms["can_fill"])
        self.assertFalse(terms["can_submit"])
        self.assertTrue(terms["can_accept_terms"])
        self.assertEqual(len(device.requests), 1)
        cli.validate_domain_response(result["state"], "account", "status")
        with self.assertRaises(cli.CliError):
            cli.validate_domain_response(result["state"], "account", "fill")
        terms["can_login_open"] = True
        with self.assertRaises(cli.CliError):
            cli.validate_domain_response(result["state"], "account", "status")
        device = FakeAdb()
        result = device.client().execute("account", "login_open")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["state"]["account"]["kind"], "login")

    def test_terms_accept_requires_tty_and_exact_agree_without_adb(self):
        for is_tty, answer, expected in ((False, "AGREE\n", "TERMS_INTERACTIVE_REQUIRED"),
                                          (True, "agree\n", "TERMS_NOT_ACCEPTED"),
                                          (True, " AGREE\n", "TERMS_NOT_ACCEPTED"),
                                          (True, "AGREE \n", "TERMS_NOT_ACCEPTED"),
                                          (True, "", "TERMS_NOT_ACCEPTED")):
            stream = io.StringIO(answer)
            output, prompt = io.StringIO(), io.StringIO()
            with patch.object(stream, "isatty", return_value=is_tty), patch.object(cli.sys, "stdin", stream), \
                    patch.object(cli, "Adb") as adb, contextlib.redirect_stdout(output), contextlib.redirect_stderr(prompt):
                result = cli.main(["--serial", "emulator-5556", "account", "terms-accept"])
            self.assertEqual(result, 1)
            self.assertEqual(json.loads(output.getvalue())["error"]["code"], expected)
            adb.assert_not_called()
            if is_tty:
                self.assertIn(cli.TERMS_URL, prompt.getvalue())
                self.assertIn(cli.PRIVACY_URL, prompt.getvalue())
                self.assertIn("native 'I Agree'", prompt.getvalue())

    def test_terms_accept_exact_tty_confirmation_dispatches_only_that_action_once(self):
        device = FakeAdb()
        stream = io.StringIO("AGREE\n")
        output, prompt = io.StringIO(), io.StringIO()
        with patch.object(stream, "isatty", return_value=True), patch.object(cli.sys, "stdin", stream), \
                patch.object(cli, "Adb", return_value=cli.Adb("fixture-adb", "emulator-5556", device.run)), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(prompt):
            self.assertEqual(cli.main(["--serial", "emulator-5556", "account", "terms-accept"]), 0)
        self.assertTrue(json.loads(output.getvalue())["ok"])
        self.assertEqual([request[4:] for request in device.requests], [["account", "terms_accept"]])
        self.assertFalse(cli._terms_tickets)
        self.assertNotIn(cli.TERMS_URL, output.getvalue())
        self.assertIn("does not fill credentials or submit login", prompt.getvalue())

    def test_direct_terms_dispatch_or_reused_consent_is_rejected(self):
        device = FakeAdb()
        result = device.client().execute("account", "terms_accept")
        self.assertEqual(result["error"]["code"], "TERMS_INTERACTIVE_REQUIRED")
        self.assertFalse(device.calls)
        stream = io.StringIO("AGREE\n")
        with patch.object(stream, "isatty", return_value=True), patch.object(cli.sys, "stdin", stream), contextlib.redirect_stderr(io.StringIO()):
            ticket = cli.confirm_terms()
        self.assertTrue(device.client().execute("account", "terms_accept", terms_consent=ticket)["ok"])
        before = len(device.requests)
        result = device.client().execute("account", "terms_accept", terms_consent=ticket)
        self.assertEqual(result["error"]["code"], "TERMS_INTERACTIVE_REQUIRED")
        self.assertEqual(len(device.requests), before)

    def test_terms_accept_has_no_force_or_noninteractive_flag(self):
        for flag in ("--force", "--yes", "--credentials-stdin", "--headless"):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = cli.main(["--serial", "emulator-5556", "account", "terms-accept", flag])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output.getvalue())["error"]["code"], "ARGUMENT_ERROR")

    def test_terms_accept_success_requires_the_actual_login_form(self):
        device = FakeAdb()
        device.response_override = {"state": {"account": {"kind": "logged_out_menu", "signed_in": False,
                                   "blocked": False, "can_open": False, "can_login_open": True,
                                   "can_fill": False, "can_submit": False, "can_accept_terms": False}}}
        stream = io.StringIO("AGREE\n")
        with patch.object(stream, "isatty", return_value=True), patch.object(cli.sys, "stdin", stream), contextlib.redirect_stderr(io.StringIO()):
            ticket = cli.confirm_terms()
        result = device.client().execute("account", "terms_accept", terms_consent=ticket)
        self.assertEqual(result["error"]["code"], "PROTOCOL_ERROR")
        self.assertTrue(result["error"]["outcome_unknown"])

    def test_credential_payload_is_private_bound_and_wiped_after_fill(self):
        device = FakeAdb()
        credentials = cli.credential_bytes({"username": "fixture-user", "password": "fixture-private-pass"})
        result = device.client().execute("account", "fill", credentials=credentials)
        self.assertTrue(result["ok"], result)
        request = device.requests[0]
        payload = device.credential_payload
        self.assertEqual(payload[:8], b"AKCRED1\n")
        self.assertEqual(payload[8:40].decode(), request[2])
        self.assertEqual(payload[40:72].decode(), request[1])
        self.assertEqual(struct.unpack_from("<HH", payload, 72), (12, 20))
        self.assertEqual(payload[76:], b"fixture-userfixture-private-pass")
        self.assertTrue(all(value == bytes(len(value)) for value in credentials))
        self.assertNotIn("credential", device.files)
        self.assertNotIn("credential.tmp", device.files)
        for arguments, _, _ in device.calls:
            self.assertNotIn("fixture-user", str(arguments))
            self.assertNotIn("fixture-private-pass", str(arguments))
        self.assertNotIn("fixture-user", json.dumps(result))
        self.assertNotIn("fixture-private-pass", json.dumps(result))

    def test_credential_restart_before_request_cleans_payload_and_never_fills(self):
        device = FakeAdb()
        device.restart_after_credential = True
        credentials = cli.credential_bytes({"username": "fixture", "password": "fixture-pass"})
        result = device.client().execute("account", "fill", credentials=credentials)
        self.assertEqual(result["error"]["code"], "BRIDGE_RESTARTED")
        self.assertNotIn("outcome_unknown", result["error"])
        self.assertFalse(device.requests)
        self.assertNotIn("credential", device.files)
        self.assertFalse(device.locked)

    def test_credential_timeout_never_retries_and_cleans_unconsumed_payload(self):
        device = FakeAdb()
        device.respond = False
        credentials = cli.credential_bytes({"username": "fixture", "password": "fixture-pass"})
        result = device.client(timeout=1).execute("account", "fill", credentials=credentials)
        self.assertEqual(result["error"]["code"], "TIMEOUT")
        self.assertTrue(result["error"]["outcome_unknown"])
        self.assertEqual(len(device.requests), 1)
        self.assertNotIn("credential", device.files)
        self.assertFalse(device.locked)

    def test_existing_credential_file_is_preserved_for_manual_inspection(self):
        for filename in ("credential", "credential.tmp", "credential.inflight"):
            device = FakeAdb()
            device.files[filename] = b"previous-private-payload"
            credentials = cli.credential_bytes({"username": "fixture", "password": "fixture-pass"})
            result = device.client().execute("account", "fill", credentials=credentials)
            self.assertEqual(result["error"]["code"], "CREDENTIAL_FILE_EXISTS")
            self.assertEqual(device.files[filename], b"previous-private-payload")
            self.assertFalse(device.requests)

    def test_credential_validation_rejects_missing_extra_duplicate_and_oversized_input(self):
        values = ["{}", '{"username":"fixture"}', '{"username":"a","username":"b","password":"p"}',
                  json.dumps({"username": "a", "password": "b", "extra": "never-output"}),
                  json.dumps({"username": "a" * 65, "password": "b"}),
                  json.dumps({"username": "a", "password": "b" * 257}),
                  json.dumps({"username": "a", "password": "a\u0000b"}), " " * 513]
        for raw in values:
            with self.subTest(raw_size=len(raw)), patch.object(cli.sys, "stdin", io.StringIO(raw)):
                with self.assertRaises(cli.CliError) as error:
                    cli.read_credentials(True)
                self.assertEqual(error.exception.code, "CREDENTIAL_INPUT")
                self.assertNotIn("never-output", str(error.exception))

    def test_credential_stdin_and_interactive_input_support_unicode(self):
        raw = json.dumps({"username": "fixture", "password": "mật-khẩu"}, ensure_ascii=False)
        with patch.object(cli.sys, "stdin", io.StringIO(raw)):
            credentials = cli.read_credentials(True)
        self.assertEqual(credentials[1].decode("utf-8"), "mật-khẩu")
        with patch.object(cli.sys.stdin, "isatty", return_value=True), patch.object(cli.getpass, "getpass", side_effect=["fixture", "hidden-pass"]) as hidden:
            credentials = cli.read_credentials(False)
        self.assertEqual(credentials[1], b"hidden-pass")
        self.assertEqual(hidden.call_count, 2)
        for call in hidden.call_args_list:
            self.assertIs(call.kwargs["stream"], cli.sys.stderr)

    def test_account_response_refuses_unexpected_private_fields_without_echo(self):
        for command, argument in (("account", "status"), ("status", "none")):
            device = FakeAdb()
            device.response_override = {"state": {"account": {"kind": "login", "username": "never-output", "password": "hidden-pass"}}}
            result = device.client().execute(command, argument)
            self.assertEqual(result["error"]["code"], "PROTOCOL_ERROR")
            self.assertNotIn("never-output", json.dumps(result))
            self.assertNotIn("hidden-pass", json.dumps(result))

    def test_public_parser_routes_native_controls_and_keeps_catalogue_sort_separate(self):
        cases = [("song select diein", "song_select", "diein"), ("song difficulty etr", "difficulty", "4"),
                 ("song sort artist", "sort", "5"), ("song group level", "group", "2"), ("song reverse on", "reverse", "1"),
                 ("pack select all", "pack_select", "all"), ("pack close", "pack_close", "none"),
                 ("character select 98", "character", "98"), ("character list", "character", "list"),
                 ("account login-open", "account", "login_open"), ("account submit", "account", "submit"),
                 ("song list --sort title", "song-catalogue", "none")]
        for arguments, expected_command, expected_argument in cases:
            with patch.object(cli, "Client") as client, contextlib.redirect_stdout(io.StringIO()):
                client.return_value.execute.return_value = {"ok": True}
                self.assertEqual(cli.main(["--serial", "emulator-5556", *shlex.split(arguments)]), 0)
                call = client.return_value.execute.call_args
                self.assertEqual(call.args[:2], (expected_command, expected_argument))

    def test_unsupported_argv_does_not_echo_pasted_credentials(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.main(["--serial", "emulator-5556", "account", "fill", "--password", "never-output"])
        self.assertEqual(code, 1)
        self.assertNotIn("never-output", output.getvalue())

    def test_ui_list_reads_fixed_actions_without_dispatching_activation(self):
        device = FakeAdb()
        result = device.client().execute("ui", "list")
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"]["ui"]["actions"], [{"token": "main_music." + "a" * 16,
                                                             "name": "Music", "enabled": True}])
        self.assertEqual([request[4:] for request in device.requests], [["ui", "list"]])
        self.assertEqual(device.ui_context, "a" * 16)

    def test_ui_activation_preflights_current_context_then_confirms_fresh_context(self):
        device = FakeAdb()
        token = "main_music." + "a" * 16
        result = device.client().execute("ui", token)
        self.assertTrue(result["ok"])
        self.assertEqual([request[4:] for request in device.requests], [["ui", "list"], ["ui", token]])
        self.assertEqual(result["state"]["ui"]["context"], "b" * 16)
        self.assertEqual(result["request_id"], device.requests[1][1])
        self.assertFalse(device.locked)

    def test_pack_open_confirms_changed_context_with_same_song_select_scene(self):
        device = FakeAdb()
        device.ui_actions = [("pack_open", "Pack Select", True)]
        token = "pack_open." + "a" * 16
        result = device.client().execute("ui", token)
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"]["screen"], "song_select")
        self.assertEqual(result["state"]["ui"]["context"], "b" * 16)
        self.assertEqual([request[4:] for request in device.requests], [["ui", "list"], ["ui", token]])

    def test_pack_open_rejects_wrong_label_and_does_not_accept_arbitrary_ui_action(self):
        device = FakeAdb()
        device.ui_actions = [("pack_open", "Packs", True)]
        result = device.client().execute("ui", "pack_open." + "a" * 16)
        self.assertEqual(result["error"]["code"], "PROTOCOL_ERROR")
        self.assertEqual(len(device.requests), 1)
        device = FakeAdb()
        result = device.client().execute("ui", "song_play." + "a" * 16)
        self.assertEqual(result["error"]["code"], "ARGUMENT_ERROR")
        self.assertFalse(device.calls)

    def test_ui_stale_disabled_unoffered_and_modal_tokens_do_not_activate(self):
        cases = [("b" * 16, [("main_music", "Music", True)], False, None, "STALE_UI_CONTEXT"),
                 ("a" * 16, [("main_music", "Music", False)], False, None, "UI_ACTION_UNAVAILABLE"),
                 ("a" * 16, [], False, "not_ready", "UI_ACTION_UNAVAILABLE"),
                 ("a" * 16, [], True, "unsupported_modal", "UI_ACTION_UNAVAILABLE")]
        for context, actions, modal, reason, expected in cases:
            device = FakeAdb()
            device.ui_context, device.ui_actions, device.ui_modal, device.ui_reason = context, actions, modal, reason
            result = device.client().execute("ui", "main_music." + "a" * 16)
            self.assertEqual(result["error"]["code"], expected)
            self.assertNotIn("outcome_unknown", result["error"])
            self.assertEqual([request[4:] for request in device.requests], [["ui", "list"]])

    def test_ui_token_whitelist_and_wire_safety(self):
        for token in ("unknown." + "a" * 16, "main_music." + "A" * 16, "main_music." + "a" * 15,
                      "main_music." + "a" * 17, "main_music." + "a" * 16 + "\n", "dialog_primary." + "a" * 16):
            device = FakeAdb()
            result = device.client().execute("ui", token)
            self.assertEqual(result["error"]["code"], "ARGUMENT_ERROR")
            self.assertFalse(device.calls)

    def test_ui_malformed_context_labels_and_actions_fail_before_activation(self):
        for override in ({"context": "bad"}, {"actions": [{"token": "main_music." + "a" * 16,
                                                          "name": "account-sensitive-text", "enabled": True}]},
                         {"modal_present": 1}, {"reason": {}}, {"modal_present": True},
                         {"actions": [{"token": "main_music." + "b" * 16, "name": "Music", "enabled": True}]}):
            device = FakeAdb()
            device.ui_override = override
            result = device.client().execute("ui", "main_music." + "a" * 16)
            self.assertEqual(result["error"]["code"], "PROTOCOL_ERROR", override)
            self.assertNotIn("outcome_unknown", result["error"])
            self.assertNotIn("account-sensitive-text", json.dumps(result))
            self.assertEqual(len(device.requests), 1)

    def test_ui_success_without_context_confirmation_is_unknown_and_never_retried(self):
        device = FakeAdb()
        device.ui_context_stays = True
        result = device.client().execute("ui", "main_music." + "a" * 16)
        self.assertEqual(result["error"]["code"], "PROTOCOL_ERROR")
        self.assertTrue(result["error"]["outcome_unknown"])
        self.assertFalse(result["error"]["automatic_retry"])
        self.assertEqual(len(device.requests), 2)

    def test_ui_native_postdispatch_vs_stale_context_errors(self):
        for error in ("ACTION_TIMEOUT", "SCENE_CHANGED", "STALE_UI_CONTEXT", "EXPIRED"):
            device = FakeAdb()
            device.ui_action_error = error
            result = device.client().execute("ui", "main_music." + "a" * 16)
            self.assertEqual(result["error"]["code"], error)
            self.assertEqual(result["error"].get("outcome_unknown", False), error in ("ACTION_TIMEOUT", "SCENE_CHANGED"))
            self.assertEqual(len(device.requests), 2)

    def test_run_as_shell_uses_shell_v2_remote_exit_status(self):
        device = FakeAdb()
        adb = cli.Adb("fixture-adb", "emulator-5556", device.run)
        raw = adb.call(["exec-out", "run-as", cli.PACKAGE, "sh", "-c", shlex.quote("exit 7")], 1,
                       allow_failure=True)
        self.assertEqual(raw.returncode, 0)
        result = adb.shell("exit 7", cli.Deadline(1, device.clock), allow_failure=True)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(device.calls[-1][0][3:5], ["shell", "-T"])

    def test_status_round_trip_is_bound_to_pid_session_and_explicit_device(self):
        device = FakeAdb()
        result = device.client().execute("status")
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"]["frame"], 120)
        self.assertEqual(device.requests[0][4:], ["status", "none"])
        self.assertFalse(device.locked)
        self.assertEqual(len(device.requests), 1)
        for arguments, _, _ in device.calls:
            self.assertEqual(arguments[1:3], ["-s", "emulator-5556"])
            self.assertNotIn("root", arguments)

    def test_category_serializes_validated_semantic_argument(self):
        device = FakeAdb()
        result = device.client().execute("category", "8")
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"]["category"], {"section": 8, "name": "mod", "selected_ordinal": 5})
        self.assertEqual(device.requests[0][4:], ["category", "8"])

    def test_internal_api_rejects_unsupported_arguments_before_adb(self):
        for command, argument in (("status", "other"), ("category", "8\ncategory 7"),
                                  ("category", "99"), ("arbitrary", "none")):
            device = FakeAdb()
            result = device.client().execute(command, argument)
            self.assertEqual(result["error"]["code"], "ARGUMENT_ERROR")
            self.assertFalse(device.calls)

    def test_serial_validation_rejects_shell_inputs_without_invocation(self):
        for serial in (None, "", "-s", "emulator-5556 extra", "x;id", "x\ny", "$(id)", "x'", "x/abc"):
            with self.subTest(serial=serial), self.assertRaises(cli.CliError):
                cli.Adb("unused", serial, lambda **kw: self.fail("ADB invoked"))

    def test_missing_serial_and_invalid_timeout_are_json_errors(self):
        for arguments in (["status"], ["--serial", "emulator-5556", "--timeout", "31", "status"],
                          ["--serial", "emulator-5556", "--timeout", "nan", "status"]):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = cli.main(arguments)
            result = json.loads(output.getvalue())
            self.assertEqual(code, 1)
            self.assertEqual(result["error"]["code"], "ARGUMENT_ERROR")

    def test_not_staging_never_acquires_lock_or_writes_request(self):
        for changes in ({"environment": "production"}, {"package": "other"}, {"protocol": True}):
            device = FakeAdb()
            device.metadata.update(changes)
            device.files["bridge.json"] = json.dumps(device.metadata).encode()
            result = device.client().execute("category", "8")
            self.assertEqual(result["error"]["code"], "NOT_STAGING")
            self.assertFalse(device.requests)
            self.assertFalse(device.locked)

    def test_stale_pid_and_malformed_session_do_not_dispatch(self):
        for changes, pid, expected in (({}, "5678", "STALE_BRIDGE"), ({"session": "bad"}, "1234", "PROTOCOL_ERROR")):
            device = FakeAdb()
            device.metadata.update(changes)
            device.files["bridge.json"] = json.dumps(device.metadata).encode()
            device.pid = pid
            result = device.client().execute("status")
            self.assertEqual(result["error"]["code"], expected)
            self.assertFalse(device.requests)

    def test_owned_lock_is_not_deleted_or_replaced(self):
        device = FakeAdb()
        device.locked = True
        result = device.client().execute("category", "8")
        self.assertEqual(result["error"]["code"], "LOCKED")
        self.assertTrue(device.locked)
        self.assertFalse(device.requests)
        self.assertFalse(any("rmdir" in arguments[-1] for arguments, _, _ in device.calls))

    def test_stale_response_id_is_ignored_until_matching_response(self):
        device = FakeAdb()
        device.stale_response_first = True
        device.files["response.json"] = json.dumps({"request_id": "a" * 32, "ok": True}).encode()
        result = device.client().execute("status")
        self.assertTrue(result["ok"])
        self.assertEqual(device.response_reads, 2)
        self.assertNotEqual(result["request_id"], "a" * 32)

    def test_matching_response_wrong_session_or_environment_is_rejected(self):
        for attribute, value in (("response_session", "a" * 32), ("response_environment", "production")):
            device = FakeAdb()
            setattr(device, attribute, value)
            result = device.client().execute("category", "8")
            self.assertEqual(result["error"]["code"], "PROTOCOL_ERROR")
            self.assertTrue(result["error"]["outcome_unknown"])
            self.assertEqual(len(device.requests), 1)

    def test_response_structure_command_and_confirmed_category_are_checked(self):
        for override in ({"protocol": True}, {"command": "status"}, {"ok": 1},
                         {"error": {"code": "unexpected"}}, {"state": {}},
                         {"state": {"category": {"section": 7, "name": "variety"}}}):
            device = FakeAdb()
            device.response_override = override
            result = device.client().execute("category", "8")
            self.assertEqual(result["error"]["code"], "PROTOCOL_ERROR", override)
            self.assertTrue(result["error"]["outcome_unknown"])
            self.assertEqual(len(device.requests), 1)

    def test_native_wrong_scene_is_returned_without_retry(self):
        device = FakeAdb()
        device.response_override = {"ok": False, "error": {"code": "WRONG_SCENE", "message": "Requires pack selector."}}
        result = device.client().execute("category", "8")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "WRONG_SCENE")
        self.assertNotIn("outcome_unknown", result["error"])
        self.assertEqual(len(device.requests), 1)

    def test_native_postdispatch_errors_are_unknown_but_predispatch_errors_are_known(self):
        for code in ("ACTION_TIMEOUT", "SCENE_CHANGED", "WRONG_SCENE", "EXPIRED"):
            with self.subTest(code=code):
                device = FakeAdb()
                device.response_override = {"ok": False, "error": {"code": code, "message": "Fixture error."}}
                result = device.client().execute("category", "8")
                self.assertFalse(result["ok"])
                self.assertEqual(result["error"]["code"], code)
                self.assertEqual(result["session"], device.metadata["session"])
                self.assertEqual(result["request_id"], device.requests[0][1])
                self.assertEqual(result["state"]["frame"], 120)
                if code in ("ACTION_TIMEOUT", "SCENE_CHANGED"):
                    self.assertTrue(result["error"]["outcome_unknown"])
                    self.assertFalse(result["error"]["automatic_retry"])
                else:
                    self.assertNotIn("outcome_unknown", result["error"])
                self.assertEqual(len(device.requests), 1)

    def test_session_restart_after_dispatch_has_unknown_outcome_without_retry(self):
        device = FakeAdb()
        device.restart_after_write = True
        result = device.client().execute("category", "8")
        self.assertEqual(result["error"]["code"], "BRIDGE_RESTARTED")
        self.assertTrue(result["error"]["outcome_unknown"])
        self.assertFalse(result["error"]["automatic_retry"])
        self.assertEqual(len(device.requests), 1)
        self.assertFalse(device.locked)

    def test_deadline_bounds_polling_and_never_retries_mutation(self):
        device = FakeAdb()
        device.respond = False
        result = device.client(timeout=1).execute("category", "8")
        self.assertEqual(result["error"]["code"], "TIMEOUT")
        self.assertTrue(result["error"]["outcome_unknown"])
        self.assertEqual(len(device.requests), 1)
        self.assertLessEqual(device.clock.now, 1.000001)
        self.assertFalse(device.locked)
        self.assertLessEqual(int(device.requests[0][3]), 1800000001123)

    def test_deadline_covers_all_adb_steps_not_only_response_polling(self):
        device = FakeAdb()
        device.transport_delay = 0.3
        result = device.client(timeout=1).execute("category", "8")
        self.assertEqual(result["error"]["code"], "TIMEOUT")
        self.assertFalse(device.requests)
        self.assertFalse(device.locked)
        self.assertLessEqual(device.clock.now, 1.3)

    def test_invalid_device_time_and_oversized_json_fail_before_dispatch(self):
        for time_output in (b"1800000000\n", b"1800000000123%3N\n", b"0\n", b"-1800000000123\n"):
            device = FakeAdb()
            device.date_output = time_output
            result = device.client().execute("category", "8")
            self.assertEqual(result["error"]["code"], "DEVICE_TIME")
            self.assertFalse(device.requests)
        device = FakeAdb()
        device.files["bridge.json"] = b" " * (cli.MAX_JSON + 1)
        result = device.client().execute("status")
        self.assertEqual(result["error"]["code"], "PROTOCOL_ERROR")
        self.assertFalse(device.requests)

    def test_adb_timeout_does_not_echo_sensitive_stderr(self):
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired("hidden secret", 1, b"token=never-print", b"password=never-print")
        device = FakeAdb()
        result = cli.Client(cli.Adb("fixture-adb", "emulator-5556", timeout)).execute("status")
        self.assertEqual(result["error"]["code"], "TIMEOUT")
        self.assertNotIn("never-print", json.dumps(result))

    def test_cleanup_failure_preserves_result_and_warns(self):
        device = FakeAdb()
        device.lock_release_fails = True
        result = device.client().execute("status")
        self.assertTrue(result["ok"])
        self.assertIn("lock cleanup failed", result["warning"])

    def test_logs_are_pid_filtered_and_redacted_before_any_disk_write(self):
        device = FakeAdb()
        secrets = ["secret-value", "neverwrite-password", "alice@example.com", "long-signature-value",
                   "user-12345", "B" * 40, "eyJh" * 8 + "." + "e30x" * 8 + "." + "sigx" * 8]
        device.log = ("scene=song_select\n"
                      'payload={"token":"secret-value"}\n'
                      r'payload={\"password\":\"neverwrite-password\"}' + "\n"
                      "contact alice@example.com\n"
                      "signature='long-signature-value'\n"
                      r'payload={"\u0074oken":"secret-value"}' + "\n"
                      'payload={"user_id":"user-12345"}\n'
                      "Bearer " + secrets[5] + "\n" + secrets[6] + "\n").encode()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "sanitized.log"
            original_write = cli.write_artifact
            def guarded_write(path, data):
                for secret in secrets:
                    self.assertNotIn(secret.encode(), data)
                return original_write(path, data)
            with patch.object(cli, "write_artifact", guarded_write):
                result = device.client().execute("logs", output=output)
            self.assertTrue(result["ok"])
            content = output.read_text()
            self.assertIn("scene=song_select", content)
            for secret in secrets:
                self.assertNotIn(secret, content)
            self.assertEqual(list(Path(directory).iterdir()), [output])

    def test_screenshot_and_logs_validate_identity_and_preserve_existing_files(self):
        for command in ("screenshot", "logs"):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "evidence"
                output.write_bytes(b"original")
                result = FakeAdb().client().execute(command, output=output)
                self.assertEqual(result["error"]["code"], "OUTPUT_EXISTS")
                self.assertEqual(output.read_bytes(), b"original")
                device = FakeAdb()
                device.pid = "5678"
                result = device.client().execute(command, output=Path(directory) / "new")
                self.assertEqual(result["error"]["code"], "STALE_BRIDGE")
                self.assertFalse((Path(directory) / "new").exists())

    def test_full_screenshot_is_written_without_cropping(self):
        device = FakeAdb()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "full-screen.png"
            result = device.client().execute("screenshot", output=output)
            self.assertTrue(result["ok"])
            self.assertEqual(output.read_bytes(), b"\x89PNG\r\n\x1a\nfixture")


class OverlayContractTests(unittest.TestCase):
    def setUp(self):
        self.ids = patch.object(cli, "OVERLAY_IDS", {"fixture_tutorial": ("fixture_pack_hint",)})
        self.coverage = patch.object(cli, "OVERLAY_COVERAGE", ("fixture_progression_guide",))
        self.ids.start(); self.coverage.start()
        self.addCleanup(self.ids.stop); self.addCleanup(self.coverage.stop)

    def state(self, overlay=None, actions=False):
        return {"ui": {"context": "a" * 16, "modal_present": False, "reason": None,
            "actions": [{"token": "main_music." + "a" * 16, "name": "Music", "enabled": True}] if actions else [],
            "overlays": [overlay] if overlay else [], "overlay_scan_complete": True,
            "overlay_coverage": ["fixture_progression_guide"]}}

    def overlay(self, **changes):
        return {"kind": "fixture_tutorial", "id": "fixture_pack_hint", "active": True,
                "visible": False, "opacity": 0, "blocks_input": True, **changes}

    def test_hidden_and_zero_opacity_active_interceptor_is_reported(self):
        state = self.state(self.overlay())
        self.assertEqual(cli.validate_ui(state)["overlays"], [self.overlay()])
        self.assertFalse(state["ui"]["modal_present"])
        with self.assertRaisesRegex(cli.CliError, "interceptor"):
            cli.validate_ui(self.state(self.overlay(), actions=True))

    def test_input_interception_does_not_depend_on_active_or_rendering(self):
        with self.assertRaisesRegex(cli.CliError, "interceptor"):
            cli.validate_ui(self.state(self.overlay(active=False, visible=False, opacity=0), actions=True))
        self.assertTrue(cli.validate_ui(self.state(self.overlay(visible=True, opacity=255, blocks_input=False), actions=True))["actions"])

    def test_active_tutorial_reason_does_not_claim_input_is_blocked(self):
        state = self.state(self.overlay(active=True, visible=False, opacity=0, blocks_input=False))
        state["ui"]["reason"] = "tutorial_active"
        result = cli.validate_ui(state)
        self.assertEqual(result["reason"], "tutorial_active")
        self.assertFalse(result["overlays"][0]["blocks_input"])

    def test_unknown_fields_remain_unknown_and_scan_is_not_a_global_claim(self):
        state = self.state(self.overlay(active=None, visible=None, opacity=None, blocks_input=None), actions=True)
        state["ui"]["overlay_scan_complete"] = False
        result = cli.validate_ui(state)
        self.assertIsNone(result["overlays"][0]["blocks_input"])
        self.assertFalse(result["overlay_scan_complete"])
        self.assertEqual(result["overlay_coverage"], ["fixture_progression_guide"])

    def test_missing_overlay_revision_fields_are_rejected(self):
        for key in ("overlays", "overlay_scan_complete", "overlay_coverage"):
            state = self.state(); del state["ui"][key]
            with self.subTest(key=key), self.assertRaises(cli.CliError):
                cli.validate_ui(state)

    def test_bounded_exact_overlay_shape_types_and_identity(self):
        bad_entries = [self.overlay(kind="unmapped"), self.overlay(id="sensitive-unmapped-label"),
            self.overlay(active=1), self.overlay(visible="true"), self.overlay(blocks_input=0),
            self.overlay(opacity=True), self.overlay(opacity=-1), self.overlay(opacity=256),
            self.overlay(opacity=0.5), {**self.overlay(), "raw_text": "must-not-output"}]
        missing = self.overlay(); del missing["active"]; bad_entries.append(missing)
        for entry in bad_entries:
            with self.subTest(entry=entry), self.assertRaises(cli.CliError):
                cli.validate_ui(self.state(entry))
        for changes in ({"overlays": [self.overlay(), self.overlay()]},
                        {"overlays": [self.overlay()] * (cli.OVERLAY_LIMIT + 1)},
                        {"overlay_scan_complete": 1}, {"overlay_coverage": []},
                        {"overlay_coverage": ["fixture_progression_guide", "other"]}):
            state = self.state(); state["ui"].update(changes)
            with self.subTest(changes=changes), self.assertRaises(cli.CliError):
                cli.validate_ui(state)

    def test_status_and_failed_responses_validate_any_ui_state(self):
        for success in (True, False):
            device = FakeAdb()
            state = self.state(self.overlay(id="sensitive-unmapped-label"))
            device.response_override = {"ok": success, "state": state,
                "error": None if success else {"code": "ACTION_UNAVAILABLE", "message": "Fixture error"}}
            result = device.client().execute("status")
            self.assertEqual(result["error"]["code"], "PROTOCOL_ERROR")
            self.assertNotIn("sensitive-unmapped-label", json.dumps(result))

    def test_valid_status_retains_hidden_overlay_observation(self):
        device = FakeAdb(); device.response_override = {"state": self.state(self.overlay())}
        result = device.client().execute("status")
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"]["ui"]["overlays"][0], self.overlay())
        self.assertEqual([request[4:] for request in device.requests], [["status", "none"]])

    def test_only_exact_pack_hint_can_offer_continue_under_input_blocker(self):
        taxonomy = {"tutorial": ("pack_selection_hint", "unknown_progression_guide")}
        with patch.object(cli, "OVERLAY_IDS", taxonomy), patch.object(cli, "OVERLAY_COVERAGE", ("progression_guide",)):
            overlay = self.overlay(kind="tutorial", id="pack_selection_hint")
            state = self.state(overlay)
            state["ui"]["overlay_coverage"] = ["progression_guide"]
            state["ui"]["reason"] = "input_blocked"
            state["ui"]["actions"] = [{"token": "pack_hint_continue." + "a" * 16,
                "name": "Continue pack selection guide", "enabled": True}]
            self.assertEqual(cli.validate_ui(state)["actions"][0]["name"], "Continue pack selection guide")
            state["ui"]["modal_present"] = True
            with self.assertRaisesRegex(cli.CliError, "modal"):
                cli.validate_ui(state)
            state["ui"]["modal_present"] = False
            state["ui"]["actions"] = [{"token": "pack_open." + "a" * 16, "name": "Pack Select", "enabled": True}]
            with self.assertRaisesRegex(cli.CliError, "interceptor"):
                cli.validate_ui(state)

    def test_unknown_inactive_or_incomplete_guide_cannot_offer_continue(self):
        taxonomy = {"tutorial": ("pack_selection_hint", "unknown_progression_guide")}
        with patch.object(cli, "OVERLAY_IDS", taxonomy), patch.object(cli, "OVERLAY_COVERAGE", ("progression_guide",)):
            for changes, complete in (({"id": "unknown_progression_guide"}, True), ({"active": False}, True),
                                      ({"active": None}, True), ({}, False)):
                state = self.state(self.overlay(**{"kind": "tutorial", "id": "pack_selection_hint", **changes}))
                state["ui"].update(overlay_coverage=["progression_guide"], overlay_scan_complete=complete,
                    actions=[{"token": "pack_hint_continue." + "a" * 16, "name": "Continue pack selection guide", "enabled": True}])
                with self.subTest(changes=changes, complete=complete), self.assertRaises(cli.CliError):
                    cli.validate_ui(state)


class ReusedDeadlineTests(unittest.TestCase):
    def test_prior_dispatch_does_not_mark_next_pre_dispatch_failure_unknown(self):
        device = FakeAdb(); client = device.client(timeout=1)
        self.assertTrue(client.execute('category', '8')['ok'])
        device.metadata['session'] = '2' * 32
        device.files['bridge.json'] = json.dumps(device.metadata).encode()
        result = client.execute('status')
        self.assertEqual(result['error']['code'], 'BRIDGE_RESTARTED')
        self.assertNotIn('outcome_unknown', result['error'])
        self.assertEqual(len(device.requests), 1)

    def test_prior_fill_does_not_own_later_credential_files(self):
        device = FakeAdb(); client = device.client(timeout=1)
        credentials = (bytearray(b'SyntheticUser'), bytearray(b'synthetic9'))
        self.assertTrue(client.execute('account', 'fill', credentials=credentials)['ok'])
        device.files['credential'] = b'later foreign fixture'
        self.assertTrue(client.execute('status')['ok'])
        self.assertEqual(device.files['credential'], b'later foreign fixture')
        self.assertFalse(client.credential_owned)

    def test_idle_before_first_execute_gets_full_command_budget(self):
        device = FakeAdb(); client = device.client(timeout=1)
        device.clock.sleep(5)
        self.assertTrue(client.execute('status')['ok'])
        self.assertEqual(client.deadline.end, 6)

    def test_same_client_two_commands_each_have_one_deadline(self):
        device = FakeAdb(); client = device.client(timeout=1)
        self.assertTrue(client.execute('status')['ok'])
        first = client.deadline.end
        device.clock.sleep(5)
        self.assertTrue(client.execute('status')['ok'])
        self.assertEqual(client.deadline.end, first + 5)
        self.assertEqual(len(device.requests), 2)

    def test_prior_action_runtime_does_not_shorten_next_admission(self):
        device = FakeAdb(); client = device.client(timeout=1)
        self.assertTrue(client.execute('status')['ok'])
        device.clock.sleep(0.9)
        self.assertTrue(client.execute('category', '8')['ok'])
        self.assertIn(int(device.requests[-1][3]), (1800000001122, 1800000001123))

    def test_one_command_never_gains_extra_budget_or_retry(self):
        device = FakeAdb(); client = device.client(timeout=1)
        self.assertTrue(client.execute('status')['ok'])
        device.clock.sleep(5); device.respond = False
        result = client.execute('category', '8')
        self.assertEqual(result['error']['code'], 'TIMEOUT')
        self.assertTrue(result['error']['outcome_unknown']); self.assertFalse(result['error']['automatic_retry'])
        self.assertEqual(len(device.requests), 2)
        self.assertLessEqual(device.clock.now, 6.000001)



if __name__ == "__main__":
    unittest.main()
