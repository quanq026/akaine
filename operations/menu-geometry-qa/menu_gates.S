.section .menu_trace,"ax",%progbits
.p2align 4
.p2align 4
.global menu_gate_0
menu_gate_0:
sub sp, sp, #0x2c0
stp x0, x1, [sp, #0]
stp x2, x3, [sp, #16]
stp x4, x5, [sp, #32]
stp x6, x7, [sp, #48]
stp x8, x9, [sp, #64]
stp x10, x11, [sp, #80]
stp x12, x13, [sp, #96]
stp x14, x15, [sp, #112]
stp x16, x17, [sp, #128]
stp x18, x30, [sp, #0x90]
mrs x16, nzcv
mrs x17, fpcr
stp x16, x17, [sp, #0xa0]
mrs x16, fpsr
str x16, [sp, #0xb0]
stp q0, q1, [sp, #192]
stp q2, q3, [sp, #224]
stp q4, q5, [sp, #256]
stp q6, q7, [sp, #288]
stp q8, q9, [sp, #320]
stp q10, q11, [sp, #352]
stp q12, q13, [sp, #384]
stp q14, q15, [sp, #416]
stp q16, q17, [sp, #448]
stp q18, q19, [sp, #480]
stp q20, q21, [sp, #512]
stp q22, q23, [sp, #544]
stp q24, q25, [sp, #576]
stp q26, q27, [sp, #608]
stp q28, q29, [sp, #640]
stp q30, q31, [sp, #672]
adrp x16, menu_mailbox
add x16, x16, :lo12:menu_mailbox
ldr x17, [x16]
cmp x17, #1
b.ne menu_restore_0
add x17, x16, #8
ldar x17, [x17]
cmp x17, #1
b.ne menu_restore_0
ldr x16, [x16, #72]
cbz x16, menu_restore_0
mov w0, #1
mov w1, #0
blr x16
menu_restore_0:
ldp q0, q1, [sp, #192]
ldp q2, q3, [sp, #224]
ldp q4, q5, [sp, #256]
ldp q6, q7, [sp, #288]
ldp q8, q9, [sp, #320]
ldp q10, q11, [sp, #352]
ldp q12, q13, [sp, #384]
ldp q14, q15, [sp, #416]
ldp q16, q17, [sp, #448]
ldp q18, q19, [sp, #480]
ldp q20, q21, [sp, #512]
ldp q22, q23, [sp, #544]
ldp q24, q25, [sp, #576]
ldp q26, q27, [sp, #608]
ldp q28, q29, [sp, #640]
ldp q30, q31, [sp, #672]
ldp x16, x17, [sp, #0xa0]
msr nzcv, x16
msr fpcr, x17
ldr x16, [sp, #0xb0]
msr fpsr, x16
ldp x0, x1, [sp, #0]
ldp x2, x3, [sp, #16]
ldp x4, x5, [sp, #32]
ldp x6, x7, [sp, #48]
ldp x8, x9, [sp, #64]
ldp x10, x11, [sp, #80]
ldp x12, x13, [sp, #96]
ldp x14, x15, [sp, #112]
ldp x16, x17, [sp, #128]
ldp x18, x30, [sp, #0x90]
add sp, sp, #0x2c0
.word 0x6db923e9
b menu_resume_0
.p2align 4
.global menu_gate_1
menu_gate_1:
sub sp, sp, #0x2c0
stp x0, x1, [sp, #0]
stp x2, x3, [sp, #16]
stp x4, x5, [sp, #32]
stp x6, x7, [sp, #48]
stp x8, x9, [sp, #64]
stp x10, x11, [sp, #80]
stp x12, x13, [sp, #96]
stp x14, x15, [sp, #112]
stp x16, x17, [sp, #128]
stp x18, x30, [sp, #0x90]
mrs x16, nzcv
mrs x17, fpcr
stp x16, x17, [sp, #0xa0]
mrs x16, fpsr
str x16, [sp, #0xb0]
stp q0, q1, [sp, #192]
stp q2, q3, [sp, #224]
stp q4, q5, [sp, #256]
stp q6, q7, [sp, #288]
stp q8, q9, [sp, #320]
stp q10, q11, [sp, #352]
stp q12, q13, [sp, #384]
stp q14, q15, [sp, #416]
stp q16, q17, [sp, #448]
stp q18, q19, [sp, #480]
stp q20, q21, [sp, #512]
stp q22, q23, [sp, #544]
stp q24, q25, [sp, #576]
stp q26, q27, [sp, #608]
stp q28, q29, [sp, #640]
stp q30, q31, [sp, #672]
adrp x16, menu_mailbox
add x16, x16, :lo12:menu_mailbox
ldr x17, [x16]
cmp x17, #1
b.ne menu_restore_1
add x17, x16, #8
ldar x17, [x17]
cmp x17, #1
b.ne menu_restore_1
ldr x16, [x16, #72]
cbz x16, menu_restore_1
mov w0, #1
mov w1, #1
blr x16
menu_restore_1:
ldp q0, q1, [sp, #192]
ldp q2, q3, [sp, #224]
ldp q4, q5, [sp, #256]
ldp q6, q7, [sp, #288]
ldp q8, q9, [sp, #320]
ldp q10, q11, [sp, #352]
ldp q12, q13, [sp, #384]
ldp q14, q15, [sp, #416]
ldp q16, q17, [sp, #448]
ldp q18, q19, [sp, #480]
ldp q20, q21, [sp, #512]
ldp q22, q23, [sp, #544]
ldp q24, q25, [sp, #576]
ldp q26, q27, [sp, #608]
ldp q28, q29, [sp, #640]
ldp q30, q31, [sp, #672]
ldp x16, x17, [sp, #0xa0]
msr nzcv, x16
msr fpcr, x17
ldr x16, [sp, #0xb0]
msr fpsr, x16
ldp x0, x1, [sp, #0]
ldp x2, x3, [sp, #16]
ldp x4, x5, [sp, #32]
ldp x6, x7, [sp, #48]
ldp x8, x9, [sp, #64]
ldp x10, x11, [sp, #80]
ldp x12, x13, [sp, #96]
ldp x14, x15, [sp, #112]
ldp x16, x17, [sp, #128]
ldp x18, x30, [sp, #0x90]
add sp, sp, #0x2c0
.word 0xd65f03c0
.p2align 4
.global menu_gate_2
menu_gate_2:
sub sp, sp, #0x2c0
stp x0, x1, [sp, #0]
stp x2, x3, [sp, #16]
stp x4, x5, [sp, #32]
stp x6, x7, [sp, #48]
stp x8, x9, [sp, #64]
stp x10, x11, [sp, #80]
stp x12, x13, [sp, #96]
stp x14, x15, [sp, #112]
stp x16, x17, [sp, #128]
stp x18, x30, [sp, #0x90]
mrs x16, nzcv
mrs x17, fpcr
stp x16, x17, [sp, #0xa0]
mrs x16, fpsr
str x16, [sp, #0xb0]
stp q0, q1, [sp, #192]
stp q2, q3, [sp, #224]
stp q4, q5, [sp, #256]
stp q6, q7, [sp, #288]
stp q8, q9, [sp, #320]
stp q10, q11, [sp, #352]
stp q12, q13, [sp, #384]
stp q14, q15, [sp, #416]
stp q16, q17, [sp, #448]
stp q18, q19, [sp, #480]
stp q20, q21, [sp, #512]
stp q22, q23, [sp, #544]
stp q24, q25, [sp, #576]
stp q26, q27, [sp, #608]
stp q28, q29, [sp, #640]
stp q30, q31, [sp, #672]
adrp x16, menu_mailbox
add x16, x16, :lo12:menu_mailbox
ldr x17, [x16]
cmp x17, #1
b.ne menu_restore_2
add x17, x16, #8
ldar x17, [x17]
cmp x17, #1
b.ne menu_restore_2
ldr x16, [x16, #72]
cbz x16, menu_restore_2
mov w0, #2
mov w1, #0
blr x16
menu_restore_2:
ldp q0, q1, [sp, #192]
ldp q2, q3, [sp, #224]
ldp q4, q5, [sp, #256]
ldp q6, q7, [sp, #288]
ldp q8, q9, [sp, #320]
ldp q10, q11, [sp, #352]
ldp q12, q13, [sp, #384]
ldp q14, q15, [sp, #416]
ldp q16, q17, [sp, #448]
ldp q18, q19, [sp, #480]
ldp q20, q21, [sp, #512]
ldp q22, q23, [sp, #544]
ldp q24, q25, [sp, #576]
ldp q26, q27, [sp, #608]
ldp q28, q29, [sp, #640]
ldp q30, q31, [sp, #672]
ldp x16, x17, [sp, #0xa0]
msr nzcv, x16
msr fpcr, x17
ldr x16, [sp, #0xb0]
msr fpsr, x16
ldp x0, x1, [sp, #0]
ldp x2, x3, [sp, #16]
ldp x4, x5, [sp, #32]
ldp x6, x7, [sp, #48]
ldp x8, x9, [sp, #64]
ldp x10, x11, [sp, #80]
ldp x12, x13, [sp, #96]
ldp x14, x15, [sp, #112]
ldp x16, x17, [sp, #128]
ldp x18, x30, [sp, #0x90]
add sp, sp, #0x2c0
.word 0xd102c3ff
b menu_resume_2
.p2align 4
.global menu_gate_3
menu_gate_3:
sub sp, sp, #0x2c0
stp x0, x1, [sp, #0]
stp x2, x3, [sp, #16]
stp x4, x5, [sp, #32]
stp x6, x7, [sp, #48]
stp x8, x9, [sp, #64]
stp x10, x11, [sp, #80]
stp x12, x13, [sp, #96]
stp x14, x15, [sp, #112]
stp x16, x17, [sp, #128]
stp x18, x30, [sp, #0x90]
mrs x16, nzcv
mrs x17, fpcr
stp x16, x17, [sp, #0xa0]
mrs x16, fpsr
str x16, [sp, #0xb0]
stp q0, q1, [sp, #192]
stp q2, q3, [sp, #224]
stp q4, q5, [sp, #256]
stp q6, q7, [sp, #288]
stp q8, q9, [sp, #320]
stp q10, q11, [sp, #352]
stp q12, q13, [sp, #384]
stp q14, q15, [sp, #416]
stp q16, q17, [sp, #448]
stp q18, q19, [sp, #480]
stp q20, q21, [sp, #512]
stp q22, q23, [sp, #544]
stp q24, q25, [sp, #576]
stp q26, q27, [sp, #608]
stp q28, q29, [sp, #640]
stp q30, q31, [sp, #672]
adrp x16, menu_mailbox
add x16, x16, :lo12:menu_mailbox
ldr x17, [x16]
cmp x17, #1
b.ne menu_restore_3
add x17, x16, #8
ldar x17, [x17]
cmp x17, #1
b.ne menu_restore_3
ldr x16, [x16, #72]
cbz x16, menu_restore_3
mov w0, #2
mov w1, #1
blr x16
menu_restore_3:
ldp q0, q1, [sp, #192]
ldp q2, q3, [sp, #224]
ldp q4, q5, [sp, #256]
ldp q6, q7, [sp, #288]
ldp q8, q9, [sp, #320]
ldp q10, q11, [sp, #352]
ldp q12, q13, [sp, #384]
ldp q14, q15, [sp, #416]
ldp q16, q17, [sp, #448]
ldp q18, q19, [sp, #480]
ldp q20, q21, [sp, #512]
ldp q22, q23, [sp, #544]
ldp q24, q25, [sp, #576]
ldp q26, q27, [sp, #608]
ldp q28, q29, [sp, #640]
ldp q30, q31, [sp, #672]
ldp x16, x17, [sp, #0xa0]
msr nzcv, x16
msr fpcr, x17
ldr x16, [sp, #0xb0]
msr fpsr, x16
ldp x0, x1, [sp, #0]
ldp x2, x3, [sp, #16]
ldp x4, x5, [sp, #32]
ldp x6, x7, [sp, #48]
ldp x8, x9, [sp, #64]
ldp x10, x11, [sp, #80]
ldp x12, x13, [sp, #96]
ldp x14, x15, [sp, #112]
ldp x16, x17, [sp, #128]
ldp x18, x30, [sp, #0x90]
add sp, sp, #0x2c0
.word 0xd65f03c0
.section .note.GNU-stack,"",%progbits
