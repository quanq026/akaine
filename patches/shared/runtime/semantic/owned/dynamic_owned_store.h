#pragma once
#include <algorithm>
#include <atomic>
#include <cstdint>
#include <limits>
#include <memory>
#include <mutex>
#include <new>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

namespace owned_packs {

struct Token {
    uintptr_t manager = 0;
    uint64_t epoch = 0;
    uint64_t catalog_generation = 0;
    explicit operator bool() const { return manager && epoch; }
    bool operator==(const Token& other) const {
        return manager == other.manager && epoch == other.epoch
            && catalog_generation == other.catalog_generation;
    }
};

class DynamicOwnedStore {
    struct Entry { uintptr_t pack; std::string id; };
    struct Snapshot {
        Token token;
        std::vector<Entry> ordered;
        std::unordered_set<uintptr_t> pointers;
        std::unordered_set<std::string> ids;
    };
    std::mutex mutation_;
    std::shared_ptr<Snapshot> building_;
    std::shared_ptr<const Snapshot> published_;
    uint64_t epoch_ = 0;
    std::atomic<bool> failed_{false};

    void clear_locked(bool failed) noexcept {
        std::atomic_store_explicit(&published_, std::shared_ptr<const Snapshot>{}, std::memory_order_release);
        building_.reset();
        failed_.store(failed, std::memory_order_release);
    }
    std::shared_ptr<const Snapshot> snapshot(Token token) const noexcept {
        auto value = std::atomic_load_explicit(&published_, std::memory_order_acquire);
        return value && value->token == token ? value : nullptr;
    }

public:
    DynamicOwnedStore() = default;
    DynamicOwnedStore(const DynamicOwnedStore&) = delete;
    DynamicOwnedStore& operator=(const DynamicOwnedStore&) = delete;

    Token begin(uintptr_t manager, uint64_t catalog_generation) {
        std::lock_guard<std::mutex> lock(mutation_);
        clear_locked(false);
        if (!manager || epoch_ == std::numeric_limits<uint64_t>::max()) {
            failed_.store(true, std::memory_order_release);
            return {};
        }
        Token token{manager, ++epoch_, catalog_generation};
        try {
            building_ = std::make_shared<Snapshot>();
            building_->token = token;
            return token;
        } catch (const std::bad_alloc&) {
            clear_locked(true);
            return {};
        }
    }

    // Initial native iteration preserves duplicates; reserved additions deduplicate by ID.
    bool append(Token token, uintptr_t pack, const std::string& id, bool reserved, bool* inserted = nullptr) {
        std::lock_guard<std::mutex> lock(mutation_);
        if (inserted) *inserted = false;
        if (!building_ || !(building_->token == token)) return false;
        if (!pack || id.empty()) {
            clear_locked(true);
            return false;
        }
        if (reserved && building_->ids.find(id) != building_->ids.end()) return true;
        try {
            building_->ordered.push_back({pack, id});
            building_->pointers.insert(pack);
            building_->ids.insert(id);
            if (inserted) *inserted = true;
            return true;
        } catch (const std::bad_alloc&) {
            clear_locked(true);
            return false;
        } catch (const std::length_error&) {
            clear_locked(true);
            return false;
        }
    }

    bool finish(Token token) {
        std::lock_guard<std::mutex> lock(mutation_);
        if (!building_ || !(building_->token == token)) return false;
        std::shared_ptr<const Snapshot> completed = building_;
        building_.reset();
        std::atomic_store_explicit(&published_, std::move(completed), std::memory_order_release);
        return true;
    }

    void invalidate() {
        std::lock_guard<std::mutex> lock(mutation_);
        clear_locked(false);
    }

    bool ready(Token token) const noexcept { return bool(snapshot(token)); }
    bool failed() const noexcept { return failed_.load(std::memory_order_acquire); }
    bool contains_pointer(Token token, uintptr_t pack) const noexcept {
        const auto value = snapshot(token);
        return value && (!pack || value->pointers.find(pack) != value->pointers.end());
    }
    bool contains_id(Token token, const std::string& id) const {
        const auto value = snapshot(token);
        return value && value->ids.find(id) != value->ids.end();
    }
    size_t size(Token token) const noexcept {
        const auto value = snapshot(token);
        return value ? value->ordered.size() : 0;
    }
    size_t legacy_shadow(Token token, uintptr_t* output, size_t capacity) const noexcept {
        const auto value = snapshot(token);
        if (!value || !output) return 0;
        const size_t count = std::min({size_t{64}, capacity, value->ordered.size()});
        for (size_t index = 0; index < count; ++index) output[index] = value->ordered[index].pack;
        return count;
    }
};
}
