"""Pure bridge identity, UI and domain response validation."""
from . import catalogue
import re
from .contracts import (
    ACCOUNT_ERRORS,
    CliError,
    GUIDE_ACTIONS,
    GUIDE_FIELDS,
    HEX_ID,
    OVERLAY_LIMIT,
    STAGING,
    UI_CONTEXT,
    UI_LABELS,
    UI_REASONS,
    UI_TOKEN,
    encode_query,
)


def validate_identity(metadata, live_pid, *, target=STAGING):
    if (metadata.get("protocol") != 1 or type(metadata.get("protocol")) is not int or
            metadata.get("environment") != target.environment or metadata.get("package") != target.package):
        raise CliError("NOT_" + target.environment.upper(), f"The app is not the expected {target.environment} bridge.")
    if (type(metadata.get("pid")) is not int or metadata["pid"] <= 0 or
            not isinstance(metadata.get("session"), str) or not HEX_ID.fullmatch(metadata["session"]) or
            not isinstance(metadata.get("commands"), list) or
            not all(isinstance(command, str) for command in metadata["commands"])):
        raise CliError("PROTOCOL_ERROR", "Bridge identity is malformed.")
    if live_pid != str(metadata["pid"]):
        raise CliError("STALE_BRIDGE", "Bridge metadata does not match the live app PID.")
    if target.package == catalogue.QA73_PACKAGE and metadata.get("application_version") != catalogue.QA73_VERSION:
        raise CliError("PROTOCOL_ERROR", "The QA bridge must declare application version 7.3.1.")
    if target.environment == "staging":
        return metadata
    # V36 predates this field; never infer a newer contract from its bundle files.
    version = metadata.get("application_version", catalogue.QA73_VERSION)
    if not isinstance(version, str):
        raise CliError("PROTOCOL_ERROR", "Bridge application version is malformed.")
    try:
        catalogue.bundle_version_pattern(target.package, version)
    except ValueError:
        raise CliError("PROTOCOL_ERROR", "Bridge application version is unsupported.") from None
    return {**metadata, "application_version": version}


def validate_overlays(ui, application_version=catalogue.QA73_VERSION, *, target=STAGING):
    if target.environment == "production":
        catalogue.bundle_version_pattern(target.package, application_version)
    overlays, coverage = ui.get("overlays"), ui.get("overlay_coverage")
    expected_coverage = target.overlay_coverage + (("category_tutorial", "partner_tutorial") if target.modern_ui(application_version) else ())
    if (type(ui.get("overlay_scan_complete")) is not bool or not isinstance(overlays, list)
            or len(overlays) > OVERLAY_LIMIT or not isinstance(coverage, list)
            or coverage != list(expected_coverage)):
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
        if (not isinstance(kind, str) or kind not in dict(target.overlay_ids) or not isinstance(identifier, str)
                or identifier not in dict(target.overlay_ids)[kind] or (kind, identifier) in seen
                or identifier == "partner_selection_hint" and not target.modern_ui(application_version)):
            raise CliError("PROTOCOL_ERROR", "UI overlay identity is unknown or duplicated.")
        seen.add((kind, identifier))
        if (any(overlay[key] is not None and type(overlay[key]) is not bool for key in ("active", "visible", "blocks_input"))
                or overlay["opacity"] is not None and (type(overlay["opacity"]) is not int or not 0 <= overlay["opacity"] <= 255)):
            raise CliError("PROTOCOL_ERROR", "UI overlay flags or opacity are invalid.")
    return overlays


def validate_ui(state, application_version=catalogue.QA73_VERSION, *, target=STAGING):
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
    overlays = validate_overlays(ui, application_version, target=target)
    partner_hint = (target.modern_ui(application_version) and state.get("screen") == "song_select"
        and ui["modal_present"] and ui["overlay_scan_complete"] and len(overlays) == 1
        and overlays[0]["kind"] == "tutorial" and overlays[0]["id"] == "partner_selection_hint"
        and all(overlays[0].get(key) is True for key in ("active", "blocks_input", "can_advance",
            "advance_ready", "owner_validated", "callback_owned"))
        and isinstance(state.get("character"), dict) and state["character"].get("dialog_open") is True)
    partner_action = (partner_hint and onboarding is None and reason == "input_blocked" and len(ui["actions"]) == 1
        and isinstance(ui["actions"][0], dict)
        and ui["actions"][0].get("token") == "partner_hint_continue." + ui["context"])
    if ui["modal_present"] and ui["actions"] and not partner_action:
        expected = onboarding_actions.get(onboarding)
        if (not expected or state.get("screen") != "main_menu" or reason is not None
                or len(ui["actions"]) != 1 or not isinstance(ui["actions"][0], dict)
                or ui["actions"][0].get("token") != expected + "." + ui["context"]):
            raise CliError("PROTOCOL_ERROR", "Unsupported modal must block underlying scene actions.")
    blocking = any(overlay["blocks_input"] is True for overlay in overlays)
    known_hint = any(overlay["kind"] == "tutorial" and overlay["id"] == "pack_selection_hint"
                     and overlay["active"] is True for overlay in overlays)
    unknown_blocker = any(overlay["blocks_input"] is True and
                          (overlay["kind"], overlay["id"]) != ("tutorial", "pack_selection_hint") for overlay in overlays)
    if blocking and any(not isinstance(action, dict) or not isinstance(action.get("token"), str)
                        or not action["token"].startswith(("pack_hint_continue.", "song_hint_continue.", "partner_hint_continue.", "main_hint_continue.", "notification_hint_continue.")) for action in ui["actions"]):
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
            raise CliError("PROTOCOL_ERROR", f"UI action does not match the fixed {target.environment} action contract.")
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
        if token[1] == "song_hint_continue" and (
                state.get("screen") != "song_select" or not ui["overlay_scan_complete"] or len(overlays) != 1
                or overlays[0]["id"] != "song_selection_hint" or not overlays[0]["can_advance"]):
            raise CliError("PROTOCOL_ERROR", "Guide continuation requires the exact active native song hint.")
        if token[1] == "partner_hint_continue" and not partner_action:
            raise CliError("PROTOCOL_ERROR", "Partner continuation requires its exact owned modal and active native guide.")
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


def guide_status(state, application_version=catalogue.QA73_VERSION, *, target=STAGING):
    """Choose at most one known guide callback; no consent, download or Play action."""
    ui = validate_ui(state, application_version, target=target)
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


def validate_domain_response(state, command, argument, application_version=catalogue.QA73_VERSION, *, target=STAGING):
    if command == "bundle":
        value = state.get("bundle")
        version_pattern = target.bundle_pattern(application_version)
        if (not isinstance(value, dict) or set(value) != {"available", "phase", "can_confirm", "pending_versions", "pending_bytes", "reason"}
                or any(type(value.get(key)) is not bool for key in ("available", "can_confirm"))
                or value.get("phase") not in ("unavailable", "ready", "confirmation", "downloading", "failed")
                or not isinstance(value.get("pending_versions"), list) or len(value["pending_versions"]) > 16
                or any(not isinstance(version, str) or not re.fullmatch(version_pattern, version) for version in value["pending_versions"])
                or value.get("pending_bytes") is not None and (type(value["pending_bytes"]) is not int or not 0 <= value["pending_bytes"] <= 2**63 - 1)
                or value.get("reason") is not None and not isinstance(value["reason"], str)):
            raise CliError("PROTOCOL_ERROR", "Native bundle state does not match its bounded public contract.")
        if value["can_confirm"] and (not value["available"] or value["phase"] != "confirmation" or value["reason"] is not None):
            raise CliError("PROTOCOL_ERROR", "Bundle confirmation is available outside its exact native prompt.")
        if argument == "confirm" and (not value["available"] or value["phase"] not in ("downloading", "ready") or value["can_confirm"] or value["reason"] is not None):
            raise CliError("PROTOCOL_ERROR", "Native bundle confirmation did not observe download progress or readiness.")
        if argument == "dismiss-error" and (not value["available"] or value["phase"] == "failed"):
            raise CliError("PROTOCOL_ERROR", "Native bundle error dismissal was not observed.")
    elif command == "customize":
        value = state.get("customize")
        required = {"available", "open", "tab", "items", "download_required"}
        if (not isinstance(value, dict) or set(value) not in (required, required | {"phase", "download_song"})
                or any(type(value[k]) is not bool for k in ("available", "open", "download_required"))
                or value["tab"] not in (None, "title", "bgm", "scenery")
                or not isinstance(value["items"], list) or len(value["items"]) > 48):
            raise CliError("PROTOCOL_ERROR", "Customize state is malformed.")
        phase = value.get("phase")
        if phase is not None and (
                phase not in ("closed", "ready", "blocked", "confirmation", "downloading")
                or value["open"] != (phase != "closed")
                or value["download_required"] != (phase == "confirmation")
                or value.get("download_song") != ("hascome" if phase == "confirmation" else None)):
            raise CliError("PROTOCOL_ERROR", "Customize phase is inconsistent with its native overlay.")
        seen = set()
        selected = None
        for row in value["items"]:
            if (not isinstance(row, dict) or set(row) != {"id", "unlocked", "selected"}
                    or not isinstance(row["id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", row["id"])
                    or type(row["unlocked"]) is not bool or type(row["selected"]) is not bool
                    or row["id"] in seen or row["selected"] and selected is not None):
                raise CliError("PROTOCOL_ERROR", "Customize items are malformed.")
            seen.add(row["id"])
            if row["selected"]:
                selected = row["id"]
        if argument in ("status", "list"):
            return
        if argument == "confirm-download" and phase == "downloading":
            return
        if (not value["available"] or (argument == "close") == value["open"]
                or argument.startswith("tab:") and value["tab"] != argument[4:]
                or argument.startswith("select:") and selected != argument[7:]
                or argument == "confirm-download" and value["download_required"]):
            raise CliError("PROTOCOL_ERROR", "Customize did not confirm the requested action.")
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
        if argument in ("quit", "continue") and state.get("screen") != "song_select" and not (
                argument == "quit" and target.package == catalogue.QA73_PACKAGE and state.get("screen") == "main_menu"):
            raise CliError("PROTOCOL_ERROR", "Native navigation did not confirm song selection.")
        if argument == "back" and state.get("screen") not in ("song_select", "main_menu"):
            raise CliError("PROTOCOL_ERROR", "Native Back did not confirm the expected menu.")
    elif command == "replay":
        if type(state.get("anomaly_replay")) is not bool or state["anomaly_replay"] != (argument == "1"):
            raise CliError("PROTOCOL_ERROR", "Native response did not confirm Anomaly Replay.")
    elif command == "play_set_speed":
        ui = validate_ui(state, application_version, target=target)
        if ui["overlay_scan_complete"] is not True or any(overlay["id"] == "note_speed_setup" for overlay in ui["overlays"]):
            raise CliError("PROTOCOL_ERROR", "Native note-speed setup is still present or its scan is incomplete.")
        if state.get("gameplay") is True:
            validate_domain_response(state, "play", argument, application_version, target=target)
        else:
            song = state.get("song_selection")
            if (state.get("screen") != "song_select" or not isinstance(song, dict) or song.get("song_id") != argument
                    or type(song.get("difficulty")) is not int or not 0 <= song["difficulty"] <= 4):
                raise CliError("PROTOCOL_ERROR", "Native note-speed setup did not confirm the expected song.")
    elif command == "play_guide" and state.get("gameplay") is True:
        validate_domain_response(state, "play", argument, application_version, target=target)
    elif command == "play_download" and target.package == catalogue.QA73_PACKAGE:
        song, ui = state.get("song_selection"), state.get("ui")
        download = state.get("chart_download")
        if (state.get("screen") != "song_select" or state.get("gameplay") is not False
                or not isinstance(song,dict) or song.get("song_id") != argument
                or type(song.get("selected_difficulty")) is not int or not 0 <= song["selected_difficulty"] <= 4
                or type(song.get("difficulty")) is not int or song["difficulty"] != song["selected_difficulty"]
                or not isinstance(ui,dict) or ui.get("modal_present") is not False
                or not isinstance(download,dict)
                or set(download) != {"song_id","difficulty","can_confirm","prompt_dismissed"}
                or download["song_id"] != argument or type(download["difficulty"]) is not int
                or download["difficulty"] != song["selected_difficulty"]
                or download["can_confirm"] is not False or download["prompt_dismissed"] is not True):
            raise CliError("PROTOCOL_ERROR", "Native chart download prompt dismissal was not confirmed.")
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
