// 7.1 replay gates retain native fallbacks until the owning monitor publishes callbacks.
.section .replay_gates,"ax",%progbits
.p2align 4
.macro MAILBOX_LOAD destination, scratch, offset
    adrp \scratch, toggle_mailbox
    ldr \destination, [\scratch, #:lo12:toggle_mailbox + \offset]
.endm
.macro READY_LOAD destination, scratch
    adrp \scratch, toggle_mailbox
    add \scratch, \scratch, :lo12:toggle_mailbox
    ldar \destination, [\scratch]
.endm
.macro GLOBAL name
    .global \name
\name:
.endm

GLOBAL official_factory_gate
    MAILBOX_LOAD x8, x8, 32
    cbz x8, .Lfactory_native
    br x8
.Lfactory_native:
    b native_modifier_factory

GLOBAL official_init_gate
    mov x1, x8
    MAILBOX_LOAD x8, x8, 40
    cbz x8, .Linit_native
    br x8
.Linit_native:
    br x1

GLOBAL official_update_gate
    mov x2, x8
    MAILBOX_LOAD x8, x8, 48
    cbz x8, .Lupdate_native
    br x8
.Lupdate_native:
    br x2

GLOBAL official_finish_gate
    mov x3, x8
    MAILBOX_LOAD x8, x8, 56
    cbz x8, .Lfinish_native
    br x8
.Lfinish_native:
    br x3

GLOBAL axium_scope_gate
    MAILBOX_LOAD x10, x9, 96
    sub x10, x10, x20
    cbnz x10, .Laxium_native
    ldr w10, [x9, #:lo12:toggle_mailbox + 88]
    sub w10, w10, #1
    cbnz w10, .Laxium_native
    // Native x23 is the GOT value (singleton slot), not the GOT slot's own address.
    adrp x23, native_online_global_got
    ldr x23, [x23, #:lo12:native_online_global_got]
    b native_axium_visuals
.Laxium_native:
    adrp x23, native_online_global_got
    b native_axium_continue

GLOBAL ether_scope_gate
    MAILBOX_LOAD x10, x9, 96
    sub x10, x10, x22
    cbnz x10, .Lether_native
    ldr w10, [x9, #:lo12:toggle_mailbox + 88]
    sub w10, w10, #2
    cbnz w10, .Lether_native
    mov w8, #1
    b native_ether_continue
.Lether_native:
    orr w8, w19, w20
    b native_ether_continue

.macro PROGRESS_GATE name, actor, operation, fallback
GLOBAL \name
    mov x4, \actor
    mov w5, #\operation
    MAILBOX_LOAD x8, x8, 64
    cbz x8, .Lprogress_native\@
    br x8
.Lprogress_native\@:
    b \fallback
.endm
PROGRESS_GATE last_accept_player_gate, x19, 0, native_last_player_write
PROGRESS_GATE last_accept_persist_gate, x19, 1, native_last_player_persist
PROGRESS_GATE last_accept_story_gate, x23, 2, native_last_story_write
PROGRESS_GATE last_accept_story_persist_gate, x23, 3, native_last_story_persist
PROGRESS_GATE last_reject_story_gate, x23, 4, native_last_story_write
PROGRESS_GATE last_reject_story_persist_gate, x23, 5, native_last_story_persist

GLOBAL last_reject_progress_gate
    MAILBOX_LOAD x10, x9, 72
    sub x10, x10, x23
    cbnz x10, .Llast_progress_native
    ldr x10, [x9, #:lo12:toggle_mailbox + 80]
    cbz x10, .Llast_progress_native
    b native_last_reject_resume
.Llast_progress_native:
    ldr x0, [x8, #0xd0]
    b native_last_reject_progress_continue

GLOBAL tempest_scope_gate
    MAILBOX_LOAD x10, x9, 96
    sub x10, x10, x20
    cbnz x10, .Ltempest_native
    ldr w10, [x9, #:lo12:toggle_mailbox + 88]
    sub w10, w10, #3
    cbnz w10, .Ltempest_native
    ldr w10, [x20, #0x2f0]
    cbnz w10, .Ltempest_native
    ldr w10, [x20, #0x2e8]
    cbz w10, .Ltempest_replay
    sub w10, w10, #1
    cbz w10, .Ltempest_replay
    sub w10, w10, #1
    cbnz w10, .Ltempest_native
.Ltempest_replay:
    mov w8, #1
.Ltempest_native:
    strb w8, [x20, #0x311]
    b native_tempest_continue

GLOBAL replay_render_gate
    MAILBOX_LOAD x10, x9, 104
    sub x10, x10, x0
    cbnz x10, .Lrender_native
    mov w0, #0
    b native_render_failed_resume
.Lrender_native:
    ldr x8, [x8, #0x548]
    b native_render_continue

GLOBAL replay_intro_mark_gate
    READY_LOAD x9, x9
    cbz x9, replay_intro_native_tail
    adrp x9, toggle_mailbox
    str xzr, [x9, #:lo12:toggle_mailbox + 112]
    cmp w28, #4
    b.hi replay_intro_gate
    cbnz w25, replay_intro_gate
    cbz w27, replay_intro_gate
    ldr w9, [x9, #:lo12:toggle_mailbox + 16]
    cbnz w9, replay_intro_gate
    adrp x9, toggle_mailbox
    add w10, w28, #1
    str x10, [x9, #:lo12:toggle_mailbox + 112]
    b replay_intro_gate

GLOBAL replay_intro_gate
    READY_LOAD x9, x9
    cbz x9, replay_intro_native_tail
    cmp w28, #4
    b.hi .Lintro_native
    cbnz w25, .Lintro_native
    cbz w27, .Lintro_native
    adrp x9, toggle_mailbox
    ldr w9, [x9, #:lo12:toggle_mailbox + 16]
    mov w24, wzr
    eor w19, w9, #1
.Lintro_native:
GLOBAL replay_intro_native_tail
    and w9, w24, w27
    b native_intro_continue

GLOBAL testify_factory_gate
    ldr w8, [x20, #0x310]
    cbnz w8, .Ltestify_factory_native
    READY_LOAD x8, x8
    cbz x8, .Ltestify_factory_native
    MAILBOX_LOAD w21, x8, 16
    cbz w21, .Ltestify_factory_enabled
    str wzr, [x20, #0x324]
    str wzr, [x20, #0x328]
.Ltestify_factory_enabled:
    eor w21, w21, #1
    ldurb w9, [x29, #-0x20]
    b native_testify_factory_choice
.Ltestify_factory_native:
    ldr x8, [x20, #0x330]
    b native_testify_factory_continue

GLOBAL replay_setting_getter_gate
    READY_LOAD x8, x8
    cbz x8, .Lsetting_getter_default
    br x8
.Lsetting_getter_default:
    mov w0, #1
    ret

GLOBAL replay_setting_setter_gate
    MAILBOX_LOAD x8, x8, 8
    cbz x8, .Lsetting_setter_default
    br x8
.Lsetting_setter_default:
    ret

GLOBAL testify_supplied_gate
    cbz x19, .Ltestify_supplied_absent
    ldr w8, [x20, #0x310]
    cbnz w8, .Ltestify_supplied_native
    READY_LOAD x8, x8
    cbz x8, .Ltestify_supplied_native
    MAILBOX_LOAD w8, x8, 16
    cbz w8, .Ltestify_supplied_native
    ldr x8, [x19]
    adrp x9, native_testify_challenge_vtable
    add x9, x9, :lo12:native_testify_challenge_vtable
    cmp x8, x9
    b.ne .Ltestify_supplied_native
    ldr w8, [x19, #0x2f4]
    cmp w8, #2
    b.ne .Ltestify_supplied_native
    str wzr, [x20, #0x324]
    str wzr, [x20, #0x328]
    b native_testify_supplied_release
.Ltestify_supplied_native:
    b native_testify_supplied_continue
.Ltestify_supplied_absent:
    b native_testify_supplied_absent
GLOBAL replay_gates_end
.section .note.GNU-stack,"",%progbits
