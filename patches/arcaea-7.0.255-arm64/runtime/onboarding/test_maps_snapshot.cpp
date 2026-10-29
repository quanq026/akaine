#include "../semantic/native/maps_snapshot.h"
#include <assert.h>
#include <thread>
#include <unistd.h>
#include <sys/mman.h>
#include <string>

FILE* fixture(const std::string& text) {
    FILE* file = tmpfile(); assert(file);
    assert(fwrite(text.data(), 1, text.size(), file) == text.size());
    rewind(file); return file;
}
int main() {
    using namespace monitor_maps;
    static_assert(sizeof(Snapshot) == 196648 && sizeof(Scope) == 196656);
    Mapping row;
    const char* good = "00001000-00002000 rw-p 0 0:0 0 /path\n";
    assert(parse(good, strlen(good), row) && row.contains(0x1000, 0x1000, true));
    assert(row.contains(0x2000, 0, false) && !row.contains(0x2000, 1, false));
    assert(!row.contains(0, 0, false) && !row.contains(0x1fff, 2, true));
    const char* readonly = "1000-2000 r-xp\n";
    assert(parse(readonly, strlen(readonly), row) && row.contains(0x1800, 1, false) && !row.contains(0x1800, 1, true));
    for (const char* bad : {"", "-2000 r--p", "1000- r--p", "2000-1000 r--p", "1000-1000 r--p", "1000-2000 rwx?", "1000-2000 rw-pjunk", "10000000000000000-2000 r--p"})
        assert(!parse(bad, strlen(bad), row));
    for (size_t length = 0; length < 21; ++length) assert(!parse(good, length, row));
    FILE* file = fixture("1000-2000 r--p\n2000-3000 rw-p\n4000-5000 ---p\n");
    Mapping rows[3]; size_t count = 0;
    auto result = scan(file, [&](const Mapping& value) { rows[count++] = value; return Visit::Continue; });
    assert(result.good && result.rows == 3 && count == 3);
    assert(!rows[0].contains(0x1fff, 2, false)); // Single-mapping policy, even across adjacent readable maps.
    assert(!rows[2].contains(0x4000, 1, false));
    fclose(file);
    file = fixture("1000-2000 r--p\n2000-3000 rw-p\n");
    assert(!scan(file, [](const Mapping&) { return Visit::Continue; }, 1).good); fclose(file);
    file = fixture("1000-2000 r--p " + std::string(1200, 'x') + "\n");
    assert(!scan(file, [](const Mapping&) { return Visit::Continue; }, 8192, 1).good); fclose(file);
    file = fixture("1000-2000 r--p\ninvalid\n");
    assert(!scan(file, [](const Mapping&) { return Visit::Continue; }).good); fclose(file);
    file = fixture("1000-2000 r--p " + std::string(1200, 'x') + "\n2000-3000 rw-p\n");
    result = scan(file, [](const Mapping&) { return Visit::Continue; });
    assert(result.good && result.rows == 2 && result.chunks > 2); fclose(file);
    file = fixture("1000-2000 r--p\n");
    assert(!scan(file, [](const Mapping&) { return Visit::Reject; }).good); fclose(file);
    file = fixture("1000-2000 r--p\n"); close(fileno(file));
    assert(!scan(file, [](const Mapping&) { return Visit::Continue; }).good); fclose(file);
    // Physical Lenovo has8342 rows; bounded scan must reach the later entries.
    auto many = [](size_t count) {
        std::string text;
        for (size_t i=0; i<count; ++i) {
            char line[96];
            snprintf(line,sizeof(line),"%zx-%zx %s 0 0:0 0\n",(i+1)*0x2000,(i+1)*0x2000+0x1000,
                     i % 4 ? "r--p" : "---p");
            text += line;
        }
        return text;
    };
    file=fixture(many(8342)); size_t visited=0;
    result=scan(file,[&](const Mapping&){++visited;return Visit::Continue;});
    assert(result.good && result.rows==8342 && visited==8342); fclose(file);
    file=fixture(many(8342));
    result=scan(file,[](const Mapping&){return Visit::Continue;},8192);
    assert(!result.good && result.rows==8193); fclose(file);
    file=fixture(many(16384));
    result=scan(file,[](const Mapping&){return Visit::Continue;});
    assert(result.good && result.rows==16384); fclose(file);
    file=fixture(many(16385));
    result=scan(file,[](const Mapping&){return Visit::Continue;});
    assert(!result.good && result.rows==16385); fclose(file);
    file=fixture("1000-2000 r--p " + std::string(511*32769,'x') + "\n");
    result=scan(file,[](const Mapping&){return Visit::Continue;});
    assert(!result.good && result.chunks==32769); fclose(file);
    // Consumer capacities and visitor rejection stay fixed.
    static_assert(Snapshot::LIMIT==8192);
    file=fixture(many(9000)); size_t ranges=0;
    result=scan(file,[&](const Mapping& m){if(m.readable && ++ranges>4096)return Visit::Reject;return Visit::Continue;});
    assert(!result.good && ranges==4097); fclose(file);
    Snapshot missing("/does-not-exist/monitor-maps"); assert(!missing.valid && !missing.contains(1, 1));
    assert(current_snapshot == nullptr);
    {
        Scope outer; const Snapshot* saved = current_snapshot; assert(saved == &outer.snapshot && saved->valid);
        bool other_thread_empty = false;
        std::thread thread([&] { other_thread_empty = current_snapshot == nullptr; Scope own; assert(current_snapshot == &own.snapshot); });
        thread.join(); assert(other_thread_empty && current_snapshot == saved);
        { Scope inner; assert(current_snapshot == &inner.snapshot && current_snapshot != saved); }
        assert(current_snapshot == saved);
    }
    assert(current_snapshot == nullptr);
    const size_t page = size_t(sysconf(_SC_PAGESIZE));
    void* mapped = mmap(nullptr, page * 2, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(mapped != MAP_FAILED);
    { Scope scope; assert(scope.snapshot.contains(uintptr_t(mapped), 1, true)); }
    assert(mprotect(mapped, page * 2, PROT_READ) == 0);
    { Scope scope; assert(scope.snapshot.contains(uintptr_t(mapped), 1, false) && !scope.snapshot.contains(uintptr_t(mapped), 1, true)); }
    assert(mprotect(mapped, page, PROT_NONE) == 0);
    { Scope scope; assert(!scope.snapshot.contains(uintptr_t(mapped), 1, false)); }
    assert(munmap(mapped, page * 2) == 0 && current_snapshot == nullptr);
}
