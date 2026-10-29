// Compile only after the root reviews the QA diagnostic source.
#include <assert.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <time.h>
#include <string>
#include <vector>
static uint64_t tick = 1;
static bool broken_clock = false;
static std::vector<std::string> logs;
static unsigned interval_reads = 0;
extern "C" int fixture_clock(clockid_t, timespec* value) {
    value->tv_sec = tick / 1000000000ULL;
    value->tv_nsec = tick % 1000000000ULL;
    return broken_clock ? -1 : 0;
}
extern "C" int __android_log_print(int, const char* tag, const char* format, ...) {
    assert(std::string(tag) == "AkaineMenuGeometry");
    char line[1024]; va_list args; va_start(args, format);
    vsnprintf(line, sizeof(line), format, args); va_end(args);
    logs.emplace_back(line); return 0;
}
#define clock_gettime fixture_clock
#include "menu_geometry_trace.h"
#undef clock_gettime
void reset() {
    using namespace menu_geometry;
    armed.store(false); used.store(false); foreign_thread.store(false);
    depth = sequence = errors = clock_errors = discarded = 0;
    warmup_end = window_begin = root_begin = group_begin = last_stamp = 0;
    costs[0] = {}; costs[1] = {}; pending_group = {}; invalid_root = false;
    tick = 1; broken_clock = false; logs.clear(); interval_reads = 0; interval_reader = nullptr;
}
menu_geometry::Interval fake_interval() noexcept { ++interval_reads; return {16666668, 0}; }
void* foreign_event(void*) { menu_geometry::event(1, 0); return nullptr; }
void root_call(uint64_t length, unsigned groups) {
    using namespace menu_geometry;
    event(1, 0);
    for (unsigned i = 0; i < groups; ++i) {
        tick += 1; event(2, 0); tick += 2; event(2, 1);
    }
    tick += length; event(1, 1);
}
int main() {
    using namespace menu_geometry;
    event(1, 0); event(1, 1); assert(logs.empty());
    arm(); interval_reader = &fake_interval; root_call(1, 1); assert(!depth && !costs[0].count);
    tick = warmup_end; root_call(10, 3);
    assert(costs[0].count == 1 && costs[0].sum == 19);
    assert(costs[1].count == 3 && costs[1].sum == 6 && logs.empty() && interval_reads == 0);
    tick += WINDOW_NS; root_call(10, 0);
    assert(logs.size() == 1 && logs[0].find("valid=1") != std::string::npos);
    assert(logs[0].find("c1=2") != std::string::npos && logs[0].find("c2=3") != std::string::npos);
    assert(interval_reads == 1 && logs[0].find("requested_interval_ns=16666668") != std::string::npos);
    reset(); arm(); tick = warmup_end;
    event(1, 0); event(2, 0); tick += 1; event(2, 1); // Missing outer RET.
    tick += 2; event(1, 0); assert(costs[1].count == 0 && discarded == 1);
    tick += WINDOW_NS; event(1, 1);
    assert(logs.size() == 1 && logs[0].find("valid=0") != std::string::npos && !armed.load());
    reset(); arm(); tick = warmup_end;
    pthread_t thread; assert(pthread_create(&thread, nullptr, foreign_event, nullptr) == 0);
    assert(pthread_join(thread, nullptr) == 0 && foreign_thread.load()); root_call(WINDOW_NS, 1);
    assert(logs[0].find("valid=0") != std::string::npos && !armed.load());
    reset(); arm(); tick = warmup_end; event(1, 0); broken_clock = true; event(2, 0);
    broken_clock = false; tick += WINDOW_NS; event(1, 1);
    assert(logs[0].find("valid=0") != std::string::npos && logs[0].find("c1=0") != std::string::npos);
    reset(); arm(); tick = warmup_end; const uint64_t first = tick; event(1, 0);
    tick = first + 100; event(2, 0); tick = first + 110; event(2, 1);
    tick = first + 50; event(1, 1);
    assert(logs.size() == 1 && logs[0].find("valid=0") != std::string::npos && !armed.load());
    reset(); arm(); tick = warmup_end; event(2, 0); event(2, 1);
    assert(!depth && !costs[1].count && logs.empty());
    reset(); arm(); tick = warmup_end;
    for (unsigned i = 0; i < MAX_WINDOWS; ++i) { root_call(WINDOW_NS, 1); tick += 1; }
    assert(logs.size() == MAX_WINDOWS && !armed.load()); arm(); assert(!armed.load());
    puts("PASS bounded aggregate, nesting, lost RET, clock rejection, outside-group silence and no rearm");
}
