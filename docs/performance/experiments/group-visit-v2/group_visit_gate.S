.section .group_visit_gate,"ax",%progbits
.p2align 4
.global group_visit_gate
group_visit_gate:
    adrp x16, owned_mailbox
    add x16, x16, :lo12:owned_mailbox
    ldr x17, [x16]
    eor x17, x17, #1
    cbnz x17, group_visit_fallback
    add x17, x16, #8
    ldar x17, [x17]
    eor x17, x17, #1
    cbnz x17, group_visit_fallback
    ldr x16, [x16, #88]
    cbz x16, group_visit_fallback
    br x16
group_visit_fallback:
    b native_group_visit
.section .note.GNU-stack,"",%progbits
