#pragma once
#include "news_latest10.h"
#include "../native/sampler_read_probe.h"
#include <android/log.h>
#include <pthread.h>
#include <string>
#include <unordered_map>

namespace news_limit {
using Address = uintptr_t;
inline Address base = 0;
inline pthread_t owner;
inline bool ready = false;
inline uint64_t sort_calls = 0, limited_calls = 0, fallback_calls = 0;
inline uint64_t last_total = 0, last_selected = 0;
constexpr Address MAILBOX = 0x1c031c0;

inline bool read(Address address, void* output, size_t size) {
    return sampler_probe::copy(address, output, size);
}
template<class T> bool field(Address object, Address offset, T* output) {
    return object && offset <= ~Address(0) - object && read(object + offset, output, sizeof(T));
}
inline bool bytes(Address address, void* output, size_t size) {
    if (!address || size > ~Address(0) - address) return false;
    auto* target = static_cast<unsigned char*>(output);
    for (size_t at = 0; at < size; at += sampler_probe::LIMIT) {
        const size_t count = std::min(sampler_probe::LIMIT, size - at);
        if (!read(address + at, target + at, count)) return false;
    }
    return true;
}
inline bool id(const unsigned char* raw, std::string* output) {
    size_t size = 0; Address pointer = 0;
    if (raw[0] & 1) {
        std::memcpy(&size, raw + 8, 8); std::memcpy(&pointer, raw + 16, 8);
        if (size > 128 || (size && !pointer)) return false;
        output->resize(size);
        if (size && !read(pointer, &(*output)[0], size)) return false;
    } else {
        size = raw[0] >> 1;
        if (size > 22) return false;
        output->assign(reinterpret_cast<const char*>(raw + 1), size);
    }
    for (unsigned char value : *output) if (value < 0x20 || value == 0x7f) return false;
    return output->find('\0') == std::string::npos;
}
inline bool catalog_dates(std::unordered_map<std::string, uint64_t>* songs,
                          std::unordered_map<std::string, uint64_t>* packs) {
    Address storage = 0, services = 0, manager = 0, bounds[3]{};
    if (!read(base + 0x1b95f58, &storage, 8) || storage != base + 0x1bf23c0
            || !read(storage, &services, 8) || !field(services, 0x20, &manager)
            || !manager || !read(manager, bounds, sizeof(bounds))) return false;
    const Address begin = bounds[0], end = bounds[1], capacity = bounds[2];
    if ((begin & 7) || end < begin || capacity < end || (end - begin) % 8 || (capacity - begin) % 8
            || (capacity - begin) / 8 > news_latest10::MAX_RECORDS) return false;
    const size_t count = (end - begin) / 8;
    std::vector<Address> entries(count);
    if (count && !bytes(begin, entries.data(), count * 8)) return false;
    for (Address entry : entries) {
        unsigned char raw[0x1c0]{};
        if (!entry || !read(entry, raw, sizeof(raw))) return false;
        std::string song, pack;
        if (!id(raw, &song) || song.empty()) return false;
        uint64_t date = 0; Address metadata = 0;
        std::memcpy(&date, raw + 0x1b8, 8); std::memcpy(&metadata, raw + 0x190, 8);
        const auto inserted = songs->emplace(song, date);
        if (!inserted.second && inserted.first->second != date) return false;
        if (metadata) {
            unsigned char pack_raw[24]{};
            if (!field(metadata, 8, &pack_raw) || !id(pack_raw, &pack)) return false;
            if (!pack.empty()) {
                auto found = packs->find(pack);
                if (found == packs->end()) packs->emplace(pack, date);
                else if (date > found->second) found->second = date;
            }
        }
    }
    return !songs->empty();
}
inline bool rank(Address begin, Address end, size_t* selected) {
    if (end < begin || (end - begin) % 56 || (end - begin) / 56 > news_latest10::MAX_RECORDS) return false;
    const size_t count = (end - begin) / 56;
    if (!begin && count) return false;
    std::vector<unsigned char> records(count * 56);
    if (count && !bytes(begin, records.data(), records.size())) return false;
    std::unordered_map<std::string, uint64_t> songs, packs;
    if (count && !catalog_dates(&songs, &packs)) return false;
    std::vector<uint64_t> dates; dates.reserve(count);
    for (size_t index = 0; index < count; ++index) {
        const auto* raw = records.data() + index * 56;
        uint32_t kind = 0; std::memcpy(&kind, raw, 4);
        std::string pack, song;
        if (!id(raw + 8, &pack) || !id(raw + 32, &song)) return false;
        if (kind == 0) {
            const auto found = songs.find(song);
            if (found == songs.end()) return false;
            dates.push_back(found->second);
        } else if (kind == 1 && song.empty()) {
            const auto found = packs.find(pack);
            if (found == packs.end()) return false;
            dates.push_back(found->second);
        } else return false;
    }
    // The native sorter just mutated this owner-GL span. Only whole owning records move.
    return news_latest10::reorder(reinterpret_cast<void*>(begin), reinterpret_cast<void*>(end), dates, selected);
}
inline void sort(Address begin, Address end, Address scratch) {
    const bool owned = ready && pthread_equal(owner, pthread_self());
    auto* fields = reinterpret_cast<Address*>(base + MAILBOX);
    if (owned) {
        __atomic_store_n(fields + 14, Address(0), __ATOMIC_RELEASE);
        fields[12] = fields[13] = 0;
    }
    // Preserve native sorting and exception propagation before any optional selection.
    reinterpret_cast<void(*)(Address, Address, Address)>(base + 0xac15c8)(begin, end, scratch);
    if (!owned) return;
    ++sort_calls;
    size_t selected = 0; bool ranked = false;
    try { ranked = rank(begin, end, &selected); } catch (...) { ranked = false; }
    if (!ranked) { ++fallback_calls; return; }
    fields[12] = begin; fields[13] = end;
    __atomic_store_n(fields + 14, begin + selected * 56, __ATOMIC_RELEASE);
    ++limited_calls; last_total = (end - begin) / 56; last_selected = selected;
    __android_log_print(ANDROID_LOG_INFO, "AkaineNewsLimit", "latest_news selected=%u total=%u",
                       unsigned(selected), unsigned(last_total));
}
inline bool initialize(Address module_base) {
    base = module_base; owner = pthread_self(); ready = sampler_probe::self_test().passed;
    auto* fields = reinterpret_cast<Address*>(base + MAILBOX);
    fields[12] = fields[13] = fields[14] = 0;
    fields[15] = reinterpret_cast<Address>(__builtin_thread_pointer());
    return ready;
}
} // namespace news_limit
