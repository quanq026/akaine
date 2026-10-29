// One authored V36 ARM64 gate translation unit. Fixed linked sections are hash checked.

// semantic/owned/owned_gates.S
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

// semantic/owned/reset_gate.S
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

// integrity/download_success_size_gate.S
.section .download_size_gate,"ax",%progbits
.global download_success_size_gate
.type download_success_size_gate,%function
download_success_size_gate:
    // x25 is the callback-id map task; global callback capture x24 may belong to another transfer.
    ldr x8, [x25, #0x18]
    cmp x8, #1
    b.lt .Loriginal
    bl native_fileutils_singleton
    ldr x8, [x0]
    ldr x8, [x8, #0x158]
    add x1, sp, #0x18
    blr x8
    ldr x9, [x25, #0x18]
    cmp x0, x9
    b.eq .Loriginal
    // Existing failure cleanup expects an empty digest string at SP+0x38.
    stp xzr, xzr, [sp, #0x38]
    str xzr, [sp, #0x48]
    b native_download_digest_failure
.Loriginal:
    ldrb w8, [x24, #0x70]
    b native_download_skiphash_dispatch
.size download_success_size_gate, .-download_success_size_gate

// integrity/download_run_once_gate.S
.section .download_run_once_gate,"ax",%progbits
.global download_run_once_gate
.type download_run_once_gate,%function
download_run_once_gate:
    // Cached completion can reenter the queue before the initial launch loop resumes.
    ldr x8, [x0, #0xe0]
    cbnz x8, .Lalready_started
    ldrb w8, [x0, #0xe8]
    cbnz w8, .Lalready_started
    sub sp, sp, #0xe0
    b native_download_run_body
.Lalready_started:
    ret
.size download_run_once_gate, .-download_run_once_gate

// integrity/child_order_gate.S
.section .child_order_gate,"ax",%progbits
.p2align 4
.global child_order_gate
child_order_gate:
    adrp x16, owned_mailbox
    add x16, x16, :lo12:owned_mailbox
    ldr x17, [x16]
    cmp x17, #1
    b.ne child_order_fallback
    add x17, x16, #8
    ldar x17, [x17]
    cmp x17, #1
    b.ne child_order_fallback
    ldr x16, [x16, #80]
    cbz x16, child_order_fallback
    mov x3, x19
    ldr x4, [sp, #0x18]
    ldr x5, [sp, #0x30]
    mov x6, x25
    br x16
child_order_fallback:
    b native_child_sort
.section .note.GNU-stack,"",%progbits

// news/news_gates.S
.section .news_gates,"ax",%progbits
.p2align 4
.global news_sort_gate
news_sort_gate:
    adrp x16, owned_mailbox
    add x16, x16, :lo12:owned_mailbox
    ldr x17, [x16]
    eor x17, x17, #1
    cbnz x17, .Lsort_original
    add x17, x16, #8
    ldar x17, [x17]
    eor x17, x17, #1
    cbnz x17, .Lsort_original
    ldr x16, [x16, #88]
    cbz x16, .Lsort_original
    br x16
.Lsort_original:
    b native_news_sort
.p2align 4
.global news_end_gate
news_end_gate:
    ldr x27, [x20, #0x398]
    adrp x16, owned_mailbox
    add x16, x16, :lo12:owned_mailbox
    ldr x17, [x16]
    eor x17, x17, #1
    cbnz x17, .Lend_resume
    add x17, x16, #8
    ldar x17, [x17]
    eor x17, x17, #1
    cbnz x17, .Lend_resume
    ldr x17, [x16, #88]
    cbz x17, .Lend_resume
    ldr x17, [x16, #120]
    mrs x16, tpidr_el0
    eor x17, x17, x16
    cbnz x17, .Lend_resume
    adrp x16, owned_mailbox
    add x16, x16, :lo12:owned_mailbox
    ldr x17, [x16, #96]
    eor x17, x17, x19
    cbnz x17, .Lend_resume
    ldr x17, [x16, #104]
    eor x17, x17, x27
    cbnz x17, .Lend_resume
    add x16, x16, #112
    ldar x17, [x16]
    cbz x17, .Lend_resume
    mov x27, x17
.Lend_resume:
    b native_news_resume
.section .note.GNU-stack,"",%progbits
