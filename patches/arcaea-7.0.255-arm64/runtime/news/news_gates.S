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
