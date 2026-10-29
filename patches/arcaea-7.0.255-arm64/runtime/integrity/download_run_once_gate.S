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
