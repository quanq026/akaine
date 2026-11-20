#pragma once
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#include "cli_core.h"

namespace akaine_cli {
inline bool owned_directory(int fd, uid_t uid, bool private_mode = false) {
    struct stat st = {};
    return fd >= 0 && !fstat(fd, &st) && S_ISDIR(st.st_mode) && st.st_uid == uid
        && !(st.st_mode & 0022) && (!private_mode || (st.st_mode & 0777) == 0700);
}
// Android ContextImpl creates files/ with 0771. The app UID/GID may write
// this parent; the bridge child itself still requires exactly0700.
inline bool valid_files_parent(const struct stat& st, uid_t uid, gid_t gid) {
    return S_ISDIR(st.st_mode) && st.st_uid == uid && st.st_gid == gid && !(st.st_mode & 0002);
}
inline bool owned_files_parent(int fd, uid_t uid, gid_t gid) {
    struct stat st = {};
    return fd >= 0 && !fstat(fd, &st) && valid_files_parent(st, uid, gid);
}
inline bool atomic_json(int directory, const char* temporary, const char* target, const Json& json) {
    if (!json.good || !owned_directory(directory, getuid(), true)) return false;
    // unlink removes a link itself and never follows it. The exclusive open then
    // rejects collisions, FIFOs and links instead of blocking the GL thread.
    unlinkat(directory, temporary, 0);
    int fd = openat(directory, temporary, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC, 0600);
    if (fd < 0) return false;
    struct stat st = {};
    bool valid = !fstat(fd, &st) && S_ISREG(st.st_mode) && st.st_uid == getuid()
        && st.st_nlink == 1 && (st.st_mode & 0777) == 0600;
    bool written = valid && write(fd, json.data, json.used) == ssize_t(json.used);
    close(fd);
    if (written) written = renameat(directory, temporary, directory, target) == 0;
    if (!written) unlinkat(directory, temporary, 0);
    return written;
}
// Return 0 when absent/unsafe, otherwise consume exactly the inode we opened.
// Never follows symlinks and O_NONBLOCK prevents a FIFO open from waiting.
inline size_t consume(int directory, char (&bytes)[REQUEST_LIMIT + 1]) {
    if (!owned_directory(directory, getuid(), true)) return 0;
    int fd = openat(directory, "request", O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
    if (fd < 0) return 0;
    struct stat st = {};
    bool valid = !fstat(fd, &st) && S_ISREG(st.st_mode) && st.st_uid == getuid()
        && st.st_nlink == 1 && (st.st_mode & 0777) == 0600 && st.st_size > 0 && st.st_size <= ssize_t(REQUEST_LIMIT);
    if (!valid) { close(fd); return 0; }
    struct stat named = {};
    valid = !fstatat(directory, "request", &named, AT_SYMLINK_NOFOLLOW)
        && named.st_dev == st.st_dev && named.st_ino == st.st_ino;
    unlinkat(directory, "inflight", 0);
    if (!valid || renameat(directory, "request", directory, "inflight")) { close(fd); return 0; }
    valid = !fstatat(directory, "inflight", &named, AT_SYMLINK_NOFOLLOW)
        && S_ISREG(named.st_mode) && named.st_dev == st.st_dev && named.st_ino == st.st_ino;
    ssize_t n = valid ? read(fd, bytes, REQUEST_LIMIT + 1) : -1;
    struct stat after = {};
    valid = valid && !fstat(fd, &after) && after.st_size == st.st_size && n == st.st_size;
    close(fd);
    unlinkat(directory, "inflight", 0);
    if (!valid) return 0;
    bytes[n] = 0;
    return size_t(n);
}
}
