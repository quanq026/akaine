# Semantic CLI: first-run playing flow

The V36 client exposes native UI actions with short-lived context tokens. List the current state before activating a token. A token is valid only for the exact current scene, owned UI object, and registered callback.

```powershell
& $python scripts/akaine_cli/akaine.py --serial $serial ui list
& $python scripts/akaine_cli/akaine.py --serial $serial ui activate <token-from-ui-list>
```

## First-run setup and guides

| Native state | CLI action | Confirmation |
|---|---|---|
| Welcome | Offered `onboarding_setup` token | Exact Offset Setup dialog appears |
| Offset Setup | Offered `onboarding_cancel` token | Native incomplete-setup warning appears |
| Incomplete-setup warning | Offered `onboarding_skip` token | Calibration dialogs close; Settings remains open |
| Settings | `settings close` | Settings closes through native Done callback |
| Main Menu Music guide | Offered `main_hint_continue` token | One ordinary native guide step completes |
| Notification guide | Offered `notification_hint_continue` token | Guide closes and Android notification permission is requested |

Refresh `ui list` after every guide step. The notification action requests Android permission; the Android prompt remains a separate OS choice. Unknown guides remain blocked.

The ordinary Offset Setup cancellation path requires incomplete calibration and no captured samples. It preserves the existing timing value. Native first-show markers may be set when a dialog or guide is constructed, so restarting the process can consume a first-run fixture before a callback is tested.

## Inspect or advance one guide step

```powershell
& $python scripts/akaine_cli/akaine.py --serial $serial guide status
& $python scripts/akaine_cli/akaine.py --serial $serial guide next
```

These host conveniences require explicit native guide metadata. Older native
responses still support the existing commands, but `guide` rejects missing
metadata. `guide status` reports `action`, `wait`, `blocked`, or `none` and the
single eligible native action. `guide next` refreshes its context and performs
at most one known callback. It returns the remaining guide state and the
`performed` action; a successful step is not a promise that every guide ended.

`ui.overlays` now exposes native step/pending counts, readiness, validated
ownership and listener flags. Invisible swallowing listeners remain blockers.
Welcome, offset cancellation, Settings close and the known Main Menu,
notification and Pack Select steps reuse their existing typed callbacks.

An exact Advanced Tutorial prompt is exposed as `advanced_guide`, including
selected chart, Skip eligibility and priority. Skip and Note Speed Set can run
the continuation of an already requested Play; `may_continue_play` reports this.
`guide next` does not issue a new Play, accept a song download, legal terms or an
Android permission prompt. A notification-guide step explicitly reports
`effect="requests_android_notification_permission"`; it requests the OS prompt
but never grants or revokes Android permission. The OS choice is a separate
explicit step. This command never loops through several steps automatically.

A Pack Select hint coexisting with Advanced Tutorial currently reports
`pack_hint_priority_unproven`. It remains blocked until native listener/layer
priority is established. Unknown or competing guides and modals remain blocked;
this API does not dismiss them or write tutorial preferences.

## First Play and Note Speed

Select the intended song and difficulty, then use its native Play callback:

```powershell
& $python scripts/akaine_cli/akaine.py --serial $serial song select <song-id>
& $python scripts/akaine_cli/akaine.py --serial $serial song difficulty ftr
& $python scripts/akaine_cli/akaine.py --serial $serial song play <song-id>
```

When the first-play Note Speed popup is open, `ui.overlays` includes `note_speed_setup`; underlying scene actions are blocked. `NOTE_SPEED_SETUP_REQUIRED` means the native Play path reached that popup. Inspect the selected chart and popup before confirming:

```powershell
& $python scripts/akaine_cli/akaine.py --serial $serial ui list
& $python scripts/akaine_cli/akaine.py --serial $serial song confirm-speed <song-id>
```

`song confirm-speed` maps to the exact native `play_set_speed` command. It supplies no replacement speed. The registered Set callback preserves the displayed value, marks the ordinary first-play setup complete, and runs the existing continuation for that selected song and difficulty. This continuation can enter gameplay or a native download/tutorial prompt. Inspect the returned state before the next action.

For a recognized native song download prompt, use `song confirm-download <song-id>`. Use `song skip-advanced-guide <song-id>` only when the ordinary supported gameplay tutorial prompt is present. Gameplay controls do not generate notes or scores.

## Unconfirmed outcomes

An action timeout is an unknown outcome. Inspect a fresh CLI state and clean full-screen evidence; do not automatically repeat Play or Set. Multiple Note Speed popups are ambiguous and remain blocked. A stale token or changed scene requires a fresh list and an explicitly selected current action.

## Native login failures

`account status` reports only the fixed public `error_code` and canonical `error_text` allowlist. Unknown visible labels return `unrecognized` without their contents. Credential fields are never read.

`ACCOUNT_LOGIN_FAILED` requires the same native login form to disable its submit button after dispatch, then re-enable it with a recognized error. An old banner alone cannot confirm a new failure. The response sets `outcome_unknown=false` and `automatic_retry=false`. If completion occurs before the busy observation, the command conservatively retains its timeout.
