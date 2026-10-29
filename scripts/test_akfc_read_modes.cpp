// Host regression test. actual_read_hook.inc must contain the extracted hook,
// not a rewritten copy. No real file or cryptographic operations run here.
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

using std::size_t;
using std::uint8_t;
using std::strcmp;

static const char* const original_path = "/synthetic/dl/0.aff";
static const char* const materialized_path = "/synthetic/cache/plain.aff";
static const std::vector<uint8_t> ciphertext{'A', 'K', 'F', 'C', 1};
static const std::vector<uint8_t> plaintext{'p', 'l', 'a', 'i', 'n'};
static FILE original_handle{};
static FILE materialized_handle{};
static int failures = 0;
static std::string test_name;

static void check(bool condition, const char* message) {
    if (!condition) {
        std::fprintf(stderr, "FAIL [%s]: %s\n", test_name.c_str(), message);
        ++failures;
    }
}

struct State {
    int detect = 0, wait = 0, read = 0, decrypt = 0, materialize = 0, open = 0;
    bool akfc = true, complete = true, readable = true;
    bool decryptable = true, writable = true;
    bool null_path = false, null_mode = false;
    std::string opened_path, opened_mode;
};
static State state;

static void reset(const std::string& name) {
    state = State{};
    test_name = name;
}

static FILE* fake_fopen(const char* path, const char* mode) {
    ++state.open;
    state.null_path = path == nullptr;
    state.null_mode = mode == nullptr;
    state.opened_path = path ? path : "";
    state.opened_mode = mode ? mode : "";
    return path && state.opened_path == materialized_path
        ? &materialized_handle : &original_handle;
}
static FILE* (*real_fopen)(const char*, const char*) = fake_fopen;

static bool is_akfc_file(const char* path) {
    ++state.detect;
    check(path && std::string(path) == original_path, "detector receives original path");
    return state.akfc;
}

static bool wait_for_file_complete(const char* path, int timeout_ms) {
    ++state.wait;
    check(path && std::string(path) == original_path, "wait receives original path");
    check(timeout_ms == 2000, "download completeness timeout remains 2000 ms");
    return state.complete;
}

static std::vector<uint8_t> read_file(const char* path) {
    ++state.read;
    check(path && std::string(path) == original_path, "reader receives original path");
    return state.readable ? ciphertext : std::vector<uint8_t>{};
}

static std::vector<uint8_t> decrypt_akfc(const uint8_t* data, size_t size,
                                         const char* path) {
    ++state.decrypt;
    check(path && std::string(path) == original_path, "decrypt receives original path");
    check(data && size == ciphertext.size() &&
          std::memcmp(data, ciphertext.data(), size) == 0,
          "decrypt receives encrypted bytes returned by reader");
    return state.decryptable ? plaintext : std::vector<uint8_t>{};
}

static std::string write_temp_file(const std::vector<uint8_t>& data, const char* path) {
    ++state.materialize;
    check(path && std::string(path) == original_path, "materializer receives original path");
    check(data == plaintext, "materializer receives decrypted plaintext");
    return state.writable ? materialized_path : "";
}

#define LOGI(...) ((void)0)
#define LOGE(...) ((void)0)
#include "actual_read_hook.inc"

static void counts(int detect, int wait, int read, int decrypt, int materialize, int open) {
    check(state.detect == detect && state.wait == wait && state.read == read &&
          state.decrypt == decrypt && state.materialize == materialize && state.open == open,
          "dispatch reaches exactly the expected stages");
}

static void opened(const char* path, const char* mode) {
    check(state.null_path == (path == nullptr), "null path is preserved");
    check(state.null_mode == (mode == nullptr), "null mode is preserved");
    check(state.opened_path == (path ? path : ""), "real opener receives expected path");
    check(state.opened_mode == (mode ? mode : ""), "real opener receives unchanged mode");
}

int main(int argc, char** argv) {
    const bool baseline = argc == 2 && strcmp(argv[1], "--expect-baseline") == 0;
    if (argc != 1 && !baseline) {
        std::fprintf(stderr, "usage: %s [--expect-baseline]\n", argv[0]);
        return 2;
    }

    for (const char* mode : {"rb", "r", "rb+", "rbe"}) {
        reset(std::string("read mode ") + mode);
        const bool intercepted = !baseline || strcmp(mode, "rbe") != 0;
        FILE* result = hooked_fopen(original_path, mode);
        check(result == (intercepted ? &materialized_handle : &original_handle),
              "caller receives expected original or plaintext stream");
        counts(intercepted, intercepted, intercepted, intercepted, intercepted, 1);
        opened(intercepted ? materialized_path : original_path, mode);
    }

    for (const char* mode : {"wb", "ab", "r+b", "", "invalid", "rbee", "rbx", "re"}) {
        reset(std::string("unchanged mode '") + mode + "'");
        check(hooked_fopen(original_path, mode) == &original_handle,
              "other modes return original stream");
        counts(0, 0, 0, 0, 0, 1);
        opened(original_path, mode);
    }

    for (int variant = 0; variant < 3; ++variant) {
        reset("null pass-through " + std::to_string(variant));
        const char* path = variant == 1 ? original_path : nullptr;
        const char* mode = variant == 0 ? "rb" : nullptr;
        check(hooked_fopen(path, mode) == &original_handle, "null arguments pass through");
        counts(0, 0, 0, 0, 0, 1);
        opened(path, mode);
    }

    // Exercise the existing failure contracts through a supported read mode.
    const char* failure_mode = baseline ? "rb" : "rbe";
    for (int stage = 0; stage < 5; ++stage) {
        reset("read failure stage " + std::to_string(stage));
        state.akfc = stage != 0;
        state.complete = stage != 1;
        state.readable = stage != 2;
        state.decryptable = stage != 3;
        state.writable = stage != 4;
        FILE* result = hooked_fopen(original_path, failure_mode);
        check(result == (stage == 2 ? nullptr : &original_handle),
              "failure preserves original fallback or empty-read null result");
        counts(1, stage >= 1, stage >= 2, stage >= 3, stage >= 4, stage == 2 ? 0 : 1);
        if (stage != 2) opened(original_path, failure_mode);
    }

    if (failures) return 1;
    std::printf("PASS: extracted hooked_fopen (%s expectation); modes, nulls, and failures\n",
                baseline ? "baseline" : "candidate");
    return 0;
}
