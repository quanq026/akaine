#pragma once
// Include inside staging_cli after account_adapter.h; native allocation/string ABIs only.
#include "cloudsync_pins.h"
namespace cloudsync_cli {
constexpr Size DATA_SIZE = 0xd8;
constexpr Size STRING_OFFSETS[] = {0x10, 0x28, 0x48, 0x60, 0x78, 0x90, 0xa8, 0xc0};
constexpr Size STRING_LIMIT = 8 * 1024 * 1024, TOTAL_LIMIT = 32 * 1024 * 1024;
enum class Result { ok, unavailable, busy, expired, fault, pin_mismatch };
struct alignas(8) NativeData { unsigned char bytes[DATA_SIZE] = {}; };
struct View { const char* phase = "unavailable"; int error_code = 0; bool has_error = false, can_download = false; };
struct State {
    pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
    uint64_t generation = 0, expires = 0;
    char request[33] = {}, session[33] = {};
    Address scene = 0, context = 0, online = 0, online_user = 0, manager = 0, userdata = 0;
    const char* phase = "unavailable";
    bool delivered = false, payload = false, has_error = false;
    int error = 0;
    NativeData data;
};
inline State state;
inline bool pins() {
    for (const auto& pin : CLOUDSYNC_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    return account_controls::pointer_pin(0x1ae06a8 + 0x110, 0x941134);
}
inline bool data_valid(Reader& h, Address address) {
    if (!h.readable(address, DATA_SIZE) || h.get<unsigned char>(address) > 1) return false;
    Size total = 0;
    for (Size offset : STRING_OFFSETS) {
        const Address text = address + offset;
        const unsigned char tag = h.get<unsigned char>(text);
        const Size size = tag & 1 ? h.get<Size>(text + 8) : Size(tag >> 1);
        const Address bytes = tag & 1 ? h.get<Address>(text + 16) : text + 1;
        if (size > STRING_LIMIT || size > TOTAL_LIMIT - total || (!(tag & 1) && size > 22)
            || !h.readable(bytes, size + 1) || h.get<unsigned char>(bytes + size) != 0) return false;
        if ((tag & 1) && ((h.get<Size>(text) & ~Size(1)) < size + 1)) return false;
        total += size;
    }
    return !h.fault;
}
inline void move_data(NativeData& to, Address from) {
    // Exact owning move emitted in native1354690: transfer headers, empty all source strings.
    memcpy(to.bytes, reinterpret_cast<const void*>(from), DATA_SIZE);
    for (Size offset : STRING_OFFSETS) memset(reinterpret_cast<void*>(from + offset), 0, 24);
}
inline void destroy_data(NativeData& value) {
    OfficialHost host;
    host.call<void>(0x96ddf8, Address(&value));
    account_controls::wipe(value.bytes, DATA_SIZE);
}
inline Address native_allocate(Size size) { OfficialHost host; return host.call<Address>(0x1a6d9c0, Address(size)); }
inline void native_delete(Address address) { OfficialHost host; host.call<void>(0x1a6d9e0, address); }
struct Callback { Address vtable = 0; uint64_t generation = 0; };
inline Address callback_vtable[11] = {};
inline pthread_once_t callback_once = PTHREAD_ONCE_INIT;
inline void callback_destroy(Callback*) {}
inline void callback_delete(Callback* self) { native_delete(Address(self)); }
inline Callback* callback_clone(const Callback* self) {
    Callback* result = reinterpret_cast<Callback*>(native_allocate(sizeof(Callback)));
    if (result) memcpy(result, self, sizeof(Callback));
    return result;
}
inline void callback_clone_into(const Callback* self, Callback* destination) { memcpy(destination, self, sizeof(Callback)); }
inline Address callback_target(Callback*, Address) { return 0; }
inline Address callback_type(Callback*) { return module.base + 0x1a9d6f8; } // native type_info<void>
inline void callback_invoke(Callback* self, const bool* success, const int* error, Address data) {
    Reader reader;
    const bool valid = self && success && error && reader.readable(Address(success), 1) && reader.readable(Address(error), 4);
    pthread_mutex_lock(&state.mutex);
    if (!valid || self->generation != state.generation || strcmp(state.phase, "fetching") || state.delivered) {
        pthread_mutex_unlock(&state.mutex); return;
    }
    state.delivered = true;
    state.error = *error;
    state.has_error = !*success;
    if (*success && data_valid(reader, data)) {
        move_data(state.data, data); state.payload = true;
    } else if (*success) { state.error = -1; state.has_error = true; }
    pthread_mutex_unlock(&state.mutex);
}
inline void initialize_callback_vtable() {
    callback_vtable[0] = 0; callback_vtable[1] = module.base + 0x1a9d6f8;
    callback_vtable[2] = Address(&callback_destroy); callback_vtable[3] = Address(&callback_delete);
    callback_vtable[4] = Address(&callback_clone); callback_vtable[5] = Address(&callback_clone_into);
    callback_vtable[6] = Address(&callback_destroy); callback_vtable[7] = Address(&callback_delete);
    callback_vtable[8] = Address(&callback_invoke); callback_vtable[9] = Address(&callback_target);
    callback_vtable[10] = Address(&callback_type);
}
struct alignas(16) NativeFunction {
    unsigned char bytes[48] = {};
    explicit NativeFunction(uint64_t generation) {
        const Callback callback{Address(callback_vtable + 2), generation};
        memcpy(bytes, &callback, sizeof(callback));
        const Address target = Address(bytes); memcpy(bytes + 0x20, &target, sizeof(target));
    }
};
static_assert(sizeof(NativeData) == 216 && sizeof(NativeFunction) == 48 && sizeof(Callback) == 16);
inline bool identities(Reader& h, Address scene, Address* context, Address* online, Address* user,
                       Address* manager, Address* userdata) {
    if (!h.readable(scene, 0x330) || h.get<Address>(scene) != module.base + 0x1b2e5a0
        || !account_controls::pointer_pin(0x1b95f58, 0x1bf23c0)) return false;
    *context = h.get<Address>(module.base + 0x1bf23c0);
    if (!h.readable(*context, 0x88)) return false;
    *online = h.get<Address>(*context + 0x80); *manager = h.get<Address>(*context + 0x50);
    *userdata = h.get<Address>(*context + 0x30);
    if (!h.readable(*online, 0x126) || h.get<Address>(*online) != module.base + 0x1ae06a8
        || h.get<unsigned char>(*online + 0x124) != 1 || h.get<unsigned char>(*online + 0x125) != 0
        || !h.readable(*manager, 0xf8) || !h.readable(*userdata, 0x118)) return false;
    *user = h.get<Address>(*online + 0xd0);
    return *user && h.readable(*user, 0x10) && !h.fault;
}
inline View inspect(Reader& h, Address scene, const UiTree& tree) {
    View view;
    const auto account = account_controls::inspect(h, scene, tree);
    Address context = 0, online = 0, user = 0, manager = 0, userdata = 0;
    const bool ready = pins() && tree.valid && !tree.loading && account.signed_in_known && account.signed_in
        && (!strcmp(account.kind, "main_menu") || !strcmp(account.kind, "logged_in_menu"))
        && identities(h, scene, &context, &online, &user, &manager, &userdata);
    pthread_mutex_lock(&state.mutex);
    view.phase = state.phase; view.error_code = state.error; view.has_error = state.has_error;
    const bool busy = !strcmp(state.phase, "fetching") || !strcmp(state.phase, "applying");
    view.can_download = ready && !busy;
    if (!strcmp(view.phase, "unavailable") && ready) view.phase = "ready";
    pthread_mutex_unlock(&state.mutex);
    return view;
}
inline void write_state(akaine_cli::Json& json, const View& view) {
    json.add("{\"phase\":"); json.string(view.phase);
    json.add(",\"error_code\":");
    if (view.has_error) { char number[24]; snprintf(number, sizeof(number), "%d", view.error_code); json.add(number); }
    else json.add("null");
    json.add(",\"download_only\":true,\"can_download\":"); json.add(view.can_download ? "true" : "false"); json.add("}");
}
inline Result download(Reader& h, Address scene, const UiTree& tree,
                       const akaine_cli::Request& request, const char* session, uint64_t now) {
    if (!official_thread() || !cli_dispatch_allowed()) return Result::expired;
    if (!pins()) return Result::pin_mismatch;
    if (akaine_cli::request_guard(request, session, now) || strcmp(request.command, "sync") || strcmp(request.argument, "download")) return Result::expired;
    if (!inspect(h, scene, tree).can_download) return Result::unavailable;
    Address context = 0, online = 0, user = 0, manager = 0, userdata = 0;
    if (!identities(h, scene, &context, &online, &user, &manager, &userdata)) return Result::unavailable;
    pthread_mutex_lock(&state.mutex);
    if (!strcmp(state.phase, "fetching") || !strcmp(state.phase, "applying") || state.payload) {
        pthread_mutex_unlock(&state.mutex); return Result::busy;
    }
    if (state.generation == UINT64_MAX) { pthread_mutex_unlock(&state.mutex); return Result::fault; }
    ++state.generation; state.phase = "fetching"; state.expires = request.expires;
    memcpy(state.request, request.id, 33); memcpy(state.session, session, 33);
    state.scene = scene; state.context = context; state.online = online; state.online_user = user;
    state.manager = manager; state.userdata = userdata;
    state.delivered = state.has_error = false; state.error = 0;
    const uint64_t generation = state.generation;
    pthread_mutex_unlock(&state.mutex);
    pthread_once(&callback_once, initialize_callback_vtable);
    NativeFunction callback(generation);
    OfficialHost host;
    if (!cli_dispatch_allowed()) { pthread_mutex_lock(&state.mutex); state.phase = "failed"; state.has_error = true; state.error = -1; pthread_mutex_unlock(&state.mutex); return Result::expired; }
    // This native entry invokes OnlineManager fetchSyncData only. Never performSync or server-save helpers.
    host.call<void>(0xc7fd80, manager, Address(&callback));
    if (host.fault) { pthread_mutex_lock(&state.mutex); state.phase = "failed"; state.has_error = true; state.error = -1; pthread_mutex_unlock(&state.mutex); return Result::fault; }
    return Result::ok;
}
inline void poll(Reader& h, Address scene, const akaine_cli::Request& active_request, const char* session, uint64_t now) {
    if (!official_thread()) return;
    NativeData payload;
    Address manager = 0; bool owned = false, apply = false;
    pthread_mutex_lock(&state.mutex);
    if (strcmp(state.phase, "fetching")) { pthread_mutex_unlock(&state.mutex); return; }
    Address context = 0, online = 0, user = 0, current_manager = 0, userdata = 0;
    const bool identity = session && !strcmp(state.session, session) && scene == state.scene
        && !strcmp(state.request, active_request.id) && !strcmp(active_request.session, state.session)
        && !strcmp(active_request.command, "sync") && !strcmp(active_request.argument, "download")
        && active_request.expires == state.expires
        && identities(h, scene, &context, &online, &user, &current_manager, &userdata)
        && context == state.context && online == state.online && user == state.online_user
        && current_manager == state.manager && userdata == state.userdata;
    const bool deadline = now && now < state.expires;
    if (!identity || !deadline || !pins()) {
        state.phase = "failed"; state.error = -1; state.has_error = true;
    } else if (!state.delivered) { pthread_mutex_unlock(&state.mutex); return; }
    else if (state.has_error || !state.payload) {
        state.phase = "failed";
        if (!state.has_error) { state.has_error = true; state.error = -1; }
    }
    else { state.phase = "applying"; manager = state.manager; apply = true; }
    if (state.payload) {
        move_data(payload, Address(&state.data)); state.payload = false; owned = true;
    }
    pthread_mutex_unlock(&state.mutex);
    int result = -1;
    Reader fresh;
    UiTree fresh_tree(fresh, scene, fresh.get<Address>(scene + 0x328), 0);
    const auto account = account_controls::inspect(fresh, scene, fresh_tree);
    Reader overlay_reader;
    const auto overlays = overlay_cli::capture(overlay_reader, scene, "13MainMenuScene");
    const bool ui_ready = fresh_tree.valid && !fresh_tree.loading && !fresh.fault
        && account.signed_in_known && account.signed_in && !account.blocked
        && (!strcmp(account.kind, "main_menu") || !strcmp(account.kind, "logged_in_menu"))
        && overlays.complete && !overlays.blocked && !overlay_reader.fault;
    if (apply && ui_ready && cli_dispatch_allowed() && data_valid(fresh, Address(&payload)) && pins()) {
        const unsigned char absent = payload.bytes[0];
        if (absent) result = 9905;
        else {
            OfficialHost host;
            // Native1354690 assigns these same eight strings to SyncManager's embedded SyncData.
            // One synchronous native commit: once cache assignment starts, finish restore without mid-commit cancellation.
            Address final_context = 0, final_online = 0, final_user = 0, final_manager = 0, final_userdata = 0;
            const bool final_identity = identities(fresh, scene, &final_context, &final_online, &final_user, &final_manager, &final_userdata)
                && final_context == context && final_online == online && final_user == user
                && final_manager == manager && final_userdata == userdata;
            if (final_identity && cli_dispatch_allowed()) {
                for (Size offset : STRING_OFFSETS)
                    host.call<void>(0x1a6db80, manager + 0x20 + offset, Address(payload.bytes + offset));
            } else host.fault = true;
            if (!host.fault) {
                memcpy(reinterpret_cast<void*>(manager + 0x20), payload.bytes, 16);
                memcpy(reinterpret_cast<void*>(manager + 0x60), payload.bytes + 0x40, 4);
                result = host.call<int>(0x13926fc, manager);
                // Native success returns only after local collection reload and1823f40 persistence.
                if (host.fault) result = -1;
            }
        }
    }
    if (owned) destroy_data(payload);
    pthread_mutex_lock(&state.mutex);
    if (!strcmp(state.phase, "applying")) {
        state.phase = result == 0 ? "success" : "failed";
        state.has_error = result != 0; state.error = result;
    }
    pthread_mutex_unlock(&state.mutex);
}
} // namespace cloudsync_cli
