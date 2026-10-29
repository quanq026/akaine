#pragma once

// Include inside staging_cli after account_adapter.h and the common cli_files.h.
namespace account_controls {
constexpr Size CREDENTIAL_HEADER_SIZE = 76;
constexpr Size CREDENTIAL_FILE_LIMIT = CREDENTIAL_HEADER_SIZE + 64 + 256;
enum class CredentialResult { ok, missing, rejected, expired, io_error };
struct CredentialBuffer {
    char username[65] = {}, password[257] = {};
    Size username_size = 0, password_size = 0;
    CredentialBuffer() = default;
    CredentialBuffer(const CredentialBuffer&) = delete;
    CredentialBuffer& operator=(const CredentialBuffer&) = delete;
    void clear() { wipe(username, sizeof(username)); wipe(password, sizeof(password)); username_size = password_size = 0; }
    ~CredentialBuffer() { clear(); }
};
struct CredentialBytes {
    unsigned char data[CREDENTIAL_FILE_LIMIT + 1] = {};
    ~CredentialBytes() { wipe(data, sizeof(data)); }
};

inline CredentialResult parse_credential(const unsigned char* bytes, Size size,
    const akaine_cli::Request& request, const char* session, uint64_t now, CredentialBuffer& output) {
    output.clear();
    if (strcmp(request.command, "account") || strcmp(request.argument, "fill")
        || !akaine_cli::hex_id(request.id, 32) || request.id[32]
        || !akaine_cli::hex_id(request.session, 32) || request.session[32]
        || !session || strlen(session) != 32 || !akaine_cli::hex_id(session, 32)) return CredentialResult::rejected;
    if (const char* guard = akaine_cli::request_guard(request, session, now))
        return !strcmp(guard, "EXPIRED") ? CredentialResult::expired : CredentialResult::rejected;
    if (!bytes || size < CREDENTIAL_HEADER_SIZE || size > CREDENTIAL_FILE_LIMIT
        || memcmp(bytes, "AKCRED1\n", 8) || memcmp(bytes + 8, session, 32)
        || memcmp(bytes + 40, request.id, 32)) return CredentialResult::rejected;
    const Size username_size = Size(bytes[72]) | (Size(bytes[73]) << 8);
    const Size password_size = Size(bytes[74]) | (Size(bytes[75]) << 8);
    if (!username_size || username_size > 64 || !password_size || password_size > 256
        || size != CREDENTIAL_HEADER_SIZE + username_size + password_size) return CredentialResult::rejected;
    memcpy(output.username, bytes + CREDENTIAL_HEADER_SIZE, username_size);
    memcpy(output.password, bytes + CREDENTIAL_HEADER_SIZE + username_size, password_size);
    if (!valid_input(output.username, username_size) || !valid_input(output.password, password_size)) {
        output.clear(); return CredentialResult::rejected;
    }
    output.username_size = username_size; output.password_size = password_size;
    return CredentialResult::ok;
}

inline CredentialResult load_credential(int directory, const akaine_cli::Request& request,
    const char* session, uint64_t now, CredentialBuffer& output) {
    output.clear();
    if (!akaine_cli::owned_directory(directory, getuid(), true)) return CredentialResult::rejected;
    const int fd = openat(directory, "credential", O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
    if (fd < 0) return errno == ENOENT ? CredentialResult::missing : CredentialResult::rejected;
    struct stat before = {}, named = {};
    bool valid = !fstat(fd, &before) && S_ISREG(before.st_mode) && before.st_uid == getuid()
        && before.st_nlink == 1 && (before.st_mode & 0777) == 0600;
    if (!valid) { close(fd); return CredentialResult::rejected; }
    valid = !fstatat(directory, "credential", &named, AT_SYMLINK_NOFOLLOW)
        && named.st_dev == before.st_dev && named.st_ino == before.st_ino;
    unlinkat(directory, "credential.inflight", 0);
    if (!valid || renameat(directory, "credential", directory, "credential.inflight")) {
        close(fd); return CredentialResult::rejected;
    }
    valid = !fstatat(directory, "credential.inflight", &named, AT_SYMLINK_NOFOLLOW)
        && S_ISREG(named.st_mode) && named.st_dev == before.st_dev && named.st_ino == before.st_ino;
    // The credential has no directory entry before any secret bytes are read.
    const bool removed = unlinkat(directory, "credential.inflight", 0) == 0;
    if (!valid || !removed || before.st_size < ssize_t(CREDENTIAL_HEADER_SIZE)
        || before.st_size > ssize_t(CREDENTIAL_FILE_LIMIT)) { close(fd); return CredentialResult::rejected; }
    CredentialBytes bytes;
    const ssize_t size = read(fd, bytes.data, sizeof(bytes.data));
    struct stat after = {};
    valid = size == before.st_size && !fstat(fd, &after) && after.st_size == before.st_size
        && after.st_dev == before.st_dev && after.st_ino == before.st_ino && after.st_nlink == 0
        && after.st_uid == getuid() && (after.st_mode & 0777) == 0600;
    close(fd);
    if (!valid) return CredentialResult::io_error;
    return parse_credential(bytes.data, Size(size), request, session, now, output);
}
} // namespace account_controls
