.section .reset_gate,"ax",%progbits
.p2align 4
.global reset_default_second_refresh_gate
.type reset_default_second_refresh_gate,%function

.macro SAVE_TEMP
    sub sp, sp, #0x40
    stp x8, x9, [sp, #0x00]
    stp x10, x11, [sp, #0x10]
    stp x12, x13, [sp, #0x20]
    mrs x12, nzcv
    str x12, [sp, #0x30]
.endm
.macro RESTORE_TEMP
    ldr x12, [sp, #0x30]
    msr nzcv, x12
    ldp x8, x9, [sp, #0x00]
    ldp x10, x11, [sp, #0x10]
    ldp x12, x13, [sp, #0x20]
    add sp, sp, #0x40
.endm

reset_default_second_refresh_gate:
    SAVE_TEMP
    ldr x8, [x29, #8]
    adrp x9, reset_call_return
    add x9, x9, :lo12:reset_call_return
    cmp x8, x9
    b.ne original_path
    cmp w22, #1
    b.ne original_path
    cbnz w21, original_path
    cbnz w23, original_path
    ldr x8, [x19]
    cbz x8, original_path
    ldp w9, w10, [x8, #0x70]
    cmp w9, #1
    b.ne original_path
    cbnz w10, original_path
    ldr w9, [x8, #0xcc]
    cbnz w9, original_path
    ldrb w9, [x8, #0x78]
    cbnz w9, original_path
    ldrb w9, [x8, #0x80]
    tbnz w9, #0, empty_long_query
    lsr w9, w9, #1
    cbnz w9, original_path
    b persistence_tail
empty_long_query:
    ldr x9, [x8, #0x88]
    cbnz x9, original_path
persistence_tail:
    RESTORE_TEMP
    b native_persistence_tail
original_path:
    RESTORE_TEMP
    cbnz x0, original_refresh
    b native_persistence_tail
original_refresh:
    b native_refresh_continue
.size reset_default_second_refresh_gate, .-reset_default_second_refresh_gate
.section .note.GNU-stack,"",%progbits
