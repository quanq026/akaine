/* The caller has already sorted the 56-byte records.
 * Bound the display loop without writing its vector or its backing records.
 */
.text
.p2align 2
.global akaine_qa_news_limit
.type akaine_qa_news_limit,%function
akaine_qa_news_limit:
    ldr x27, [x20, #0x398]
    str x16, [sp, #-16]!
    cbz x19, .Lreturn
    cmp x27, x19
    b.lo .Lreturn
    adds x16, x19, #560
    b.hs .Lreturn
    cmp x27, x16
    csel x27, x27, x16, ls
.Lreturn:
    ldr x16, [sp], #16
    b news_resume
.size akaine_qa_news_limit, .-akaine_qa_news_limit
.section .note.GNU-stack,"",%progbits
