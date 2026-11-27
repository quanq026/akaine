constexpr Address GAME_SCENE_VTABLE = 0x1bf4d50;
struct OfficialHost {
    Address base = module.base;
    bool fault = false;
    template<class T> T get(Address address) {
        T value = {};
        if (fault || !process_readable(address, sizeof(T))) fault = true;
        else memcpy(&value, reinterpret_cast<const void*>(address), sizeof(T));
        return value;
    }
    template<class T> void put(Address address, T value) {
        if (fault || !process_readable(address, sizeof(T), true)) fault = true;
        else memcpy(reinterpret_cast<void*>(address), &value, sizeof(T));
    }
    template<class R, class... Args> R call(Address va, Args... args) {
        if (fault || va > ~Address(0) - base
            || !in_ranges(module.executable, module.executable_count, base + va, 4)) {
            fault = true;
            if constexpr (!std::is_void_v<R>) return R{};
            else return;
        }
        return reinterpret_cast<R (*)(Args...)>(base + va)(args...);
    }
    Address song_id_string(Address scene) { return get<Address>(scene + 0x318); }
    Address makeNode(unsigned size, Address vtable) {
        if (size < 0x300 || size > 0x3a0 || !module_readable(base + vtable, 0x568)) {
            fault = true;
            return 0;
        }
        Address node = call<Address>(0x1b05b60, Address(size));
        if (!node || !process_readable(node, size, true)) { fault = true; return 0; }
        memset(reinterpret_cast<void*>(node), 0, size);
        call<void>(0x123e18c, node);
        put<Address>(node, base + vtable);
        call<Address>(0x19204d0, node);
        return fault ? 0 : node;
    }
    void schedule(Address object, Address closure_vtable, Address capture) {
        if (!object || object != capture) { fault = true; return; }
        Address destroy = 0;
        if (!static_pointer(base + closure_vtable + 0x20, &destroy)
            || !in_ranges(module.executable, module.executable_count, destroy, 4)) {
            fault = true;
            return;
        }
        alignas(16) Address closure[5] = {base + closure_vtable, capture, 0, 0, 0};
        closure[4] = Address(closure);
        call<void>(0x172ea58, Address(closure));
        // Native std::function copies the capture; dispose only its stack wrapper.
        reinterpret_cast<void (*)(Address)>(destroy)(Address(closure));
    }
};

struct OfficialActor {
    Address modifier = 0, scene = 0;
    const akaine_official::OfficialProfile* profile = nullptr;
    bool init_done = false, failed = false;
};
OfficialActor official_actors[16] = {};
Size official_actor_count = 0;

bool actor_matches(const OfficialActor& a) {
    if (!a.modifier || !a.scene || !a.profile
        || !process_readable(a.modifier, a.profile->size, true)
        || !process_readable(a.scene, 0x338)) return false;
    Address vt = 0, scene_vt = 0;
    memcpy(&vt, reinterpret_cast<const void*>(a.modifier), sizeof(vt));
    memcpy(&scene_vt, reinterpret_cast<const void*>(a.scene), sizeof(scene_vt));
    return vt == module.base + a.profile->vtable && scene_vt == module.base + GAME_SCENE_VTABLE;
}

OfficialActor* registered_official_actor(Address modifier) {
    for (Size i = 0; i < official_actor_count; ++i)
        if (official_actors[i].modifier == modifier) return &official_actors[i];
    return nullptr;
}

akaine_official::CallbackPolicy official_callback_policy(OfficialActor* actor, const char* phase) {
    const bool ready = official_thread();
    const bool identity = actor && ready && actor_matches(*actor);
    const auto policy = akaine_official::callbackPolicy(actor != nullptr, ready, identity);
    if (policy == akaine_official::CallbackPolicy::Denied)
        __android_log_print(ANDROID_LOG_ERROR, TAG,
            "official_replay_callback song_id=%s phase=%s status=blocked reason=state_thread_or_identity",
            actor->profile->song, phase);
    return policy;
}

void clear_official_actors() {
    official_mailbox->active_last = 0;
    official_mailbox->is_last = 0;
    official_mailbox->scoped_tag = 0;
    official_mailbox->scoped_actor = 0;
    official_mailbox->failed_actor = 0;
    OfficialHost h;
    for (Size i = 0; i < official_actor_count; ++i) {
        auto& actor = official_actors[i];
        if (actor.modifier && actor.profile && process_readable(actor.modifier, actor.profile->size)) {
            Address vt = h.get<Address>(actor.modifier);
            if (vt == module.base + actor.profile->vtable) h.call<void>(0x10c1aa0, actor.modifier);
        }
        if (actor.scene && process_readable(actor.scene, sizeof(Address))
            && h.get<Address>(actor.scene) == module.base + GAME_SCENE_VTABLE)
            h.call<void>(0x10c1aa0, actor.scene);
        actor = {};
    }
    official_actor_count = 0;
}

bool permitted_official_scene(Address scene, char* song) {
    OfficialHost h;
    if (!process_readable(scene, 0x338, true)
        || h.get<Address>(scene) != module.base + GAME_SCENE_VTABLE
        || h.get<uint32_t>(scene + 0x310) != 0) return false;
    Address context_owner = 0;
    if (!static_pointer(module.base + 0x1c92968, &context_owner)) return false;
    Address suppression = h.get<Address>(context_owner + 0xb0);
    if (!suppression || h.get<uint8_t>(suppression + 8) != 0 || h.fault) return false;
    return song_id(h.song_id_string(scene), song, 65);
}

void official_factory(Address scene) {
    monitor_maps::Scope mappings;
    OfficialHost h;
    if (!official_thread()) { h.call<void>(0xa45a34, scene); return; }
    const unsigned finale_intent = unsigned(official_mailbox->pending_finale);
    official_mailbox->pending_finale = 0;
    clear_official_actors();
    char song[65] = {};
    if (!permitted_official_scene(scene, song)) { h.call<void>(0xa45a34, scene); return; }
    const auto* profile = akaine_official::officialProfile(song);
    if (!profile) { h.call<void>(0xa45a34, scene); return; }
    bool enabled = official_mailbox->disabled == 0;
    Address existing = h.get<Address>(scene + 0x308);
    if (existing) {
        if (!process_readable(existing, 0x2bc, true)
            || h.get<Address>(existing) != module.base + profile->vtable
            || akaine_official::preserveStoryModifier(*profile, h.get<uint32_t>(existing + 0x2b8), enabled, finale_intent)) {
            __android_log_print(ANDROID_LOG_INFO, TAG,
                "official_replay_profile song_id=%s status=skipped reason=existing_story_or_foreign_modifier", song);
            h.call<void>(0xa45a34, scene);
            return;
        }
    }
    if (!enabled) {
        if (akaine_official::mandatoryGameplay(*profile)) h.call<void>(0xa45a34, scene);
        else {
            if (existing) {
                h.put<Address>(scene + 0x308, 0);
                h.call<void>(0x10c1aa0, existing);
            }
        }
        __android_log_print(ANDROID_LOG_INFO, TAG,
            "official_replay_profile song_id=%s status=disabled mandatory_gameplay=%d", song,
            akaine_official::mandatoryGameplay(*profile) ? 1 : 0);
        return;
    }
    __android_log_print(ANDROID_LOG_INFO, TAG,
        "official_replay_profile song_id=%s status=selected family=%u difficulty=%u",
        song, unsigned(profile->family), h.get<uint32_t>(scene + 0x320));
    Address modifier = akaine_official::createOfficial(*profile, scene, h);
    if (!modifier || h.fault || !process_readable(modifier, profile->size, true)
        || h.get<Address>(modifier) != module.base + profile->vtable || official_actor_count == 16) {
        __android_log_print(ANDROID_LOG_ERROR, TAG,
            "official_replay_profile song_id=%s status=skipped reason=creation_or_identity_guard", song);
        return;
    }
    h.put<Address>(scene + 0x308, modifier);
    h.call<void>(0x12e63ec, modifier);
    h.call<void>(0x12e63ec, scene);
    if (existing) h.call<void>(0x10c1aa0, existing);
    // This extra reference protects captured Last callbacks through the ending UI.
    h.call<void>(0x12e63ec, modifier);
    official_actors[official_actor_count++] = {modifier, scene, profile, false, false};
    if (akaine_official::isLastProfile(*profile)) {
        official_mailbox->active_last = modifier;
        official_mailbox->is_last = 1;
    }
    __android_log_print(ANDROID_LOG_INFO, TAG,
        "official_replay_profile song_id=%s status=applied result_type=0 runtime_verified=false", song);
}

void fail_official_actor(OfficialActor& actor, const char* reason) {
    actor.init_done = true;
    actor.failed = true;
    official_mailbox->failed_actor = actor.modifier;
    OfficialHost safe;
    const auto& p = *actor.profile;
    if (p.family == akaine_official::Family::Modern) {
        if (p.variant == 0) safe.put<uint32_t>(actor.modifier + 0x2f4, 0);
        else if (p.variant == 1) safe.put<uint32_t>(actor.modifier + 0x2f8, 0);
        else if (p.variant == 2) safe.put<uint32_t>(actor.modifier + 0x330, 0);
        else safe.put<uint8_t>(actor.modifier + 0x2f4, 0);
    }
    __android_log_print(ANDROID_LOG_ERROR, TAG,
        "official_replay_init song_id=%s status=failed reason=%s", p.song, reason);
}

bool target_song_ready(Address scene, Address scope, OfficialHost& h) {
    if (scope != 1 && scope != 2) return true;
    const uint32_t diff = h.get<uint32_t>(scene + 0x320);
    if (h.fault || diff > 2) return false;
    Address context_owner = 0;
    if (!static_pointer(module.base + 0x1c92968, &context_owner) || !context_owner) return false;
    const Address song_repo = h.get<Address>(context_owner + 0x20);
    const Address dm = h.get<Address>(context_owner + 0x58);
    if (h.fault || !song_repo || !dm) return false;
    struct ShortString {
        uint8_t tag;
        char buf[23];
    } ss = {};
    static_assert(sizeof(ShortString) == 24);
    const char* target = (scope == 1) ? "grievouslady" : "fractureray";
    const size_t len = (scope == 1) ? 12 : 11;
    ss.tag = static_cast<uint8_t>(len << 1);
    memcpy(ss.buf, target, len + 1);
    const Address target_song = h.call<Address>(0xc9ccd4, song_repo, reinterpret_cast<Address>(&ss));
    if (h.fault || !target_song) return false;
    const uint32_t status = h.call<uint32_t>(0x1a3a2bc, dm, target_song, diff, uint32_t(0));
    return !h.fault && status == 0;
}

uint32_t official_init(Address modifier, Address original) {
    OfficialHost h;
    auto* actor = registered_official_actor(modifier);
    RetainedScope access(actor ? actor->modifier : 0, actor ? actor->profile->size : 0, actor ? actor->scene : 0);
    const auto policy = official_callback_policy(actor, "init");
    if (policy == akaine_official::CallbackPolicy::Native) return h.call<uint32_t>(original - module.base, modifier);
    if (policy == akaine_official::CallbackPolicy::Denied) {
        if (official_mailbox) official_mailbox->failed_actor = modifier;
        return 0;
    }
    if (original != module.base + actor->profile->init
        || h.get<Address>(modifier + 0x2a0) != actor->scene) {
        fail_official_actor(*actor, "target_or_bound_scene_identity");
        return 0;
    }
    Address scope = 0;
    if (actor->profile->family == akaine_official::Family::Legacy)
        scope = official32::legacy::initScope(static_cast<official32::legacy::Profile>(actor->profile->variant));
    if ((scope == 1 || scope == 2) && !target_song_ready(actor->scene, scope, h)) {
        fail_official_actor(*actor, "missing_target_song_files");
        return 0;
    }
    const Address previous_tag = official_mailbox->scoped_tag, previous_actor = official_mailbox->scoped_actor;
    official_mailbox->scoped_actor = modifier;
    official_mailbox->scoped_tag = scope;
    bool ok = akaine_official::initOfficial(*actor->profile, modifier, h);
    official_mailbox->scoped_tag = previous_tag;
    official_mailbox->scoped_actor = previous_actor;
    actor->init_done = true;
    actor->failed = !ok || h.fault;
    if (actor->failed) {
        fail_official_actor(*actor, h.fault ? "read_write_or_call_bounds" : "native_initializer_returned_false");
        return 0;
    }
    __android_log_print(ANDROID_LOG_INFO, TAG,
        "official_replay_init song_id=%s status=ready", actor->profile->song);
    return 1;
}

uint64_t official_update(Address modifier, Address scene, Address original) {
    OfficialHost h;
    auto* actor = registered_official_actor(modifier);
    RetainedScope access(actor ? actor->modifier : 0, actor ? actor->profile->size : 0, actor ? actor->scene : 0);
    const auto policy = official_callback_policy(actor, "update");
    if (policy == akaine_official::CallbackPolicy::Native) return h.call<uint64_t>(original - module.base, modifier, scene);
    if (policy == akaine_official::CallbackPolicy::Denied) return 0;
    if (actor->failed || !actor->init_done || original != module.base + actor->profile->update || scene != actor->scene) return 0;
    const auto profile = *actor->profile;
    h.call<void>(0x12e63ec, modifier);
    auto result = h.call<uint64_t>(original - module.base, modifier, scene);
    if (!(profile.family == akaine_official::Family::Legacy && profile.variant == 5))
        h.put<uint32_t>(modifier + 0x2b8, 0);
    h.call<void>(0x10c1aa0, modifier);
    return result;
}

uint64_t official_finish(Address modifier, Address callback, uint32_t failed, Address original) {
    OfficialHost h;
    auto* actor = registered_official_actor(modifier);
    RetainedScope access(actor ? actor->modifier : 0, actor ? actor->profile->size : 0, actor ? actor->scene : 0);
    const auto policy = official_callback_policy(actor, "finish");
    if (policy == akaine_official::CallbackPolicy::Native) return h.call<uint64_t>(original - module.base, modifier, callback, failed);
    if (policy == akaine_official::CallbackPolicy::Denied) return 0;
    if (actor->failed || !actor->init_done || original != module.base + actor->profile->finish) return 0;
    const auto profile = *actor->profile;
    h.call<void>(0x12e63ec, modifier);
    auto result = akaine_official::finishOfficial(profile, modifier, callback, failed, h);
    h.call<void>(0x10c1aa0, modifier);
    return result;
}

uint64_t official_progress(Address arg0, Address arg1, Address arg2, Address arg3, Address modifier, uint32_t op) {
    OfficialHost h;
    auto* actor = registered_official_actor(modifier);
    RetainedScope access(actor ? actor->modifier : 0, actor ? actor->profile->size : 0, actor ? actor->scene : 0);
    if (official_callback_policy(actor, "progress") == akaine_official::CallbackPolicy::Denied) return 0;
    if (actor && akaine_official::skipLastProgress(actor->profile, true, actor->failed, op)) {
        __android_log_print(ANDROID_LOG_INFO, TAG,
            "official_replay_progress song_id=%s operation=%u status=skipped", actor->profile->song, op);
        return 0;
    }
    const Address original = akaine_official::progressOriginal(op);
    return original ? h.call<uint64_t>(original, arg0, arg1, arg2, arg3) : 0;
}

bool initialize_official_bridge() {
    if (!official_thread()) return false;
    for (const auto& profile : akaine_official::official_profiles) {
        const Address expected[] = {profile.init, profile.update, profile.finish};
        const Address slots[] = {0x4d8, 0x508, 0x510};
        for (Size i = 0; i < 3; ++i) {
            Address actual = 0;
            if (!static_pointer(module.base + profile.vtable + slots[i], &actual)
                || actual != module.base + expected[i]) return false;
        }
    }
    official_mailbox->factory = Address(&official_factory);
    official_mailbox->init = Address(&official_init);
    official_mailbox->update = Address(&official_update);
    official_mailbox->finish = Address(&official_finish);
    official_mailbox->progress = Address(&official_progress);
    __android_log_print(ANDROID_LOG_INFO, TAG,
        "official_replay_bridge status=ready profiles=32 runtime_all_verified=false");
    return true;
}
