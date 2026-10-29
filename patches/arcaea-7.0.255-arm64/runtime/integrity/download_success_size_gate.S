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
