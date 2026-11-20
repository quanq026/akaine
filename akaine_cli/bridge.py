"""Semantic CLI argument parsing and command dispatch; standard library only."""
import argparse
from dataclasses import replace
import json
import sys
from . import catalogue
from .contracts import (
    CliError,
    NATIVE_GROUPS,
    NATIVE_SORTS,
    STAGING,
    encode_query,
    note_speed_argument,
    offset_argument,
)
from .transport import (
    Adb,
    Client,
    confirm_terms,
    read_credentials,
)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse messages can echo unexpected argv, including pasted secrets.
        raise CliError("ARGUMENT_ERROR", "Invalid command or arguments; run --help for supported options.")


def make_parser(*, target=STAGING):
    parser = Parser(description=f"Local, {target.environment}-only Akaine bridge client. Python standard library only.")
    parser.add_argument("--serial", required=True, help=f"Explicit {target.environment} device serial; no default or device fallback.")
    if target.environment == "staging":
        parser.add_argument("--package", choices=tuple(catalogue.PACKAGE_VERSIONS), default=target.package,
                            help="Exact staging app identity.")
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
    customize = commands.add_parser("customize", help="Inspect and select native title, BGM and scenery items in staging 7.3.1.")
    customize_actions = customize.add_subparsers(dest="action", required=True, parser_class=Parser)
    for name in ("status", "open", "close", "confirm-download"):
        customize_actions.add_parser(name)
    customize_actions.add_parser("list").add_argument("--all", action="store_true", help="Inspect all tabs and restore the initial tab.")
    customize_actions.add_parser("tab").add_argument("tab", choices=("title", "bgm", "scenery"))
    customize_actions.add_parser("select").add_argument("id", help="Exact item ID from customize list.")
    sync = commands.add_parser("sync", help="Read native Cloud Sync state or download server data; no upload action.")
    sync_actions = sync.add_subparsers(dest="action", required=True, parser_class=Parser)
    sync_actions.add_parser("status", help="Read Cloud Sync state without changing data.")
    sync_actions.add_parser("download", help="Use the native Download flow and confirm completion; never retry automatically.")
    for name in ("screenshot", "logs"):
        command = commands.add_parser(name)
        command.add_argument("--output", required=True, help="New local output file; never overwrite existing evidence.")
    return parser


def main(argv=None, *, target=STAGING, adb_factory=None, client_factory=None):
    adb_factory = Adb if adb_factory is None else adb_factory
    client_factory = Client if client_factory is None else client_factory
    credentials = None
    terms_consent = None
    try:
        args = make_parser(target=target).parse_args(argv)
        if target.environment == "staging":
            target = replace(target, package=args.package)
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
                terms_consent = confirm_terms(target)
        elif args.command == "settings":
            if args.setting == "anomaly-replay":
                command, argument = "replay", "1" if args.value == "on" else "0"
            elif args.setting in ("note-speed", "offset"):
                argument = ("speed:" if args.setting == "note-speed" else "offset:") + args.value
            elif args.setting == "fps":
                argument = "fps:" + args.value
            else:
                argument = args.setting
        elif args.command == "customize":
            if target.package != catalogue.QA73_PACKAGE:
                raise CliError("COMMAND_UNAVAILABLE", "Customize requires the 7.3.1 QA bridge.")
            if args.action == "tab":
                argument = "tab:" + args.tab
            elif args.action == "select":
                argument = "select:" + args.id
            elif args.action == "list" and args.all:
                argument = "list-all"
            else:
                argument = args.action
        elif args.command == "sync":
            argument = args.action
        options = {key: getattr(args, key) for key in ("query", "id", "pack", "difficulty", "level", "side", "sort", "limit", "offset")
                   if hasattr(args, key) and getattr(args, key) is not None}
        client = client_factory(adb_factory(args.adb, args.serial, target=target), args.timeout)
        execute_options = {"terms_consent": terms_consent} if terms_consent is not None else {}
        result = client.execute(command, argument, getattr(args, "output", None), options, credentials, **execute_options)
    except CliError as error:
        result = error.result()
    except KeyboardInterrupt:
        result = CliError("INTERRUPTED", "Interrupted; a dispatched action may have completed. Do not retry automatically.").result()
    finally:
        if terms_consent is not None:
            terms_consent.close()
        if credentials is not None:
            for value in credentials:
                value[:] = b"\0" * len(value)
    print(json.dumps(result, separators=(",", ":")))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
