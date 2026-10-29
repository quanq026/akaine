// New RX extension only. All fallbacks keep original inline ownership bounded.
.section .owned_gates,"ax",%progbits
.p2align 4
.macro SAVE
    sub sp, sp, #0x3a0
    stp x0, x1, [sp, #0x00]
    stp x2, x3, [sp, #0x10]
    stp x4, x5, [sp, #0x20]
    stp x6, x7, [sp, #0x30]
    stp x8, x9, [sp, #0x40]
    stp x10, x11, [sp, #0x50]
    stp x12, x13, [sp, #0x60]
    stp x14, x15, [sp, #0x70]
    stp x16, x17, [sp, #0x80]
    stp x18, x19, [sp, #0x90]
    stp x20, x21, [sp, #0xa0]
    stp x22, x23, [sp, #0xb0]
    stp x24, x25, [sp, #0xc0]
    stp x26, x27, [sp, #0xd0]
    stp x28, x29, [sp, #0xe0]
    str x30, [sp, #0xf0]
    mrs x16, nzcv
    str x16, [sp, #0xf8]
    stp q0, q1, [sp, #0x100]
    stp q2, q3, [sp, #0x120]
    stp q4, q5, [sp, #0x140]
    stp q6, q7, [sp, #0x160]
    stp q16, q17, [sp, #0x180]
    stp q18, q19, [sp, #0x1a0]
    stp q20, q21, [sp, #0x1c0]
    stp q22, q23, [sp, #0x1e0]
    stp q24, q25, [sp, #0x200]
    stp q26, q27, [sp, #0x220]
    stp q28, q29, [sp, #0x240]
    stp q30, q31, [sp, #0x260]
    stp q8, q9, [sp, #0x280]
    stp q10, q11, [sp, #0x2a0]
    stp q12, q13, [sp, #0x2c0]
    stp q14, q15, [sp, #0x2e0]
    mrs x16, fpcr
    str x16, [sp, #0x300]
    mrs x16, fpsr
    str x16, [sp, #0x308]
.endm
.macro RESTORE
    ldp q0, q1, [sp, #0x100]
    ldp q2, q3, [sp, #0x120]
    ldp q4, q5, [sp, #0x140]
    ldp q6, q7, [sp, #0x160]
    ldp q16, q17, [sp, #0x180]
    ldp q18, q19, [sp, #0x1a0]
    ldp q20, q21, [sp, #0x1c0]
    ldp q22, q23, [sp, #0x1e0]
    ldp q24, q25, [sp, #0x200]
    ldp q26, q27, [sp, #0x220]
    ldp q28, q29, [sp, #0x240]
    ldp q30, q31, [sp, #0x260]
    ldp q8, q9, [sp, #0x280]
    ldp q10, q11, [sp, #0x2a0]
    ldp q12, q13, [sp, #0x2c0]
    ldp q14, q15, [sp, #0x2e0]
    ldr x16, [sp, #0x300]
    msr fpcr, x16
    ldr x16, [sp, #0x308]
    msr fpsr, x16
    ldr x16, [sp, #0xf8]
    msr nzcv, x16
    ldp x0, x1, [sp, #0x00]
    ldp x2, x3, [sp, #0x10]
    ldp x4, x5, [sp, #0x20]
    ldp x6, x7, [sp, #0x30]
    ldp x8, x9, [sp, #0x40]
    ldp x10, x11, [sp, #0x50]
    ldp x12, x13, [sp, #0x60]
    ldp x14, x15, [sp, #0x70]
    ldp x16, x17, [sp, #0x80]
    ldp x18, x19, [sp, #0x90]
    ldp x20, x21, [sp, #0xa0]
    ldp x22, x23, [sp, #0xb0]
    ldp x24, x25, [sp, #0xc0]
    ldp x26, x27, [sp, #0xd0]
    ldp x28, x29, [sp, #0xe0]
    ldr x30, [sp, #0xf0]
    add sp, sp, #0x3a0
.endm
.macro CALLBACK offset, unavailable
    adrp x16, owned_mailbox
    add x16, x16, :lo12:owned_mailbox
    add x17, x16, #8
    ldar x17, [x17]
    cbz x17, \unavailable
    ldr x16, [x16, #\offset]
    cbz x16, \unavailable
    blr x16
.endm

.global owned_constructor_gate
owned_constructor_gate:
    SAVE
    CALLBACK 56, .Lctor_done
.Lctor_done:
    RESTORE
    stp x29, x30, [sp, #-0x10]!
    b native_constructor_continue

.global owned_reset_gate
owned_reset_gate:
    SAVE
    // Clear exactly the real inline region, independent of stale persisted counts.
    add x9, x19, #0x88
    mov x10, #64
.Lclear:
    str xzr, [x9], #8
    subs x10, x10, #1
    b.ne .Lclear
    str xzr, [x19, #0x288]
    mov x0, x19
    CALLBACK 16, .Lreset_done
.Lreset_done:
    RESTORE
    b native_reset_continue

.global owned_append_gate
owned_append_gate:
    SAVE
    mov x0, x19
    mov x1, x23
    mov w2, wzr
    CALLBACK 24, .Lappend_shadow
.Lappend_shadow:
    // Always mirror at most64; callback failure cannot re-enter an unsafe append.
    ldr x8, [x19, #0x288]
    cmp x8, #64
    b.hs .Lappend_done
    add x9, x8, #1
    add x8, x19, x8, lsl #3
    str x23, [x8, #0x88]
    str x9, [x19, #0x288]
.Lappend_done:
    RESTORE
    b native_append_continue

.global owned_reserved_gate
owned_reserved_gate:
    SAVE
    ldr x0, [x0]
    mov w2, #1
    CALLBACK 24, .Lreserved_legacy
    // Callback returns2 only when full dynamic behavior is unavailable.
    cmp w0, #2
    b.eq .Lreserved_legacy
    RESTORE
    ret
.Lreserved_legacy:
    // Original helper is safe only below64; it retains native ID dedup semantics.
    ldr x0, [sp]
    ldr x8, [x0]
    ldr x8, [x8, #0x288]
    cmp x8, #64
    b.hs .Lreserved_drop
    RESTORE
    sub sp, sp, #0x90
    b native_reserved_continue
.Lreserved_drop:
    RESTORE
    ret

.global owned_finish_gate
owned_finish_gate:
    SAVE
    mov x0, x19
    CALLBACK 32, .Lfinish_done
.Lfinish_done:
    RESTORE
    ldr x8, [x19, #0x2a8]
    b native_finish_continue

// Returns native-compatible pointer membership, using a bounded64 fallback.
.macro POINTER_GATE destination, continuation
.global \destination
\destination:
    SAVE
    .ifc \destination,owned_song_member_gate
        mov x1, x0
        mov x0, x19
    .endif
    cbz x1, .Lpointer_true\@
    CALLBACK 40, .Lpointer_legacy\@
    cmp w0, #2
    b.ne .Lpointer_result\@
.Lpointer_legacy\@:
    .ifc \destination,owned_song_member_gate
        ldr x1, [sp]
        ldr x0, [sp, #0x98]
    .else
        ldp x0, x1, [sp]
    .endif
    ldr x8, [x0, #0x288]
    mov x9, #64
    cmp x8, x9
    csel x8, x8, x9, lo
    add x9, x0, #0x88
    mov w0, wzr
    cbz x8, .Lpointer_result\@
.Lpointer_scan\@:
    ldr x10, [x9], #8
    cmp x10, x1
    b.eq .Lpointer_true\@
    subs x8, x8, #1
    b.ne .Lpointer_scan\@
    b .Lpointer_result\@
.Lpointer_true\@:
    mov w0, #1
.Lpointer_result\@:
    .ifc \destination,owned_song_member_gate
        str x0, [sp, #0x48] // savedx9 receivesresultw9
    .else
        str x0, [sp]
    .endif
    RESTORE
    .ifc \destination,owned_song_member_gate
        b \continuation
    .else
        ret
    .endif
.endm
POINTER_GATE owned_pointer_member_gate, 0
POINTER_GATE owned_song_member_gate, native_song_member_continue

.global owned_id_member_gate
owned_id_member_gate:
    SAVE
    mov x0, x19
    mov x1, x20
    CALLBACK 48, .Lid_legacy
    cmp w0, #2
    b.ne .Lid_result
.Lid_legacy:
    ldr x21, [sp, #0x98] // originalmanagerx19
    ldr x23, [sp, #0xa0] // originalstringx20
    ldr x22, [x21, #0x288]
    mov x9, #64
    cmp x22, x9
    csel x22, x22, x9, lo
    mov x24, xzr
    cbz x22, .Lid_false
.Lid_scan:
    add x8, x21, x24, lsl #3
    ldr x8, [x8, #0x88]
    cbz x8, .Lid_next
    add x0, x8, #8
    mov x1, x23
    bl native_string_equal
    cbnz w0, .Lid_true
.Lid_next:
    add x24, x24, #1
    cmp x24, x22
    b.lo .Lid_scan
.Lid_false:
    mov w0, wzr
.Lid_result:
    cbnz w0, .Lid_true
    RESTORE
    add x23, sp, #0x20
    orr x23, x23, #1
    add x25, x20, #1
    b native_id_member_missing
.Lid_true:
    RESTORE
    b native_id_member_owned

.global owned_header_gate
owned_header_gate:
    // OriginalthrowingassignmentBLstaysinitsownnativeFDE;detourthenextinstruction.
    SAVE
    add x0, x19, #0xd8 // caller'srequestvector,notunstableassignreturnx0
    CALLBACK 64, .Lheader_done
.Lheader_done:
    RESTORE
    ldp x1, x2, [x20, #0x88]
    b native_header_continue
