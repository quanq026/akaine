// The include is extracted from the exact Android source compiled for this candidate.
#include "actual_cache_function.inc"
#include <fstream>
#include <iterator>
static unsigned checks = 0;
static void check(bool value, const char* message) {
    if (!value) { fprintf(stderr, "FAIL %s\n", message); exit(1); }
    ++checks;
}
static void replace(const std::string& path, const std::string& data) {
    FILE* file = fopen(path.c_str(), "wb"); check(file != nullptr, "fixture open");
    check(fwrite(data.data(), 1, data.size(), file) == data.size(), "fixture write");
    check(fclose(file) == 0, "fixture close");
}
static std::string read(const std::string& path) {
    std::ifstream input(path, std::ios::binary);
    return {std::istreambuf_iterator<char>(input), {}};
}
static FILE* short_write(const char*, const char*) {
    FILE* file = fopen("/dev/full", "wb");
    if (file) setvbuf(file, nullptr, _IONBF, 0);
    return file;
}
static FILE* close_failure(const char*, const char*) { return fopen("/dev/full", "wb"); }
int main() {
    char directory[] = "/tmp/akfc-rbe-retry-test-XXXXXX";
    check(mkdtemp(directory) != nullptr, "temporary directory");
    const std::string path = std::string(directory) + "/fan_sample_0.tmp";
    const std::string plaintext = "AudioOffset:0\n-\ntiming(0,202,4);\n";
    const std::vector<uint8_t> authenticated(plaintext.begin(), plaintext.end());
    replace(path, "AKFC encrypted first download");
    check(write_temp_file(authenticated, path.c_str()) == path, "first materialization");
    check(read(path) == plaintext, "first plaintext bytes");
    check(get_cached_plaintext_size(path.c_str()) == plaintext.size(), "first size cached");
    // A later HTTP response replaces a file whose path remains in the cache.
    replace(path, "AKFC encrypted replacement at the exact same cached path");
    check(get_cached_plaintext_size(path.c_str()) == plaintext.size(), "stale path fixture");
    check(write_temp_file(authenticated, path.c_str()) == path, "retry materialization");
    const bool retry_ok = read(path) == plaintext;
    if (!retry_ok) { remove(path.c_str()); rmdir(directory); }
    check(retry_ok, "authenticated retry plaintext bytes");
    check(get_cached_plaintext_size(path.c_str()) == plaintext.size(), "retry size cached");
    // Buffered writes can fail only at fclose, despite a full fwrite return value.
    real_fopen = close_failure;
    check(write_temp_file(authenticated, path.c_str()).empty(), "close failure rejected");
    check(get_cached_plaintext_size(path.c_str()) == 0, "close failure cache cleared");
    check(access(path.c_str(), F_OK) != 0, "close failure partial file removed");
    real_fopen = nullptr;
    replace(path, "AKFC another encrypted replacement");
    check(write_temp_file(authenticated, path.c_str()) == path, "recovery after close failure");
    real_fopen = short_write;
    check(write_temp_file(authenticated, path.c_str()).empty(), "short write rejected");
    check(get_cached_plaintext_size(path.c_str()) == 0, "short write cache cleared");
    check(access(path.c_str(), F_OK) != 0, "short write partial file removed");
    real_fopen = nullptr;
    const std::string absent = std::string(directory) + "/missing/0.tmp";
    check(write_temp_file(authenticated, absent.c_str()).empty(), "open failure rejected");
    check(get_cached_plaintext_size(absent.c_str()) == 0, "open failure no cache");
    check(rmdir(directory) == 0, "temporary directory cleaned");
    printf("PASS %u cache checks\n", checks);
}
