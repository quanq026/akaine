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
