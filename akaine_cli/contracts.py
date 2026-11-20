"""Immutable targets, wire constants and pure command argument validation."""
from dataclasses import dataclass
import base64
from . import catalogue
import re


DIRECTORY = "files/akaine-cli-v1"


HEX_ID = re.compile(r"[0-9a-f]{32}\Z")


UI_CONTEXT = re.compile(r"[0-9a-f]{16}\Z")


UI_TOKEN = re.compile(r"(start_continue|main_music|pack_open|pack_hint_continue|song_hint_continue|partner_hint_continue|main_hint_continue|notification_hint_continue|onboarding_setup|onboarding_cancel|onboarding_skip)\.([0-9a-f]{16})\Z")


UI_LABELS = {"start_continue": "Continue", "main_music": "Music", "pack_open": "Pack Select",
             "song_hint_continue": "Continue song selection guide",
             "pack_hint_continue": "Continue pack selection guide", "partner_hint_continue": "Continue partner selection guide", "main_hint_continue": "Continue main menu guide", "notification_hint_continue": "Continue notification guide (requests Android permission)", "onboarding_setup": "Setup",
             "onboarding_cancel": "Cancel offset setup", "onboarding_skip": "Confirm skip offset setup"}


UI_REASONS = {None, "unsupported_modal", "loading", "unsupported_scene", "unavailable", "unsupported_ui_tree", "not_ready",
              "input_blocked", "tutorial_active", "overlay_scan_incomplete", "native_bundle_error"}


OVERLAY_LIMIT = 16


OVERLAY_IDS = {"tutorial": ("pack_selection_hint", "song_selection_hint", "partner_selection_hint", "main_menu_hint", "notification_permission_guide", "unknown_progression_guide", "note_speed_setup")}


OVERLAY_COVERAGE = ("progression_guide", "note_speed_setup")


GUIDE_FIELDS = {"step_index", "pending_steps", "advance_ready", "can_advance", "can_set_speed",
                "owner_validated", "callback_owned", "listener_registered", "listener_paused",
                "listener_enabled", "listener_swallow"}


GUIDE_ACTIONS = {"onboarding_setup", "onboarding_cancel", "onboarding_skip", "main_hint_continue",
                 "notification_hint_continue", "pack_hint_continue", "song_hint_continue", "partner_hint_continue"}


SERIAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


MAX_JSON = 16384


LOG_TAGS = ("AkaineAnomalyMonitor:I", "AkaineCLI:I", "AndroidRuntime:E", "libc:F", "DEBUG:F", "*:S")


NATIVE_SORTS = ("title", "difficulty", "date", "grade", "clear", "artist")


NATIVE_GROUPS = ("pack", "version", "level", "grade", "clear", "available")


DOMAIN_COMMANDS = {"song_select", "difficulty", "sort", "group", "reverse", "pack_select", "pack_close", "character", "account", "sync", "replay", "play", "play_download", "play_guide", "play_set_speed", "filter", "skill", "navigation", "gameplay", "settings", "bundle", "customize"}


ACCOUNT_ERRORS = {
    "connection_failed": "Could not connect to online server.",
    "invalid_credentials": "Username or password incorrect.",
    "account_locked": "This account is locked.",
    "maintenance": "The Arcaea network is currently under maintenance.",
    "unknown_error": "An unknown error has occurred.", "unrecognized": None}


CREDENTIAL_LIMIT = 512


TERMS_URL = "https://arcaea.lowiro.com/terms_of_service"


PRIVACY_URL = "https://arcaea.lowiro.com/privacy_policy"


class CliError(Exception):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details

    def result(self):
        return {"ok": False, "error": {"code": self.code, "message": self.message, **self.details}}


@dataclass(frozen=True)
class Target:
    package: str
    environment: str
    overlay_ids: tuple = tuple(OVERLAY_IDS.items())
    overlay_coverage: tuple = OVERLAY_COVERAGE

    def __post_init__(self):
        if (self.environment not in ("staging", "production")
                or self.package not in catalogue.PACKAGE_VERSIONS
                or self.environment == "production" and self.package != "akai.arc.lmao"
                or not isinstance(self.overlay_ids, tuple)
                or any(not isinstance(row, tuple) or len(row) != 2 or not isinstance(row[0], str)
                       or not isinstance(row[1], tuple) or any(not isinstance(value, str) for value in row[1])
                       for row in self.overlay_ids)
                or not isinstance(self.overlay_coverage, tuple)
                or any(not isinstance(value, str) for value in self.overlay_coverage)):
            raise ValueError("Unsupported immutable bridge target")

    @property
    def default_version(self):
        return catalogue.PACKAGE_VERSIONS[self.package]

    def modern_ui(self, application_version):
        return application_version == catalogue.QA73_VERSION

    def bundle_pattern(self, application_version):
        if self.environment == "production":
            return catalogue.bundle_version_pattern(self.package, application_version)
        return catalogue.bundle_version_pattern(self.package, self.default_version)


STAGING = Target(catalogue.QA73_PACKAGE, "staging")


PRODUCTION = Target("akai.arc.lmao", "production")


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
    if command == "customize":
        return (argument in ("status", "list", "open", "close", "tab:title", "tab:bgm", "tab:scenery", "confirm-download")
                or argument.startswith("select:") and bool(catalogue.ID.fullmatch(argument[7:])))
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
             ("filter", "status"), ("skill", "status"), ("navigation", "status"), ("gameplay", "status"), ("settings", "status"), ("bundle", "status"),
             ("customize", "status"), ("customize", "list")))


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
