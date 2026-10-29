#!/usr/bin/env python3
"""Local, staging-only Akaine bridge client. Python standard library only."""

import argparse
import base64
import getpass
import json
from pathlib import Path
import re
import shlex
import subprocess
import struct
import sys
import time
import uuid
import warnings

import catalogue


PACKAGE = "akai.arc.lmao"
DIRECTORY = "files/akaine-cli-v1"
HEX_ID = re.compile(r"[0-9a-f]{32}\Z")
UI_CONTEXT = re.compile(r"[0-9a-f]{16}\Z")
UI_TOKEN = re.compile(r"(start_continue|main_music|pack_open|pack_hint_continue|main_hint_continue|notification_hint_continue|onboarding_setup|onboarding_cancel|onboarding_skip)\.([0-9a-f]{16})\Z")
UI_LABELS = {"start_continue": "Continue", "main_music": "Music", "pack_open": "Pack Select",
             "pack_hint_continue": "Continue pack selection guide", "main_hint_continue": "Continue main menu guide", "notification_hint_continue": "Continue notification guide (requests Android permission)", "onboarding_setup": "Setup",
             "onboarding_cancel": "Cancel offset setup", "onboarding_skip": "Confirm skip offset setup"}
UI_REASONS = {None, "unsupported_modal", "loading", "unsupported_scene", "unavailable", "unsupported_ui_tree", "not_ready",
              "input_blocked", "tutorial_active", "overlay_scan_incomplete", "native_bundle_error"}
OVERLAY_LIMIT = 16
OVERLAY_IDS = {"tutorial": ("pack_selection_hint", "main_menu_hint", "notification_permission_guide", "unknown_progression_guide", "note_speed_setup")}
OVERLAY_COVERAGE = ("progression_guide", "note_speed_setup")
GUIDE_FIELDS = {"step_index", "pending_steps", "advance_ready", "can_advance", "can_set_speed",
                "owner_validated", "callback_owned", "listener_registered", "listener_paused",
                "listener_enabled", "listener_swallow"}
GUIDE_ACTIONS = {"onboarding_setup", "onboarding_cancel", "onboarding_skip", "main_hint_continue",
                 "notification_hint_continue", "pack_hint_continue"}
SERIAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
MAX_JSON = 16384
LOG_TAGS = ("AkaineAnomalyMonitor:I", "AkaineCLI:I", "AndroidRuntime:E", "libc:F", "DEBUG:F", "*:S")
NATIVE_SORTS = ("title", "difficulty", "date", "grade", "clear", "artist")
NATIVE_GROUPS = ("pack", "version", "level", "grade", "clear", "available")
DOMAIN_COMMANDS = {"song_select", "difficulty", "sort", "group", "reverse", "pack_select", "pack_close", "character", "account", "sync", "replay", "play", "play_download", "play_guide", "play_set_speed", "filter", "skill", "navigation", "gameplay", "settings", "bundle"}
ACCOUNT_ERRORS = {
    "connection_failed": "Could not connect to online server.",
    "invalid_credentials": "Username or password incorrect.",
    "account_locked": "This account is locked.",
    "maintenance": "The Arcaea network is currently under maintenance.",
    "unknown_error": "An unknown error has occurred.", "unrecognized": None}
CREDENTIAL_LIMIT = 512
TERMS_URL = "https://arcaea.lowiro.com/terms_of_service"
PRIVACY_URL = "https://arcaea.lowiro.com/privacy_policy"
_terms_tickets = set()


class CliError(Exception):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details

    def result(self):
        return {"ok": False, "error": {"code": self.code, "message": self.message, **self.details}}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse messages can echo unexpected argv, including pasted secrets.
        raise CliError("ARGUMENT_ERROR", "Invalid command or arguments; run --help for supported options.")


class Deadline:
    def __init__(self, seconds, clock=time.monotonic):
        if not 1 <= seconds <= 30:
            raise CliError("ARGUMENT_ERROR", "--timeout must be between 1 and 30 seconds.")
        self.clock = clock
        self.end = clock() + seconds

    def remaining(self):
        value = self.end - self.clock()
        if value <= 0:
            raise CliError("TIMEOUT", "The operation deadline expired.")
        return value


class Adb:
    def __init__(self, executable, serial, runner=subprocess.run):
        if not serial or not SERIAL.fullmatch(serial):
            raise CliError("INVALID_SERIAL", "Supply one explicit ADB serial without whitespace or shell characters.")
        self.executable, self.serial, self.runner = executable, serial, runner

    def call(self, arguments, timeout, data=None, allow_failure=False):
        try:
            result = self.runner(
                [self.executable, "-s", self.serial, *arguments], input=data,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired:
            raise CliError("TIMEOUT", "ADB did not finish before the operation deadline.") from None
        except OSError:
            raise CliError("ADB_UNAVAILABLE", "Could not execute ADB; check --adb.") from None
        if result.returncode and not allow_failure:
            raise CliError("ADB_FAILED", "ADB or the app-private operation failed.")
        return result

    def shell(self, script, deadline, data=None, allow_failure=False):
        # ADB joins the remote argv into one shell command; quote the whole script.
        # shell v2 preserves the remote exit code; exec-out does not.
        return self.call(["shell", "-T", "run-as", PACKAGE, "sh", "-c", shlex.quote(script)],
                         deadline.remaining(), data, allow_failure)

    def read(self, filename, deadline, optional=False):
        if filename not in ("bridge.json", "response.json"):
            raise ValueError("Only protocol JSON files may be read.")
        path = f"{DIRECTORY}/{filename}"
        # Fixed paths only. Never follow a bridge-directory or file symlink.
        script = (f"test -d {DIRECTORY} && test ! -L {DIRECTORY} && "
                  f"test -f {path} && test ! -L {path} && head -c {MAX_JSON + 1} {path}")
        result = self.shell(script, deadline, allow_failure=optional)
        if result.returncode:
            return None
        if len(result.stdout) > MAX_JSON:
            raise CliError("PROTOCOL_ERROR", "Bridge JSON exceeds the protocol limit.")
        try:
            value = json.loads(result.stdout)
        except (UnicodeDecodeError, ValueError):
            raise CliError("PROTOCOL_ERROR", "Bridge returned invalid JSON.") from None
        if not isinstance(value, dict):
            raise CliError("PROTOCOL_ERROR", "Bridge JSON must be an object.")
        return value


def validate_identity(metadata, live_pid):
    if (metadata.get("protocol") != 1 or type(metadata.get("protocol")) is not int or
            metadata.get("environment") != "staging" or metadata.get("package") != PACKAGE):
        raise CliError("NOT_STAGING", "The app is not the expected staging bridge.")
    if (type(metadata.get("pid")) is not int or metadata["pid"] <= 0 or
            not isinstance(metadata.get("session"), str) or not HEX_ID.fullmatch(metadata["session"]) or
            not isinstance(metadata.get("commands"), list) or
            not all(isinstance(command, str) for command in metadata["commands"])):
        raise CliError("PROTOCOL_ERROR", "Bridge identity is malformed.")
    if live_pid != str(metadata["pid"]):
        raise CliError("STALE_BRIDGE", "Bridge metadata does not match the live app PID.")
    return metadata


def redact_logs(raw):
    """Drop credential/account lines; scrub unlabelled tokens before any disk write."""
    sensitive = re.compile(
        r"\b(?:access[_-]?token|refresh[_-]?token|token|password|passwd|pwd|authorization|"
        r"cookie|api[_-]?key|secret|signature|email|username|user[_-]?(?:id|code|name)|"
        r"player[_-]?(?:id|code|name)|account[_-]?(?:id|name))[\"']?\s*[:=]", re.I)
    lines = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        normalized = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m[1], 16)), line)
        normalized = re.sub(r"\\+([\"'])", r"\1", normalized)
        if sensitive.search(normalized):
            lines.append("[REDACTED sensitive diagnostic line]")
            continue
        line = re.sub(r"\bBearer\s+[^\s\"'<>]+", "Bearer [REDACTED]", line, flags=re.I)
        line = re.sub(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
                      "[REDACTED email]", line)
        line = re.sub(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{8,}",
                      "[REDACTED token]", line)
        line = re.sub(r"(?<![A-Za-z0-9_+/-])[A-Za-z0-9_+/-]{32,}={0,2}(?![A-Za-z0-9_+/-])",
                      "[REDACTED token]", line)
        lines.append(line)
    return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")


def validate_overlays(ui):
    overlays, coverage = ui.get("overlays"), ui.get("overlay_coverage")
    if (type(ui.get("overlay_scan_complete")) is not bool or not isinstance(overlays, list)
            or len(overlays) > OVERLAY_LIMIT or not isinstance(coverage, list)
            or coverage != list(OVERLAY_COVERAGE)):
        raise CliError("PROTOCOL_ERROR", "UI overlay scan does not match its bounded coverage contract.")
    seen = set()
    for overlay in overlays:
        base = {"kind", "id", "active", "visible", "opacity", "blocks_input"}
        if not isinstance(overlay, dict) or set(overlay) not in (base, base | GUIDE_FIELDS):
            raise CliError("PROTOCOL_ERROR", "UI overlay entry does not match the public status contract.")
        if GUIDE_FIELDS <= set(overlay):
            if (type(overlay["step_index"]) is not int or not 0 <= overlay["step_index"] <= 4096
                    or type(overlay["pending_steps"]) is not int or not 0 <= overlay["pending_steps"] <= 128
                    or any(type(overlay[key]) is not bool for key in GUIDE_FIELDS - {"step_index", "pending_steps"})):
                raise CliError("PROTOCOL_ERROR", "Native guide workflow fields are malformed.")
        kind, identifier = overlay["kind"], overlay["id"]
        if (not isinstance(kind, str) or kind not in OVERLAY_IDS or not isinstance(identifier, str)
                or identifier not in OVERLAY_IDS[kind] or (kind, identifier) in seen):
            raise CliError("PROTOCOL_ERROR", "UI overlay identity is unknown or duplicated.")
        seen.add((kind, identifier))
        if (any(overlay[key] is not None and type(overlay[key]) is not bool for key in ("active", "visible", "blocks_input"))
                or overlay["opacity"] is not None and (type(overlay["opacity"]) is not int or not 0 <= overlay["opacity"] <= 255)):
            raise CliError("PROTOCOL_ERROR", "UI overlay flags or opacity are invalid.")
    return overlays


def validate_ui(state):
    ui = state.get("ui")
    if (not isinstance(ui, dict) or not isinstance(ui.get("context"), str) or
            not UI_CONTEXT.fullmatch(ui["context"]) or not isinstance(ui.get("actions"), list) or
            len(ui["actions"]) > len(UI_LABELS)):
        raise CliError("PROTOCOL_ERROR", "UI state is missing its bounded context and actions.")
    reason = ui.get("reason")
    if (type(ui.get("modal_present")) is not bool or
            (reason is not None and not isinstance(reason, str)) or reason not in UI_REASONS):
        raise CliError("PROTOCOL_ERROR", "UI modal state is invalid.")
    if "guide_metadata_version" in ui and (type(ui["guide_metadata_version"]) is not int
            or ui["guide_metadata_version"] != 1 or type(ui.get("onboarding_settings_ready")) is not bool
            or type(ui.get("note_speed_modal_ready")) is not bool):
        raise CliError("PROTOCOL_ERROR", "Native guide metadata version is malformed.")
    onboarding = ui.get("onboarding_stage")
    onboarding_actions = {"welcome": "onboarding_setup", "offset_setup": "onboarding_cancel",
                          "offset_skip_confirmation": "onboarding_skip"}
    if onboarding is not None and (not isinstance(onboarding, str) or onboarding not in onboarding_actions):
        raise CliError("PROTOCOL_ERROR", "Unknown onboarding stage.")
    if ui["modal_present"] and ui["actions"]:
        expected = onboarding_actions.get(onboarding)
        if (not expected or state.get("screen") != "main_menu" or reason is not None
                or len(ui["actions"]) != 1 or not isinstance(ui["actions"][0], dict)
                or ui["actions"][0].get("token") != expected + "." + ui["context"]):
            raise CliError("PROTOCOL_ERROR", "Unsupported modal must block underlying scene actions.")
    overlays = validate_overlays(ui)
    blocking = any(overlay["blocks_input"] is True for overlay in overlays)
    known_hint = any(overlay["kind"] == "tutorial" and overlay["id"] == "pack_selection_hint"
                     and overlay["active"] is True for overlay in overlays)
    unknown_blocker = any(overlay["blocks_input"] is True and
                          (overlay["kind"], overlay["id"]) != ("tutorial", "pack_selection_hint") for overlay in overlays)
    if blocking and any(not isinstance(action, dict) or not isinstance(action.get("token"), str)
                        or not action["token"].startswith(("pack_hint_continue.", "main_hint_continue.", "notification_hint_continue.")) for action in ui["actions"]):
        raise CliError("PROTOCOL_ERROR", "A native input interceptor must block underlying scene actions.")
    main_hint = any(overlay["kind"] == "tutorial" and overlay["id"] == "main_menu_hint"
                    and overlay["active"] is True for overlay in overlays)
    if main_hint:
        unknown_blocker = any(overlay["blocks_input"] is True and
            (overlay["kind"], overlay["id"]) != ("tutorial", "main_menu_hint") for overlay in overlays)
    notification_hint = any(overlay["kind"] == "tutorial" and overlay["id"] == "notification_permission_guide"
                            and overlay["active"] is True for overlay in overlays)
    notification_blocker = any(overlay["blocks_input"] is True and
        (overlay["kind"], overlay["id"]) != ("tutorial", "notification_permission_guide") for overlay in overlays)
    seen = set()
    for action in ui["actions"]:
        if not isinstance(action, dict) or not isinstance(action.get("token"), str):
            raise CliError("PROTOCOL_ERROR", "UI action is malformed.")
        token = UI_TOKEN.fullmatch(action["token"])
        if (not token or token[2] != ui["context"] or action.get("name") != UI_LABELS[token[1]] or
                type(action.get("enabled")) is not bool or token[1] in seen):
            raise CliError("PROTOCOL_ERROR", "UI action does not match the fixed staging action contract.")
        if token[1].startswith("onboarding_") and (not ui["modal_present"]
                or onboarding_actions.get(onboarding) != token[1] or not ui["overlay_scan_complete"]):
            raise CliError("PROTOCOL_ERROR", "Onboarding action requires its exact native modal stage.")
        if token[1] == "notification_hint_continue" and (not notification_hint or notification_blocker
                or state.get("screen") != "main_menu" or not ui["overlay_scan_complete"]):
            raise CliError("PROTOCOL_ERROR", "Notification continuation requires its exact active native guide.")
        if token[1] == "main_hint_continue" and (not main_hint or unknown_blocker
                or state.get("screen") != "main_menu" or not ui["overlay_scan_complete"]):
            raise CliError("PROTOCOL_ERROR", "Main menu continuation requires its exact active native guide.")
        if token[1] == "pack_hint_continue" and (not known_hint or unknown_blocker or not ui["overlay_scan_complete"]):
            raise CliError("PROTOCOL_ERROR", "Guide continuation requires the exact active native pack hint.")
        seen.add(token[1])
    return ui


def validate_advanced_guide(state):
    value = state.get("advanced_guide")
    if value is None:
        return None  # Legacy commands still accept V34 responses.
    if (not isinstance(value, dict) or set(value) != {"available", "can_skip", "reason", "priority", "song_id", "difficulty"}
            or type(value["available"]) is not bool or type(value["can_skip"]) is not bool
            or value["reason"] is not None and not isinstance(value["reason"], str)
            or value["priority"] not in ("unavailable", "single_modal", "unproven")):
        raise CliError("PROTOCOL_ERROR", "Native advanced guide metadata is malformed.")
    if not value["available"]:
        if value["can_skip"] or value["song_id"] is not None or value["difficulty"] is not None or value["priority"] != "unavailable":
            raise CliError("PROTOCOL_ERROR", "Unavailable advanced guide exposes an action.")
        return value
    song, ui = state.get("song_selection"), state.get("ui")
    if (state.get("screen") != "song_select" or not isinstance(song, dict) or not isinstance(ui, dict)
            or ui.get("modal_present") is not True or not isinstance(value["song_id"], str)
            or not catalogue.ID.fullmatch(value["song_id"]) or value["song_id"] != song.get("song_id")
            or type(value["difficulty"]) is not int or not 0 <= value["difficulty"] <= 4
            or value["difficulty"] != song.get("selected_difficulty", song.get("difficulty"))):
        raise CliError("PROTOCOL_ERROR", "Advanced guide selection or modal identity is inconsistent.")
    blocked = any(item.get("active") is True or item.get("blocks_input") is True for item in ui.get("overlays", []))
    if (value["can_skip"] and (value["priority"] != "single_modal" or value["reason"] is not None
            or blocked or ui.get("overlays") or ui.get("overlay_scan_complete") is not True)
            or not value["can_skip"] and (value["priority"] != "unproven" or not value["reason"])):
        raise CliError("PROTOCOL_ERROR", "Advanced guide priority does not authorize this action.")
    return value


def guide_status(state):
    """Choose at most one known guide callback; no consent, download or Play action."""
    ui = validate_ui(state)
    if ui.get("guide_metadata_version") != 1 or any(not GUIDE_FIELDS <= set(item) for item in ui["overlays"]):
        raise CliError("UNSUPPORTED_GUIDE_METADATA", "This guide command requires explicit native guide metadata.")
    advanced = validate_advanced_guide(state)
    if advanced is None:
        raise CliError("UNSUPPORTED_GUIDE_METADATA", "This guide command requires native advanced-guide discovery.")
    def result(status, kind=None, command=None, argument=None, reason=None):
        return {"status": status, "kind": kind,
                "action": {"command": command, "argument": argument} if command else None,
                "reason": reason, "may_continue_play": command in ("play_guide", "play_set_speed"),
                "effect": "requests_android_notification_permission" if kind == "notification_hint_continue" else None}
    if not ui["overlay_scan_complete"]:
        return result("blocked", reason="overlay_scan_incomplete")
    if advanced["available"]:
        if advanced["can_skip"]:
            return result("action", "advanced_tutorial", "play_guide", advanced["song_id"])
        return result("blocked", "advanced_tutorial", reason=advanced["reason"])
    actions = [action for action in ui["actions"] if action["enabled"]
               and action["token"].split(".", 1)[0] in GUIDE_ACTIONS]
    if len(actions) > 1:
        return result("blocked", reason="ambiguous_guide_actions")
    if actions:
        action = actions[0]
        kind = action["token"].split(".", 1)[0]
        if kind.endswith("hint_continue") and (len(ui["overlays"]) != 1
                or not ui["overlays"][0]["can_advance"] or not ui["overlays"][0]["owner_validated"]
                or not ui["overlays"][0]["callback_owned"] or not ui["overlays"][0]["advance_ready"]):
            raise CliError("PROTOCOL_ERROR", "Guide action lacks its verified native readiness.")
        return result("action", kind, "ui", action["token"])
    overlays = ui["overlays"]
    if len(overlays) == 1 and overlays[0]["id"] == "note_speed_setup":
        item, song = overlays[0], state.get("song_selection")
        if (item["can_set_speed"] and item["owner_validated"] and item["callback_owned"]
                and isinstance(song, dict) and catalogue.ID.fullmatch(str(song.get("song_id", "")))
                and ui["modal_present"] and ui.get("note_speed_modal_ready") is True):
            return result("action", "note_speed_setup", "play_set_speed", song["song_id"])
        return result("wait", "note_speed_setup", reason="note_speed_not_ready")
    if overlays:
        if any(item["id"] == "unknown_progression_guide" for item in overlays):
            return result("blocked", reason="unknown_progression_guide")
        if len(overlays) != 1 or ui["modal_present"]:
            return result("blocked", reason="competing_guide_or_modal")
        item = overlays[0]
        status = "wait" if not item["advance_ready"] or not item["active"] and not item["blocks_input"] else "blocked"
        return result(status, item["id"], reason="guide_not_ready" if status == "wait" else "guide_action_unavailable")
    control = state.get("settings_control", {})
    if ui.get("onboarding_settings_ready") is True and not isinstance(control, dict):
        raise CliError("PROTOCOL_ERROR", "Onboarding Settings control metadata is malformed.")
    if (ui.get("onboarding_settings_ready") is True and state.get("screen") == "main_menu"
            and control.get("open") is True and control.get("can_close") is True):
        return result("action", "onboarding_settings", "settings", "close")
    if ui["modal_present"]:
        return result("blocked", reason="unsupported_modal")
    if ui["reason"] in ("loading", "not_ready"):
        return result("wait", reason=ui["reason"])
    if ui["reason"] in ("input_blocked", "tutorial_active", "unsupported_ui_tree", "unavailable", "native_bundle_error"):
        return result("blocked", reason=ui["reason"])
    return result("none", reason="no_known_guide")


def domain_argument(command, argument):
    if not isinstance(argument, str):
        return False
    if command in ("song_select", "pack_select", "play", "play_download", "play_guide", "play_set_speed"):
        return catalogue.ID.fullmatch(argument) is not None
    if command == "pack_close":
        return argument == "none"
    if command in ("difficulty", "sort", "group", "reverse", "replay"):
        return argument in tuple(str(i) for i in range({"difficulty": 5, "sort": 6, "group": 6, "reverse": 2, "replay": 2}[command]))
    if command == "character":
        return argument in ("status", "list", "open", "close") or re.fullmatch(r"(?:0|[1-9][0-9]{0,4})", argument) is not None
    if command == "account":
        return argument in ("status", "open", "login_open", "fill", "submit", "terms_accept", "management_open", "logout")
    if command == "sync":
        return argument in ("status", "download")
    if command == "bundle":
        return argument in ("status", "confirm", "dismiss-error")
    if command == "skill":
        return argument in ("status", "seal:0", "seal:1")
    if command == "settings":
        if argument in ("fps:0", "fps:1"):
            return True
        if argument in ("status", "open", "close"):
            return True
        if re.fullmatch(r"speed:(?:[1-5][0-9]|6[0-5])", argument):
            return True
        return (re.fullmatch(r"offset:(?:0|-?[1-9][0-9]{0,3})", argument) is not None
                and -2000 <= int(argument[7:]) <= 2000)
    if command == "navigation":
        return argument in ("status", "back", "continue", "retry")
    if command == "gameplay":
        return argument in ("status", "pause", "resume", "retry", "quit")
    if command == "filter":
        if argument in ("status", "open", "close", "reset"):
            return True
        if not argument.startswith("query:") or not re.fullmatch(r"[A-Za-z0-9_-]{2,171}", argument[6:]):
            return False
        try:
            data = base64.urlsafe_b64decode(argument[6:] + "=" * (-len(argument[6:]) % 4))
            query = data.decode("utf-8")
            return encode_query(query) == argument
        except (ValueError, UnicodeError, CliError):
            return False
    return False


def encode_query(query):
    if not isinstance(query, str) or any(ord(ch) < 32 or 127 <= ord(ch) <= 159 for ch in query):
        raise CliError("ARGUMENT_ERROR", "Native query must be text without control characters.")
    try:
        data = query.encode("utf-8")
    except UnicodeError:
        raise CliError("ARGUMENT_ERROR", "Native query must be valid UTF-8.") from None
    if not 1 <= len(data) <= 128:
        raise CliError("ARGUMENT_ERROR", "Native query must contain 1-128 UTF-8 bytes; use filter reset to clear.")
    return "query:" + base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def note_speed_argument(text):
    if not re.fullmatch(r"(?:[1-5](?:\.[0-9])?|6(?:\.[0-5])?)", text):
        raise CliError("ARGUMENT_ERROR", "Note speed must be 1.0-6.5 in steps of 0.1.")
    whole, _, fraction = text.partition(".")
    return str(int(whole) * 10 + int(fraction or "0"))


def offset_argument(text):
    if not re.fullmatch(r"-?(?:0|[1-9][0-9]{0,3})", text) or not -2000 <= int(text) <= 2000:
        raise CliError("ARGUMENT_ERROR", "Offset must be an integer between -2000 and 2000 milliseconds.")
    return str(int(text))


def mutation(command, argument):
    return (command == "category" or command == "ui" and argument != "list"
            or command in DOMAIN_COMMANDS and (command, argument) not in
            (("character", "status"), ("character", "list"), ("account", "status"), ("sync", "status"),
             ("filter", "status"), ("skill", "status"), ("navigation", "status"), ("gameplay", "status"), ("settings", "status"), ("bundle", "status")))


def credential_bytes(value):
    if not isinstance(value, dict) or set(value) != {"username", "password"}:
        raise CliError("CREDENTIAL_INPUT", "Supply only username and password in the credentials object.")
    output = []
    for name, limit in (("username", 64), ("password", 256)):
        text = value[name]
        if not isinstance(text, str) or not text or any(ord(c) < 32 or ord(c) == 127 for c in text):
            raise CliError("CREDENTIAL_INPUT", "Credentials must be nonempty text without control characters.")
        try:
            encoded = text.encode("utf-8")
        except UnicodeError:
            raise CliError("CREDENTIAL_INPUT", "Credentials must contain valid UTF-8 text.") from None
        if len(encoded) > limit:
            raise CliError("CREDENTIAL_INPUT", "Username exceeds 64 bytes or password exceeds 256 bytes.")
        output.append(bytearray(encoded))
    return tuple(output)


def read_credentials(from_stdin=False):
    if not from_stdin:
        if not sys.stdin.isatty():
            raise CliError("CREDENTIAL_INPUT", "Use --credentials-stdin for a noninteractive credentials stream.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                return credential_bytes({"username": getpass.getpass("Username (hidden): ", stream=sys.stderr),
                                         "password": getpass.getpass("Password: ", stream=sys.stderr)})
        except (EOFError, getpass.GetPassWarning):
            raise CliError("CREDENTIAL_INPUT", "Hidden terminal input is unavailable; use --credentials-stdin.") from None
    stream = getattr(sys.stdin, "buffer", sys.stdin)
    raw = stream.read(CREDENTIAL_LIMIT + 1)
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if len(raw) > CREDENTIAL_LIMIT:
        raise CliError("CREDENTIAL_INPUT", "Credentials JSON exceeds 512 bytes.")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate field")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError):
        raise CliError("CREDENTIAL_INPUT", "Credentials stdin must contain one valid JSON object.") from None
    return credential_bytes(value)


def confirm_terms():
    """Create a one-use dispatch ticket only after a person's exact TTY reply."""
    if not sys.stdin.isatty():
        raise CliError("TERMS_INTERACTIVE_REQUIRED", "Run account terms-accept yourself in an interactive terminal.")
    sys.stderr.write("This command presses the game's native 'I Agree' for online-service Terms of Service and Privacy Policy.\n"
                     f"Terms of Service: {TERMS_URL}\nPrivacy Policy: {PRIVACY_URL}\n"
                     "Read both documents yourself. Acceptance records the game's normal consent preference.\n"
                     "It does not fill credentials or submit login. Type exactly AGREE to accept, or anything else to cancel: ")
    sys.stderr.flush()
    if sys.stdin.readline(64).rstrip("\r\n") != "AGREE":
        raise CliError("TERMS_NOT_ACCEPTED", "Legal agreement was not confirmed; no action was sent.")
    ticket = object()
    _terms_tickets.add(ticket)
    return ticket


def validate_domain_response(state, command, argument):
    if command == "bundle":
        value = state.get("bundle")
        if (not isinstance(value, dict) or set(value) != {"available", "phase", "can_confirm", "pending_versions", "pending_bytes", "reason"}
                or any(type(value.get(key)) is not bool for key in ("available", "can_confirm"))
                or value.get("phase") not in ("unavailable", "ready", "confirmation", "downloading", "failed")
                or not isinstance(value.get("pending_versions"), list) or len(value["pending_versions"]) > 16
                or any(not isinstance(version, str) or not re.fullmatch(r"7\.0\.255\.[0-9]{1,9}", version) for version in value["pending_versions"])
                or value.get("pending_bytes") is not None and (type(value["pending_bytes"]) is not int or not 0 <= value["pending_bytes"] <= 2**63 - 1)
                or value.get("reason") is not None and not isinstance(value["reason"], str)):
            raise CliError("PROTOCOL_ERROR", "Native bundle state does not match its bounded public contract.")
        if value["can_confirm"] and (not value["available"] or value["phase"] != "confirmation" or value["reason"] is not None):
            raise CliError("PROTOCOL_ERROR", "Bundle confirmation is available outside its exact native prompt.")
        if argument == "confirm" and (not value["available"] or value["phase"] not in ("downloading", "ready") or value["can_confirm"] or value["reason"] is not None):
            raise CliError("PROTOCOL_ERROR", "Native bundle confirmation did not observe download progress or readiness.")
        if argument == "dismiss-error" and (not value["available"] or value["phase"] == "failed"):
            raise CliError("PROTOCOL_ERROR", "Native bundle error dismissal was not observed.")
    elif command == "settings":
        value = state.get("settings")
        if not isinstance(value, dict) or type(value.get("available")) is not bool or type(value.get("panel_open")) is not bool:
            raise CliError("PROTOCOL_ERROR", "Native settings state is malformed.")
        control = state.get("settings_control")
        if (not isinstance(control, dict) or any(type(control.get(key)) is not bool for key in
                ("available", "open", "can_open", "can_close", "can_set_note_speed", "can_set_offset"))
                or control.get("reason") is not None and not isinstance(control["reason"], str)):
            raise CliError("PROTOCOL_ERROR", "Native settings control state is malformed.")
        if argument != "status":
            if not control["available"] or control.get("reason") is not None:
                raise CliError("PROTOCOL_ERROR", "Native settings control did not finish the requested operation.")
            if argument in ("open", "close"):
                if (control["open"] != (argument == "open") or value["panel_open"] != control["open"]
                        or not control["can_close" if argument == "open" else "can_open"]):
                    raise CliError("PROTOCOL_ERROR", "Native settings panel did not reach the requested state.")
            elif argument.startswith("fps:"):
                if (not value["available"] or not value["panel_open"] or not control["open"]
                        or control.get("can_set_high_framerate") is not True
                        or type(value.get("high_framerate_v2")) is not bool
                        or value["high_framerate_v2"] != (argument == "fps:1")):
                    raise CliError("PROTOCOL_ERROR", "Native frame-rate setting did not confirm the requested value.")
            else:
                speed = argument.startswith("speed:")
                key = "highspeed_int" if speed else "active_offset_ms"
                if (not value["available"] or not value["panel_open"] or not control["open"]
                        or not control["can_set_note_speed" if speed else "can_set_offset"]
                        or type(value.get(key)) is not int or value[key] != int(argument.split(":", 1)[1])):
                    raise CliError("PROTOCOL_ERROR", "Native setting did not confirm the requested persisted value.")
    elif command == "filter":
        value = state.get("filter")
        if (not isinstance(value, dict) or any(type(value.get(key)) is not bool for key in ("valid", "open", "ready"))
                or type(value.get("count")) is not int or not 0 <= value["count"] <= 8192
                or any(type(value.get(key)) is not int or not 0 <= value[key] <= 5 for key in ("sort", "group"))
                or type(value.get("reverse")) is not int or value["reverse"] not in (0, 1)
                or value.get("query") is not None and not isinstance(value["query"], str)):
            raise CliError("PROTOCOL_ERROR", "Native filter state is malformed.")
        if argument != "status":
            if not value["valid"] or not value["ready"]:
                raise CliError("PROTOCOL_ERROR", "Native filter did not finish the requested operation.")
            if argument in ("open", "close") and value["open"] != (argument == "open"):
                raise CliError("PROTOCOL_ERROR", "Native filter dialog did not reach its requested state.")
            if argument == "reset" and (value.get("query") != "" or (value["sort"], value["group"], value["reverse"]) != (1, 0, 0)):
                raise CliError("PROTOCOL_ERROR", "Native filter reset did not confirm its normal defaults.")
            if argument.startswith("query:") and (not value["open"] or encode_query(value.get("query")) != argument):
                raise CliError("PROTOCOL_ERROR", "Native filter query did not match the requested text.")
    elif command == "skill":
        value = state.get("skill")
        if (not isinstance(value, dict) or type(value.get("available")) is not bool
                or any(value.get(key) is not None and type(value[key]) is not bool for key in ("native_skill_sealed", "suppression"))
                or not isinstance(value.get("gameplay"), dict)):
            raise CliError("PROTOCOL_ERROR", "Native skill state is malformed.")
        if argument.startswith("seal:") and value.get("native_skill_sealed") is not (argument == "seal:1"):
            raise CliError("PROTOCOL_ERROR", "Native skill seal did not match the requested value.")
    elif command in ("navigation", "gameplay"):
        value = state.get("navigation")
        if (not isinstance(value, dict) or type(value.get("available")) is not bool
                or value.get("scene") not in ("unsupported", "song_select", "result", "gameplay")
                or value.get("paused") is not None and type(value["paused"]) is not bool
                or any(type(value.get("can_" + name)) is not bool for name in ("back", "continue", "pause", "resume", "retry", "quit"))):
            raise CliError("PROTOCOL_ERROR", "Native navigation state is malformed.")
        if argument in ("pause", "resume") and (state.get("gameplay") is not True or value.get("paused") is not (argument == "pause")):
            raise CliError("PROTOCOL_ERROR", "Native gameplay pause state did not match the request.")
        if argument == "retry" and (state.get("gameplay") is not True or state.get("screen") != "gameplay"):
            raise CliError("PROTOCOL_ERROR", "Native retry did not confirm gameplay.")
        if argument in ("quit", "continue") and state.get("screen") != "song_select":
            raise CliError("PROTOCOL_ERROR", "Native navigation did not confirm song selection.")
        if argument == "back" and state.get("screen") not in ("song_select", "main_menu"):
            raise CliError("PROTOCOL_ERROR", "Native Back did not confirm the expected menu.")
    elif command == "replay":
        if type(state.get("anomaly_replay")) is not bool or state["anomaly_replay"] != (argument == "1"):
            raise CliError("PROTOCOL_ERROR", "Native response did not confirm Anomaly Replay.")
    elif command == "play_set_speed":
        ui = validate_ui(state)
        if ui["overlay_scan_complete"] is not True or any(overlay["id"] == "note_speed_setup" for overlay in ui["overlays"]):
            raise CliError("PROTOCOL_ERROR", "Native note-speed setup is still present or its scan is incomplete.")
        if state.get("gameplay") is True:
            validate_domain_response(state, "play", argument)
        else:
            song = state.get("song_selection")
            if (state.get("screen") != "song_select" or not isinstance(song, dict) or song.get("song_id") != argument
                    or type(song.get("difficulty")) is not int or not 0 <= song["difficulty"] <= 4):
                raise CliError("PROTOCOL_ERROR", "Native note-speed setup did not confirm the expected song.")
    elif command == "play_guide" and state.get("gameplay") is True:
        validate_domain_response(state, "play", argument)
    elif command in ("play_download", "play_guide"):
        song, ui = state.get("song_selection"), state.get("ui")
        if (state.get("screen") != "song_select" or not isinstance(song, dict) or song.get("song_id") != argument
                or type(song.get("difficulty")) is not int or not 0 <= song["difficulty"] <= 4
                or not isinstance(ui, dict) or ui.get("modal_present") is not False
                or ui.get("overlay_scan_complete") is not True or ui.get("reason") is not None):
            raise CliError("PROTOCOL_ERROR", "Native preplay UI did not return to the requested song selection.")
    elif command == "play":
        if (state.get("gameplay") is not True or state.get("screen") != "gameplay"
                or state.get("song_id") != argument or type(state.get("difficulty")) is not int
                or not 0 <= state["difficulty"] <= 4):
            raise CliError("PROTOCOL_ERROR", "Native response did not confirm gameplay for the requested song.")
    elif command == "sync":
        sync = state.get("sync")
        if (not isinstance(sync, dict) or set(sync) != {"phase", "error_code", "download_only", "can_download"}
                or sync["phase"] not in ("unavailable", "ready", "fetching", "applying", "success", "failed")
                or sync["error_code"] is not None and (type(sync["error_code"]) is not int or not -2147483648 <= sync["error_code"] <= 2147483647)
                or sync["download_only"] is not True or type(sync["can_download"]) is not bool):
            raise CliError("PROTOCOL_ERROR", "Cloud Sync response does not match the download-only public status contract.")
        if argument == "download" and sync["phase"] != "success":
            raise CliError("PROTOCOL_ERROR", "Native response did not confirm Cloud Sync Download completion.")
    elif command in ("song_select", "difficulty", "sort", "group", "reverse", "pack_select", "pack_close"):
        song = state.get("song_selection")
        if not isinstance(song, dict):
            raise CliError("PROTOCOL_ERROR", "Song response is missing native selection state.")
        if command in ("song_select", "pack_select"):
            key = "song_id" if command == "song_select" else "pack_id"
            confirmed = song.get(key) == argument
            if command == "pack_select":
                confirmed = confirmed and song.get("pack_open") is False
        elif command == "pack_close":
            confirmed = song.get("pack_open") is False
        elif command == "reverse":
            confirmed = type(song.get("reverse")) is bool and song["reverse"] == (argument == "1")
        else:
            confirmed = type(song.get(command)) is int and song[command] == int(argument)
        if not confirmed:
            raise CliError("PROTOCOL_ERROR", "Native response did not confirm the requested song control.")
    elif command == "character":
        character = state.get("character")
        if not isinstance(character, dict):
            raise CliError("PROTOCOL_ERROR", "Character response is missing native state.")
        if argument == "open" and character.get("dialog_open") is not True or argument == "close" and character.get("dialog_open") is not False:
            raise CliError("PROTOCOL_ERROR", "Native response did not confirm the character dialog.")
        if argument.isdecimal() and (type(character.get("preview_id")) is not int or character["preview_id"] != int(argument)):
            raise CliError("PROTOCOL_ERROR", "Native response did not confirm the selected character preview.")
        if argument == "list" and (not isinstance(character.get("owned_ids"), list)
                or len(character["owned_ids"]) > 4096 or any(type(i) is not int or i < 0 or i > 99999 for i in character["owned_ids"])):
            raise CliError("PROTOCOL_ERROR", "Owned-character response is malformed.")
    elif command == "account":
        account = state.get("account")
        allowed = {"kind", "signed_in", "blocked", "can_open", "can_login_open", "can_fill", "can_submit", "can_accept_terms"}
        if (not isinstance(account, dict) or set(account) - allowed - {"error_code", "error_text", "can_management_open", "can_logout"}
                or account.get("kind") not in ("main_menu", "unavailable", "logged_out_menu", "logged_in_menu", "login_terms_required", "login", "account_management")
                or account.get("signed_in") is not None and type(account["signed_in"]) is not bool
                or any(type(account.get(key)) is not bool for key in allowed - {"kind", "signed_in"})):
            raise CliError("PROTOCOL_ERROR", "Account response does not match the public status contract.")
        management_fields = {"can_management_open", "can_logout"} & set(account)
        if management_fields and (management_fields != {"can_management_open", "can_logout"}
                or any(type(account[key]) is not bool for key in management_fields)):
            raise CliError("PROTOCOL_ERROR", "Account management capability fields must be a complete boolean pair.")
        if account["kind"] == "account_management" and management_fields != {"can_management_open", "can_logout"}:
            raise CliError("PROTOCOL_ERROR", "Account management requires its exact capability fields.")
        if argument in ("management_open", "logout") and management_fields != {"can_management_open", "can_logout"}:
            raise CliError("PROTOCOL_ERROR", "Account management actions require the native capability fields.")
        error_fields = {"error_code", "error_text"} & set(account)
        if error_fields:
            code, text = account.get("error_code"), account.get("error_text")
            if (error_fields != {"error_code", "error_text"} or code is None and text is not None
                    or code is not None and (not isinstance(code, str) or code not in ACCOUNT_ERRORS
                        or text != ACCOUNT_ERRORS[code] or account["kind"] != "login")):
                raise CliError("PROTOCOL_ERROR", "Account inline error does not match the fixed public allowlist.")
        if account["kind"] == "login_terms_required" and any(account[key] for key in ("can_open", "can_login_open", "can_fill", "can_submit")):
            raise CliError("PROTOCOL_ERROR", "Legal consent must not expose another account action.")
        if account["kind"] != "login_terms_required" and account["can_accept_terms"]:
            raise CliError("PROTOCOL_ERROR", "Agreement action is available outside the exact legal-consent dialog.")
        if account.get("can_management_open", False) and (account["kind"] != "logged_in_menu" or account["signed_in"] is not True or account["blocked"]):
            raise CliError("PROTOCOL_ERROR", "Account management requires the exact signed-in account menu.")
        if account.get("can_logout", False) and (account["kind"] != "account_management" or account["signed_in"] is not True or account["blocked"]):
            raise CliError("PROTOCOL_ERROR", "Logout action requires the exact native account-management dialog.")
        if account["kind"] == "account_management" and any(account[key] for key in ("can_open", "can_login_open", "can_fill", "can_submit", "can_accept_terms", "can_management_open")):
            raise CliError("PROTOCOL_ERROR", "Account-management dialog must not expose another account action.")
        if argument == "management_open" and (account["kind"] != "account_management" or not account.get("can_logout", False)):
            raise CliError("PROTOCOL_ERROR", "Native response did not confirm the account-management dialog.")
        if argument == "logout" and (account["signed_in"] is not False or account["kind"] != "main_menu" or account["blocked"]):
            raise CliError("PROTOCOL_ERROR", "Native response did not confirm a signed-out main menu.")
        if argument == "submit" and account.get("signed_in") is not True:
            raise CliError("PROTOCOL_ERROR", "Native response did not confirm a signed-in account.")
        if argument == "open" and account["kind"] not in ("logged_out_menu", "logged_in_menu"):
            raise CliError("PROTOCOL_ERROR", "Native response did not confirm the account menu.")
        if argument == "login_open" and account["kind"] not in ("login_terms_required", "login"):
            raise CliError("PROTOCOL_ERROR", "Native response did not confirm the legal-consent state or login form.")
        if argument == "fill" and account["kind"] != "login":
            raise CliError("PROTOCOL_ERROR", "Native response did not confirm the login form.")
        if argument == "terms_accept" and account["kind"] != "login":
            raise CliError("PROTOCOL_ERROR", "Native response did not confirm the login form after legal consent.")


def write_artifact(output, data):
    try:
        destination = Path(output).expanduser().resolve()
    except (OSError, ValueError, RuntimeError):
        raise CliError("OUTPUT_FAILED", "The output path is invalid or unavailable.") from None
    if destination.exists():
        raise CliError("OUTPUT_EXISTS", "Choose a new output path; existing files are not overwritten.")
    if not destination.parent.is_dir():
        raise CliError("OUTPUT_DIRECTORY", "The output directory does not exist.")
    created = False
    try:
        with destination.open("xb") as stream:
            created = True
            stream.write(data)
    except OSError:
        if created:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
        raise CliError("OUTPUT_FAILED", "Could not write the requested output file.") from None
    return str(destination)


class Client:
    def __init__(self, adb, timeout=10, clock=time.monotonic, sleep=time.sleep):
        self.adb, self.deadline, self.sleep = adb, Deadline(timeout, clock), sleep
        self.timeout, self.clock = timeout, clock
        self.identity = None
        self.dispatched = False
        self.credential_owned = False

    def inspect(self):
        metadata = self.adb.read("bridge.json", self.deadline)
        result = self.adb.call(["shell", "pidof", PACKAGE], self.deadline.remaining())
        try:
            live_pid = result.stdout.decode("ascii").strip()
        except UnicodeDecodeError:
            raise CliError("STALE_BRIDGE", "The live app PID is invalid.") from None
        metadata = validate_identity(metadata, live_pid)
        if self.identity and any(metadata[key] != self.identity[key] for key in ("pid", "session")):
            raise CliError("BRIDGE_RESTARTED", "The staging bridge restarted during the operation.")
        return metadata

    def publish_credentials(self, request_id, credentials):
        paths = tuple(f"{DIRECTORY}/{name}" for name in ("credential", "credential.tmp", "credential.inflight"))
        check = (f"test -d {DIRECTORY} && test ! -L {DIRECTORY} && " +
                 " && ".join(f"test ! -e {path} && test ! -L {path}" for path in paths))
        if self.adb.shell(check, self.deadline, allow_failure=True).returncode:
            raise CliError("CREDENTIAL_FILE_EXISTS", "Inspect the app-private credential files before another fill command.")
        username, password = credentials
        payload = bytearray(b"AKCRED1\n" + self.identity["session"].encode("ascii") + request_id.encode("ascii"))
        payload.extend(struct.pack("<HH", len(username), len(password)))
        payload.extend(username)
        payload.extend(password)
        self.credential_owned = True
        try:
            script = (f"umask 077; set -C; cat > {DIRECTORY}/credential.tmp && "
                      f"chmod 600 {DIRECTORY}/credential.tmp && mv -f {DIRECTORY}/credential.tmp {DIRECTORY}/credential")
            self.adb.shell(script, self.deadline, data=payload)
            self.inspect()
        finally:
            payload[:] = b"\0" * len(payload)

    def request(self, command, argument, credentials=None):
        if command not in self.identity["commands"]:
            raise CliError("UNSUPPORTED_COMMAND", "This staging bridge does not support the requested command.")
        result = self.adb.call(["shell", "date", "+%s%3N"], self.deadline.remaining())
        if not re.fullmatch(rb"[1-9][0-9]{12}\s*", result.stdout):
            raise CliError("DEVICE_TIME", "Could not read the Android wall clock.")
        expires = int(result.stdout) + int(self.deadline.remaining() * 1000)
        request_id = uuid.uuid4().hex
        wire = f"AKCLI1 {request_id} {self.identity['session']} {expires} {command} {argument}\n".encode("ascii")
        if credentials is not None:
            self.publish_credentials(request_id, credentials)
        script = (f"umask 077; test ! -L {DIRECTORY}/request.tmp && "
                  f"test ! -L {DIRECTORY}/request && cat > {DIRECTORY}/request.tmp && "
                  f"chmod 600 {DIRECTORY}/request.tmp && mv -f {DIRECTORY}/request.tmp {DIRECTORY}/request")
        self.dispatched = mutation(command, argument)
        self.adb.shell(script, self.deadline, data=wire)
        while True:
            self.inspect()
            response = self.adb.read("response.json", self.deadline, optional=True)
            if response and response.get("request_id") == request_id:
                if (type(response.get("protocol")) is not int or response.get("protocol") != 1 or
                        response.get("session") != self.identity["session"] or
                        response.get("environment") != "staging" or response.get("command") != command or
                        type(response.get("ok")) is not bool or not isinstance(response.get("state"), dict)):
                    raise CliError("PROTOCOL_ERROR", "Response identity or structure does not match the request.")
                if response["ok"] and response.get("error") is not None:
                    raise CliError("PROTOCOL_ERROR", "Successful response contains an error.")
                if not response["ok"]:
                    error = response.get("error")
                    if not isinstance(error, dict) or not isinstance(error.get("code"), str) or not isinstance(error.get("message"), str):
                        raise CliError("PROTOCOL_ERROR", "Failed response is missing its error.")
                    if self.dispatched and error["code"] in ("ACTION_TIMEOUT", "SCENE_CHANGED", "STATE_CHANGED_AFTER_DISPATCH", "EXPIRED_AFTER_DISPATCH"):
                        error.update(outcome_unknown=True, automatic_retry=False)
                if response["ok"] and command == "category":
                    category = response["state"].get("category")
                    name = "mod" if argument == "8" else "variety"
                    if not isinstance(category, dict) or category.get("section") != int(argument) or category.get("name") != name:
                        raise CliError("PROTOCOL_ERROR", "Successful category response did not confirm the selected category.")
                ui = validate_ui(response["state"]) if "ui" in response["state"] else None
                validate_advanced_guide(response["state"])
                if response["ok"] and command == "ui":
                    if ui is None:
                        raise CliError("PROTOCOL_ERROR", "UI response is missing native UI state.")
                    if argument != "list" and ui["context"] == argument.rsplit(".", 1)[1]:
                        raise CliError("PROTOCOL_ERROR", "UI activation did not confirm a changed action context.")
                if response["ok"] and command in DOMAIN_COMMANDS:
                    validate_domain_response(response["state"], command, argument)
                if "account" in response["state"]:
                    validate_domain_response(response["state"], "account", "status")
                if "sync" in response["state"]:
                    validate_domain_response(response["state"], "sync", "status")
                if "bundle" in response["state"]:
                    validate_domain_response(response["state"], "bundle", "status")
                if not response["ok"] and response["error"]["code"] == "ACCOUNT_LOGIN_FAILED":
                    account = response["state"].get("account", {})
                    if (command != "account" or argument != "submit" or account.get("can_submit") is not True or account.get("blocked") is not False
                            or account.get("signed_in") is True or account.get("error_code") not in ACCOUNT_ERRORS
                            or account.get("error_code") == "unrecognized"):
                        raise CliError("PROTOCOL_ERROR", "Login failure lacks its exact recognized native error.")
                    response["error"].update(outcome_unknown=False, automatic_retry=False)
                self.inspect()
                return response
            self.sleep(min(0.1, self.deadline.remaining()))

    def execute(self, command, argument="none", output=None, options=None, credentials=None, *, terms_consent=None):
        self.deadline = Deadline(self.timeout, self.clock)
        self.dispatched = self.credential_owned = False
        locked = False
        result = None
        try:
            ui_command = command == "ui" and (argument == "list" or UI_TOKEN.fullmatch(argument))
            catalogue_command = command in ("song-catalogue", "pack-catalogue") and argument == "none"
            domain_command = domain_argument(command, argument)
            guide_command = command == "guide" and argument in ("status", "next")
            if (((command, argument) not in (("status", "none"), ("category", "7"), ("category", "8"),
                                              ("screenshot", "none"), ("logs", "none")) and not ui_command and not catalogue_command and not domain_command and not guide_command) or
                    (command in ("screenshot", "logs") and output is None)):
                raise CliError("ARGUMENT_ERROR", "Unsupported command or argument.")
            if (command, argument) == ("account", "terms_accept"):
                if not any(terms_consent is ticket for ticket in _terms_tickets):
                    raise CliError("TERMS_INTERACTIVE_REQUIRED", "Run account terms-accept yourself and confirm AGREE in the terminal.")
                _terms_tickets.remove(terms_consent)
            elif terms_consent is not None:
                raise CliError("ARGUMENT_ERROR", "Legal consent is accepted only by account terms-accept.")
            if (command, argument) == ("account", "fill"):
                if (not isinstance(credentials, tuple) or len(credentials) != 2
                        or any(not isinstance(value, bytearray) for value in credentials)):
                    raise CliError("CREDENTIAL_INPUT", "Account fill requires credentials from the private input path.")
                try:
                    checked = credential_bytes({"username": credentials[0].decode("utf-8"), "password": credentials[1].decode("utf-8")})
                    for value in checked:
                        value[:] = b"\0" * len(value)
                except UnicodeError:
                    raise CliError("CREDENTIAL_INPUT", "Credentials must contain valid UTF-8 text.") from None
            elif credentials is not None:
                raise CliError("CREDENTIAL_INPUT", "Credentials are accepted only by account fill.")
            self.identity = self.inspect()
            lock = self.adb.shell(f"mkdir -m 700 {DIRECTORY}/lock", self.deadline, allow_failure=True)
            if lock.returncode:
                raise CliError("LOCKED", "Another client owns the bridge lock; stale locks require manual inspection.")
            locked = True
            self.inspect()
            if command == "ui" and argument != "list":
                current = self.request("ui", "list")
                if not current["ok"]:
                    result = current
                    return result
                ui = validate_ui(current["state"])
                if argument.rsplit(".", 1)[1] != ui["context"]:
                    raise CliError("STALE_UI_CONTEXT", "Run ui list again; the action context changed.")
                if not any(action["token"] == argument and action["enabled"] for action in ui["actions"]):
                    raise CliError("UI_ACTION_UNAVAILABLE", "The requested action is not currently available.")
            if guide_command:
                current = self.request("ui", "list")
                if not current["ok"]:
                    result = current
                    return result
                guide = guide_status(current["state"])
                guide.update(operation=argument, performed=None)
                current["guide"] = guide
                if argument == "status" or guide["action"] is None:
                    result = current
                    return result
                fresh = self.request("ui", "list")
                if not fresh["ok"]:
                    result = fresh
                    return result
                confirmed = guide_status(fresh["state"])
                if fresh["state"]["ui"]["context"] != current["state"]["ui"]["context"]:
                    raise CliError("STALE_UI_CONTEXT", "The guide changed before dispatch; inspect guide status.")
                if confirmed != {key: guide[key] for key in confirmed}:
                    raise CliError("GUIDE_STATE_CHANGED", "Guide eligibility changed before dispatch; inspect guide status.")
                action = guide["action"]
                result = self.request(action["command"], action["argument"])
                after = guide_status(result["state"])
                after.update(operation=argument, attempted=action, performed=action if result["ok"] else None)
                after["may_continue_play"] = guide["may_continue_play"]
                after["effect"] = guide["effect"]
                result["guide"] = after
            elif catalogue_command:
                try:
                    installed = catalogue.load(self.adb, self.deadline)
                    self.inspect()
                    result = catalogue.query(installed, "songs" if command == "song-catalogue" else "packs", options)
                except (ValueError, UnicodeError) as error:
                    raise CliError("CATALOGUE_ERROR", str(error)) from None
            elif command in ("status", "category", "ui") or domain_command:
                result = self.request(command, argument, credentials)
            elif command == "screenshot":
                data = self.adb.call(["exec-out", "screencap", "-p"], self.deadline.remaining()).stdout
                self.inspect()
                if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise CliError("SCREENSHOT_FAILED", "Android did not return a PNG screenshot.")
                result = {"ok": True, "command": command, "output": write_artifact(output, data)}
            elif command == "logs":
                data = self.adb.call(["logcat", "-d", "--pid=" + str(self.identity["pid"]),
                                      "-v", "threadtime", "-t", "2000", *LOG_TAGS], self.deadline.remaining()).stdout
                self.inspect()
                result = {"ok": True, "command": command, "output": write_artifact(output, redact_logs(data))}
            else:
                raise CliError("ARGUMENT_ERROR", "Unknown operation.")
        except CliError as error:
            if self.dispatched:
                error.details["outcome_unknown"] = True
                error.details["automatic_retry"] = False
            result = error.result()
        finally:
            if locked:
                try:
                    cleanup_script = f"rmdir {DIRECTORY}/lock"
                    if self.credential_owned:
                        cleanup_script = f"rm -f {DIRECTORY}/credential {DIRECTORY}/credential.tmp {DIRECTORY}/credential.inflight && " + cleanup_script
                    cleanup = self.adb.call(["shell", "-T", "run-as", PACKAGE, "sh", "-c",
                                             shlex.quote(cleanup_script)], 3, allow_failure=True)
                    if cleanup.returncode:
                        raise CliError("LOCK_RELEASE_FAILED", "Could not release the bridge lock; inspect it manually.")
                except CliError:
                    if result is not None:
                        result["warning"] = ("Credential and bridge lock cleanup failed; inspect the app-private directory before another command."
                                             if self.credential_owned else "Bridge lock cleanup failed; inspect it manually before another command.")
            if isinstance(credentials, (tuple, list)):
                for value in credentials:
                    if isinstance(value, bytearray):
                        value[:] = b"\0" * len(value)
        return result


def make_parser():
    parser = Parser(description=__doc__)
    parser.add_argument("--serial", required=True, help="Explicit staging device serial; no default or device fallback.")
    parser.add_argument("--adb", default="adb", help="ADB executable path (default: adb from PATH).")
    parser.add_argument("--timeout", type=float, default=10, help="Operation timeout, 1-30 seconds (default: 10); lock cleanup may add up to 3 seconds.")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=Parser)
    commands.add_parser("status", help="Read fresh game state without triggering actions.")
    guide = commands.add_parser("guide", help="Inspect or advance one recognized native guide step; no consent/download/Play loop.")
    guide.add_argument("action", choices=("status", "next"))
    bundle = commands.add_parser("bundle", help="Inspect the native content updater or confirm its exact download prompt.")
    bundle.add_argument("action", choices=("status", "confirm", "dismiss-error"))
    category = commands.add_parser("category", help="Select a visible pack category.")
    actions = category.add_subparsers(dest="action", required=True, parser_class=Parser)
    select = actions.add_parser("select")
    select.add_argument("category", choices=("variety", "mod"))
    ui = commands.add_parser("ui", help="List or activate a validated native action; no coordinate input.")
    ui_actions = ui.add_subparsers(dest="action", required=True, parser_class=Parser)
    ui_actions.add_parser("list", help="Read current semantic UI actions and context tokens.")
    activate = ui_actions.add_parser("activate", help="Activate exactly one token returned by ui list.")
    activate.add_argument("token")
    songs = commands.add_parser("song", help="Query the installed catalogue or control the native song selection.")
    song_actions = songs.add_subparsers(dest="action", required=True, parser_class=Parser)
    for name in ("list", "search", "info"):
        action = song_actions.add_parser(name)
        if name == "search":
            action.add_argument("query")
        if name == "info":
            action.add_argument("id")
        else:
            action.add_argument("--pack")
            action.add_argument("--difficulty", choices=tuple(catalogue.CLASSES))
            action.add_argument("--level")
            action.add_argument("--side", type=int, choices=(0, 1, 2))
            action.add_argument("--sort", choices=("id", "title"), default="id")
            action.add_argument("--limit", type=int, default=30)
            action.add_argument("--offset", type=int, default=0)
    song_select = song_actions.add_parser("select", help="Highlight an ID in the current native pack/filter list; never Play.")
    song_select.add_argument("id")
    play = song_actions.add_parser("play", help="Start the selected song through its native Play callback; no automatic note input.")
    play.add_argument("id", help="Expected selected song ID; a different selection is rejected.")
    confirm_download = song_actions.add_parser("confirm-download", help="Accept only the current native song-download prompt; wait for ordinary song selection to return.")
    confirm_download.add_argument("id", help="Expected selected song ID; unknown dialogs are rejected.")
    skip_guide = song_actions.add_parser("skip-advanced-guide", help="Skip only the current ordinary advanced gameplay tutorial prompt.")
    skip_guide.add_argument("id", help="Expected selected song ID; unknown dialogs are rejected.")
    confirm_speed = song_actions.add_parser("confirm-speed", help="Confirm the current native first-play Note Speed setup at its existing value.")
    confirm_speed.add_argument("id", help="Expected selected song ID; other overlays are rejected.")
    difficulty = song_actions.add_parser("difficulty", help="Select a native difficulty button.")
    difficulty.add_argument("difficulty", choices=tuple(catalogue.CLASSES))
    native_sort = song_actions.add_parser("sort", help="Change the game's native sort; catalogue --sort is independent.")
    native_sort.add_argument("native_sort", choices=NATIVE_SORTS)
    native_group = song_actions.add_parser("group", help="Change the game's native song grouping.")
    native_group.add_argument("native_group", choices=NATIVE_GROUPS)
    reverse = song_actions.add_parser("reverse", help="Set the native reverse-order preference.")
    reverse.add_argument("reverse", choices=("off", "on"))
    packs = commands.add_parser("pack", help="List packs in the installed catalogue; ownership is not inferred.")
    pack_actions = packs.add_subparsers(dest="action", required=True, parser_class=Parser)
    pack_list = pack_actions.add_parser("list")
    pack_list.add_argument("--query", default="")
    pack_list.add_argument("--limit", type=int, default=30)
    pack_list.add_argument("--offset", type=int, default=0)
    pack_select = pack_actions.add_parser("select", help="Select a pack ID or all from the open native pack selector.")
    pack_select.add_argument("id")
    pack_actions.add_parser("close", help="Close the native pack selector.")
    native_filter = commands.add_parser("filter", help="Control the game's native text filter; catalogue search remains independent.")
    filter_actions = native_filter.add_subparsers(dest="action", required=True, parser_class=Parser)
    for name in ("status", "open", "close", "reset"):
        filter_actions.add_parser(name)
    filter_query = filter_actions.add_parser("query")
    filter_query.add_argument("query", help="Public native query, 1-128 UTF-8 bytes.")
    skill = commands.add_parser("skill", help="Inspect native partner ability, seal and active gameplay gauge.")
    skill_actions = skill.add_subparsers(dest="action", required=True, parser_class=Parser)
    skill_actions.add_parser("status")
    seal = skill_actions.add_parser("seal", help="Use the ordinary skill seal button in the open partner dialog.")
    seal.add_argument("value", choices=("off", "on"))
    navigation = commands.add_parser("navigation", help="Use scene-specific native navigation callbacks.")
    navigation.add_argument("action", choices=("status", "back", "continue", "retry"))
    gameplay = commands.add_parser("gameplay", help="Control native pause/resume/retry/quit; no automatic notes or scores.")
    gameplay.add_argument("action", choices=("status", "pause", "resume", "retry", "quit"))
    character = commands.add_parser("character", help="Read owned characters and control the native selection dialog.")
    character_actions = character.add_subparsers(dest="action", required=True, parser_class=Parser)
    for name in ("status", "list", "open", "close"):
        character_actions.add_parser(name)
    character_select = character_actions.add_parser("select")
    character_select.add_argument("id", help="Owned native character ID.")
    account = commands.add_parser("account", help="Control the native account/login forms without printing credentials.")
    account_actions = account.add_subparsers(dest="action", required=True, parser_class=Parser)
    for name in ("status", "open", "login-open", "submit", "management-open", "logout"):
        account_actions.add_parser(name)
    account_actions.add_parser("terms-accept", help="User-operated only: read native terms links and type AGREE in an interactive terminal.")
    fill = account_actions.add_parser("fill", help="Fill the native login form using hidden prompts or private stdin JSON.")
    fill.add_argument("--credentials-stdin", action="store_true", help="Read <=512-byte JSON with username/password from stdin; never use argv for secrets.")
    settings = commands.add_parser("settings", help="Control the native settings panel and allowlisted preferences.")
    setting_actions = settings.add_subparsers(dest="setting", required=True, parser_class=Parser)
    for name in ("status", "open", "close"):
        setting_actions.add_parser(name)
    setting_actions.add_parser("anomaly-replay").add_argument("value", choices=("off", "on"))
    setting_actions.add_parser("note-speed").add_argument("value", type=note_speed_argument, help="1.0-6.5 in steps of 0.1; panel must be open.")
    setting_actions.add_parser("offset").add_argument("value", type=offset_argument, help="-2000..2000 milliseconds for the active audio preset; panel must be open.")
    setting_actions.add_parser("fps").add_argument("value", choices=("0", "1"), help="Native >60 FPS setting; panel must be open and the control available.")
    sync = commands.add_parser("sync", help="Read native Cloud Sync state or download server data; no upload action.")
    sync_actions = sync.add_subparsers(dest="action", required=True, parser_class=Parser)
    sync_actions.add_parser("status", help="Read Cloud Sync state without changing data.")
    sync_actions.add_parser("download", help="Use the native Download flow and confirm completion; never retry automatically.")
    for name in ("screenshot", "logs"):
        command = commands.add_parser(name)
        command.add_argument("--output", required=True, help="New local output file; never overwrite existing evidence.")
    return parser


def main(argv=None):
    credentials = None
    terms_consent = None
    try:
        args = make_parser().parse_args(argv)
        argument = {"variety": "7", "mod": "8"}.get(getattr(args, "category", None), "none")
        if args.command == "ui":
            argument = "list" if args.action == "list" else args.token
        command = args.command
        if args.command == "song":
            if args.action in ("list", "search", "info"):
                command = "song-catalogue"
            else:
                command = {"select": "song_select", "play": "play", "confirm-download": "play_download", "skip-advanced-guide": "play_guide", "confirm-speed": "play_set_speed", "difficulty": "difficulty", "sort": "sort", "group": "group", "reverse": "reverse"}[args.action]
                argument = {"select": lambda: args.id, "play": lambda: args.id, "confirm-download": lambda: args.id, "skip-advanced-guide": lambda: args.id, "confirm-speed": lambda: args.id, "difficulty": lambda: str(catalogue.CLASSES[args.difficulty]),
                            "sort": lambda: str(NATIVE_SORTS.index(args.native_sort)),
                            "group": lambda: str(NATIVE_GROUPS.index(args.native_group)),
                            "reverse": lambda: "1" if args.reverse == "on" else "0"}[args.action]()
        elif args.command == "pack":
            command = {"list": "pack-catalogue", "select": "pack_select", "close": "pack_close"}[args.action]
            argument = args.id if args.action == "select" else "none"
        elif args.command == "filter":
            argument = encode_query(args.query) if args.action == "query" else args.action
        elif args.command == "guide":
            argument = args.action
        elif args.command in ("skill", "navigation", "gameplay", "bundle"):
            argument = "seal:" + ("1" if args.value == "on" else "0") if args.command == "skill" and args.action == "seal" else args.action
        elif args.command == "character":
            argument = args.id if args.action == "select" else args.action
        elif args.command == "account":
            argument = args.action.replace("-", "_")
            if args.action == "fill":
                credentials = read_credentials(args.credentials_stdin)
            elif args.action == "terms-accept":
                terms_consent = confirm_terms()
        elif args.command == "settings":
            if args.setting == "anomaly-replay":
                command, argument = "replay", "1" if args.value == "on" else "0"
            elif args.setting in ("note-speed", "offset"):
                argument = ("speed:" if args.setting == "note-speed" else "offset:") + args.value
            elif args.setting == "fps":
                argument = "fps:" + args.value
            else:
                argument = args.setting
        elif args.command == "sync":
            argument = args.action
        options = {key: getattr(args, key) for key in ("query", "id", "pack", "difficulty", "level", "side", "sort", "limit", "offset")
                   if hasattr(args, key) and getattr(args, key) is not None}
        client = Client(Adb(args.adb, args.serial), args.timeout)
        execute_options = {"terms_consent": terms_consent} if terms_consent is not None else {}
        result = client.execute(command, argument, getattr(args, "output", None), options, credentials, **execute_options)
    except CliError as error:
        result = error.result()
    except KeyboardInterrupt:
        result = CliError("INTERRUPTED", "Interrupted; a dispatched action may have completed. Do not retry automatically.").result()
    finally:
        if terms_consent is not None:
            _terms_tickets.discard(terms_consent)
        if credentials is not None:
            for value in credentials:
                value[:] = b"\0" * len(value)
    print(json.dumps(result, separators=(",", ":")))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
