#pragma once
#include <cerrno>
#include <cstddef>
#include <cstring>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace akaine_sfx71 {
struct WaveFile { const char* song; const char* name; };
inline constexpr char URI_PREFIX[] = "file:///android_asset/songs/dl_";
inline constexpr std::size_t NAME_LIMIT = 256;

inline std::size_t bounded_length(const char* text, std::size_t limit) noexcept {
    if (!text) return limit;
    std::size_t size = 0;
    while (size < limit && text[size]) ++size;
    return size;
}

inline bool component(const char* text, std::size_t size) noexcept {
    if (!text || !size || text[0] == '.') return false;
    for (std::size_t i = 0; i < size; ++i) {
        const unsigned char c = static_cast<unsigned char>(text[i]);
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')
              || c == '_' || c == '-' || c == '.')) return false;
        if (c == '.' && i && text[i - 1] == '.') return false;
    }
    return true;
}

inline bool row_lengths(const WaveFile& row, std::size_t& song, std::size_t& name) noexcept {
    song = bounded_length(row.song, NAME_LIMIT);
    name = bounded_length(row.name, NAME_LIMIT);
    return song < NAME_LIMIT && name < NAME_LIMIT && song + name + 2 <= NAME_LIMIT
        && component(row.song, song) && component(row.name, name) && name > 4
        && !std::memcmp(row.name + name - 4, ".wav", 4);
}

inline const WaveFile* find_wave(const char* uri, const WaveFile* rows, std::size_t count) noexcept {
    constexpr std::size_t prefix = sizeof(URI_PREFIX) - 1;
    const std::size_t size = bounded_length(uri, prefix + NAME_LIMIT);
    if (!rows || size <= prefix || size == prefix + NAME_LIMIT
        || std::memcmp(uri, URI_PREFIX, prefix)) return nullptr;
    const char* song = uri + prefix;
    const char* slash = static_cast<const char*>(std::memchr(song, '/', size - prefix));
    if (!slash) return nullptr;
    const std::size_t song_size = static_cast<std::size_t>(slash - song);
    const char* name = slash + 1;
    const std::size_t name_size = size - prefix - song_size - 1;
    if (!component(song, song_size) || !component(name, name_size)) return nullptr;
    for (std::size_t i = 0; i < count; ++i) {
        std::size_t declared_song = 0, declared_name = 0;
        if (row_lengths(rows[i], declared_song, declared_name) && declared_song == song_size
            && declared_name == name_size && !std::memcmp(song, rows[i].song, song_size)
            && !std::memcmp(name, rows[i].name, name_size)) return rows + i;
    }
    return nullptr;
}

inline int close_failed(int fd, int error) noexcept {
    ::close(fd);
    errno = error;
    return -1;
}

inline int open_wave(int dl_fd, const WaveFile& row) noexcept {
    const int incoming_errno = errno;
    std::size_t song = 0, name = 0;
    if (!row_lengths(row, song, name)) { errno = EINVAL; return -1; }
    char flat[NAME_LIMIT];
    std::memcpy(flat, row.song, song);
    flat[song] = '_';
    std::memcpy(flat + song + 1, row.name, name);
    flat[song + name + 1] = '\0';
    const int fd = ::openat(dl_fd, flat, O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
    if (fd < 0) return -1;
    struct stat info = {};
    if (::fstat(fd, &info) < 0) return close_failed(fd, errno);
    if (!S_ISREG(info.st_mode) || info.st_size < 12) return close_failed(fd, EINVAL);
    if (info.st_uid != ::geteuid() || info.st_nlink != 1) return close_failed(fd, EPERM);
    unsigned char header[12];
    ssize_t read = 0;
    do { read = ::pread(fd, header, sizeof(header), 0); } while (read < 0 && errno == EINTR);
    if (read < 0) return close_failed(fd, errno);
    if (read != static_cast<ssize_t>(sizeof(header)) || std::memcmp(header, "RIFF", 4)
        || std::memcmp(header + 8, "WAVE", 4)) return close_failed(fd, EINVAL);
    errno = incoming_errno;
    return fd;
}
}
