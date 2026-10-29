#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <type_traits>
#include <vector>
#include <map>
#include <string>
#include <new>
#include "../semantic/native/cli_core.h"
#include "../semantic/native/cli_files.h"
using Address = uintptr_t;
using Size = size_t;
struct Range { Address start, end; };
struct CliPin { Address address; const unsigned char* bytes; Size size; };
struct Module { Address base; Range executable[1]; Size executable_count = 1; } module;
std::vector<Range> ranges;
std::vector<void*> owned_allocations;
std::map<Address, Address> pointers;
bool owner_thread = true;
bool dispatch_allowed = true;
unsigned releases = 0, deleted_wiped_temporaries = 0, native_calls = 0;
Address released_button = 0;
bool in_ranges(const Range* input, Size count, Address address, Size size) {
    for (Size i = 0; i < count; ++i)
        if (address >= input[i].start && address <= input[i].end && size <= input[i].end - address) return true;
    return false;
}
bool process_readable(Address address, Size size, bool = false) { return in_ranges(ranges.data(), ranges.size(), address, size); }
bool same_bytes(const unsigned char* a, const unsigned char* b, Size size) { return !memcmp(a, b, size); }
bool static_pointer(Address address, Address* output) {
    const auto it = pointers.find(address);
    if (it == pointers.end()) return false;
    *output = it->second; return true;
}
bool official_thread() { return owner_thread; }
bool cli_dispatch_allowed() { return dispatch_allowed; }
void* allocation(Size size) {
    void* p = calloc(1, size); assert(p); ranges.push_back({Address(p), Address(p) + size}); owned_allocations.push_back(p); return p;
}
template<class T> void put(Address node, Size offset, T value) { memcpy(reinterpret_cast<void*>(node + offset), &value, sizeof(value)); }
struct Reader {
    bool fault = false;
    bool readable(Address address, Size size) const { return process_readable(address, size); }
    template<class T> T get(Address address) {
        T out{}; if (!readable(address, sizeof(T))) fault = true;
        else memcpy(&out, reinterpret_cast<const void*>(address), sizeof(out));
        return out;
    }
};
struct UiTree {
    struct Item { Address node, parent; bool ancestors_enabled; } queue[32]{};
    Size count = 0;
    bool valid = true, loading = false, has_modal = false;
    Address modal = 0;
    void add(Address node, Address parent = 0, bool enabled = true) { queue[count++] = {node, parent, enabled}; }
};
struct alignas(8) ModString { unsigned char bytes[24]{}; };
std::string string_value(Address object) {
    Reader r;
    const unsigned char tag = r.get<unsigned char>(object);
    const Size size = tag & 1 ? r.get<Size>(object + 8) : Size(tag >> 1);
    const Address bytes = tag & 1 ? r.get<Address>(object + 16) : object + 1;
    assert(!r.fault && process_readable(bytes, size + 1));
    return std::string(reinterpret_cast<const char*>(bytes), size);
}
void make_string(Address object, const char* text) {
    if (!process_readable(object, 24)) ranges.push_back({object, object + 24});
    const Size size = strlen(text); memset(reinterpret_cast<void*>(object), 0, 24);
    if (size <= 22) { put<unsigned char>(object, 0, static_cast<unsigned char>(size * 2)); memcpy(reinterpret_cast<void*>(object + 1), text, size + 1); }
    else { const Size capacity = (size + 16) & ~Size(15); Address data = Address(allocation(capacity)); memcpy(reinterpret_cast<void*>(data), text, size + 1);
        put<Size>(object, 0, capacity | 1); put<Size>(object, 8, size); put<Address>(object, 16, data); }
}
std::map<Address, Size> clipping;
struct OfficialHost {
    bool fault = false;
    template<class R, class... Args> R call(Address va, Args... args) {
        ++native_calls;
        const Address values[] = {Address(args)...}; Address result = 0;
        if (va == 0xf66c9c) { ++releases; released_button = values[0]; }
        else if (va == 0x1a6dba0) make_string(values[0], reinterpret_cast<const char*>(values[1]));
        else if (va == 0x120e99c) {
            Reader r; const Address renderer = r.get<Address>(values[0] + 0x488);
            std::string text = string_value(values[1]);
            if (clipping.count(values[0]) && text.size() > clipping[values[0]]) text.resize(clipping[values[0]]);
            make_string(renderer + 0x720, text.c_str());
        } else if (va == 0xe160e0) { Reader r; result = r.get<Address>(values[0] + 0x488) + 0x720; }
        else if (va == 0x1a6d9e0) {
            const Address data = values[0]; bool found = false;
            for (const Range& range : ranges) if (range.start == data) {
                for (Address i = range.start; i < range.end; ++i) assert(*reinterpret_cast<unsigned char*>(i) == 0);
                found = true; break;
            }
            assert(found); ++deleted_wiped_temporaries;
        } else { assert(false && "unexpected native function"); }
        if constexpr (!std::is_void_v<R>) return R(result);
    }
};
void mod_destroy_string(OfficialHost& host, ModString& value) {
    if (value.bytes[0] & 1) { Address p = 0; memcpy(&p, value.bytes + 16, 8); host.call<void>(0x1a6d9e0, p); }
}
bool ui_name(Reader&, Address node, const char* expected) { return string_value(node + 0x160) == expected; }
bool ui_class(Address vt, char (&output)[240]) {
    const char* name = vt == module.base + 0x1b503d8 ? "15SideDialogLayer"
        : vt == module.base + 0x11111 ? "14LoadingOverlay" : "N7cocos2d4NodeE";
    strcpy(output, name); return true;
}
#include "../semantic/account/account_adapter.h"
int credential_test_directory = -1;
unsigned credential_reads_unlinked = 0;
ssize_t credential_fixture_read(int fd, void* bytes, size_t size) {
    struct stat st{};
    assert(fstatat(credential_test_directory, "credential", &st, AT_SYMLINK_NOFOLLOW) == -1 && errno == ENOENT);
    assert(fstatat(credential_test_directory, "credential.inflight", &st, AT_SYMLINK_NOFOLLOW) == -1 && errno == ENOENT);
    ++credential_reads_unlinked; return ::read(fd, bytes, size);
}
#define read credential_fixture_read
#include "../semantic/account/account_credentials.h"
#undef read
void credential_fixtures();
void logout_fixtures();

Address node(Address vt, const char* name = "", Size size = 0x500) {
    const Address p = Address(allocation(size)); put<Address>(p, 0, module.base + vt);
    put<unsigned char>(p, 0x1c0, 1); put<unsigned char>(p, 0x1c1, 1);
    put<unsigned char>(p, 0x312, 1); put<unsigned char>(p, 0x314, 1);
    make_string(p + 0x160, name); return p;
}
Address closure(Address vt, Size size = 0x60) { const Address p = Address(allocation(size)); put<Address>(p, 0, module.base + vt); return p; }
void bind(Address button, Address closure_address) { put<Address>(button, 0x3d0, closure_address); }
void pointer(Address slot, Address target) { pointers[module.base + slot] = module.base + target; }
int main() {
    credential_fixtures();
    module.base = Address(allocation(0x1c00000)); module.executable[0] = {module.base, module.base + 0x1c00000};
    for (const auto& pin : ACCOUNT_PINS) memcpy(reinterpret_cast<void*>(module.base + pin.address), pin.bytes, pin.size);
    for (const auto& pin : LOGOUT_PINS) memcpy(reinterpret_cast<void*>(module.base + pin.address), pin.bytes, pin.size);
    for (const auto& pin : LOGIN_ERROR_PINS) memcpy(reinterpret_cast<void*>(module.base + pin.address), pin.bytes, pin.size);
    pointer(0x1adae68 + 0x568, 0xb9acbc);
    pointer(0x1ad9788 + 0x30, 0x847f98); pointer(0x1b93718 + 0x30, 0xba307c);
    pointer(0x1a87cd8 + 0x30, 0xca27a8); pointer(0x1a8ece0 + 0x630, 0xf66c9c);
    pointer(0x1afa800 + 0x30, 0x18f81dc); pointer(0x1adb4c8 + 0x30, 0x96a884);
    pointer(0x1b4aec8 + 0x30, 0x1411494); pointer(0x1a99f50 + 0x30, 0xe25f24); pointer(0x1b7fb38 + 0x30, 0xb3e20c);
    pointer(0x1b6f640 + 0x30, 0x172fff8);
    pointer(0x1ac75b0 + 0x30, 0x11b6808); pointer(0x1adc920 + 0x30, 0x16e130c);
    pointer(0x1b95f58, 0x1bf23c0); pointer(0x1ae06a8 + 0x10, 0xac5bc0);
    pointer(0x1a8fba8 + 0x568, 0x1529c24); pointer(0x1a8fba8 + 0x560, 0x14e7ef4);
    pointer(0x1a8fba8 + 0x640, 0xe3a1e0); pointer(0x1a8fba8 + 0x668, 0x1378124);
    const Address context = Address(allocation(0x88)), online = Address(allocation(0x126));
    put<Address>(module.base, 0x1bf23c0, context); put<Address>(context, 0x80, online); put<Address>(online, 0, module.base + 0x1ae06a8);
    const Address scene = node(0x1b2e5a0), main = node(0x1b4d3e8), network = node(0x1a8ece0, "networkButton");
    put<Address>(scene, 0x328, main);
    const Address network_closure = closure(0x1ad9788); put<Address>(network_closure, 8, scene); bind(network, network_closure);
    UiTree tree; tree.add(scene); tree.add(main, scene); tree.add(network, main);
    Reader r;
    auto state = account_controls::inspect(r, scene, tree);
    assert(state.can_open && state.signed_in_known && !state.signed_in);
    assert(account_controls::open(r, scene, tree) == account_controls::Result::ok && releases == 1 && released_button == network);
    dispatch_allowed = false;
    unsigned before_dispatch = native_calls;
    assert(account_controls::open(r, scene, tree) == account_controls::Result::blocked && native_calls == before_dispatch);
    dispatch_allowed = true;
    owner_thread = false;
    assert(account_controls::open(r, scene, tree) == account_controls::Result::blocked && releases == 1); owner_thread = true;
    put<unsigned char>(online, 0x124, 1); state = account_controls::inspect(r, scene, tree); assert(state.signed_in);
    put<unsigned char>(online, 0x124, 2); state = account_controls::inspect(r, scene, tree); assert(!state.signed_in_known);
    put<unsigned char>(online, 0x124, 0);
    tree.queue[2].parent = scene; assert(!account_controls::inspect(r, scene, tree).can_open); tree.queue[2].parent = main;
    const Address modal = node(0x1b503d8), root = node(0x1b4d3e8), login = node(0x1a8ece0, "login_button");
    put<Address>(modal, 0x2d8, root); tree.has_modal = true; tree.modal = modal; tree.add(modal, scene); tree.add(root, modal); tree.add(login, root);
    const Address login_closure = closure(0x1b93718); bind(login, login_closure);
    put<Address>(login_closure, 8, modal); put<Address>(login_closure, 0x10, scene); put<Address>(login_closure, 0x18, scene + 0x308);
    state = account_controls::inspect(r, scene, tree); assert(state.can_login_open && !state.can_open);
    assert(account_controls::login_open(r, scene, tree) == account_controls::Result::ok && releases == 2);
    const Address logged_in = node(0x1b2d7b0), logged_content = node(0x1b4d3e8);
    const Address sync_button = node(0x1a8ece0, "sync_button"), sync_closure = closure(0x1b6f640);
    put<Address>(logged_in, 0x2a8, logged_content); put<Address>(sync_closure, 8, logged_in); bind(sync_button, sync_closure);
    put<Address>(modal, 0x2d8, logged_in); put<unsigned char>(online, 0x124, 1);
    UiTree logged_tree; logged_tree.has_modal = true; logged_tree.modal = modal;
    logged_tree.add(scene); logged_tree.add(main, scene); logged_tree.add(modal, scene);
    logged_tree.add(logged_in, modal); logged_tree.add(logged_content, logged_in); logged_tree.add(sync_button, logged_content);
    assert(!strcmp(account_controls::inspect(r, scene, logged_tree).kind, "logged_in_menu"));
    put<Address>(sync_closure, 8, modal);
    assert(strcmp(account_controls::inspect(r, scene, logged_tree).kind, "logged_in_menu"));
    put<Address>(sync_closure, 8, logged_in); logged_tree.queue[4].parent = main;
    assert(strcmp(account_controls::inspect(r, scene, logged_tree).kind, "logged_in_menu"));
    put<Address>(modal, 0x2d8, root); put<unsigned char>(online, 0x124, 0);
    tree.count = 5;
    const Address username = node(0x1aea538, "username_field"), password = node(0x1aea538, "password_field");
    const Address submit = node(0x1a8ece0, "confirm_button"), submit_closure = closure(0x1a87cd8);
    for (Address field : {username, password}) { const Address renderer = Address(allocation(0x7b0)); put<Address>(renderer, 0, module.base + 0x1a8fba8); put<Address>(field, 0x488, renderer); }
    bind(submit, submit_closure); put<Address>(submit_closure, 8, modal); put<Address>(submit_closure, 0x18, scene);
    put<Address>(submit_closure, 0x20, scene + 0x308); put<Address>(submit_closure, 0x30, password);
    put<Address>(submit_closure, 0x38, username); put<Address>(submit_closure, 0x40, submit);
    tree.add(username, root); tree.add(password, root); tree.add(submit, root);
    state = account_controls::inspect(r, scene, tree); assert(state.can_fill && state.can_submit);
    const Address error_label=node(0x1a98ce0,"error_text"), error_renderer=node(0x1adae68,"",0x400);
    put<Address>(error_label,0x148,root); put<Address>(error_label,0x4b8,error_renderer);tree.add(error_label,root);
    make_string(error_renderer+0x2d0,"");
    state=account_controls::inspect(r,scene,tree);assert(!state.error_code && !state.error_text);
    struct Error {const char* code;const char* text;};
    const Error errors[]={
        {"connection_failed","Could not connect to online server."},
        {"invalid_credentials","Username or password incorrect."},
        {"account_locked","This account is locked."},
        {"maintenance","The Arcaea network is currently under maintenance."},
        {"unknown_error","An unknown error has occurred."}};
    for (const auto& e:errors) {
        make_string(error_renderer+0x2d0,e.text);state=account_controls::inspect(r,scene,tree);
        assert(state.error_code && !strcmp(state.error_code,e.code) && !strcmp(state.error_text,e.text));
        assert(account_controls::known_login_error(state.error_code));
    }
    make_string(error_renderer+0x2d0,"PRIVATE_BANNER_SENTINEL_do_not_echo");
    state=account_controls::inspect(r,scene,tree);assert(!strcmp(state.error_code,"unrecognized")&&!state.error_text);
    akaine_cli::Json unknown_json;account_controls::write_state(unknown_json,state);
    assert(!strstr(unknown_json.data,"PRIVATE_BANNER_SENTINEL"));
    make_string(error_renderer+0x2d0,errors[0].text);
    put<unsigned char>(error_label,0x1c1,0);state=account_controls::inspect(r,scene,tree);assert(!state.error_code);put<unsigned char>(error_label,0x1c1,1);
    put<Address>(error_label,0x148,scene);state=account_controls::inspect(r,scene,tree);assert(!state.error_code);put<Address>(error_label,0x148,root);
    put<Address>(error_label,0,module.base+0x1aea538);state=account_controls::inspect(r,scene,tree);assert(!state.error_code);put<Address>(error_label,0,module.base+0x1a98ce0);
    put<Address>(error_renderer,0,module.base+0x1a8fba8);state=account_controls::inspect(r,scene,tree);assert(!state.error_code);put<Address>(error_renderer,0,module.base+0x1adae68);
    pointer(0x1adae68+0x568,0x1529c24);state=account_controls::inspect(r,scene,tree);assert(!state.error_code);pointer(0x1adae68+0x568,0xb9acbc);
    state=account_controls::inspect(r,scene,tree);assert(state.error_code);
    put<Address>(submit_closure,0x10,scene+0x388);
    account_controls::SubmitCycle cycle;
    cycle.observe_busy(r,state);assert(!cycle.observed_busy&&!cycle.failed(state)); // Old error alone never confirms.
    put<unsigned char>(submit,0x312,0);put<unsigned char>(submit,0x313,0);
    cycle.observe_busy(r,state);assert(cycle.observed_busy);
    auto fresh=state;fresh.can_submit=false;assert(!cycle.failed(fresh));
    put<unsigned char>(submit,0x312,1);put<unsigned char>(submit,0x313,1);
    fresh=account_controls::inspect(r,scene,tree);assert(cycle.failed(fresh));
    for (const char* code:{"unrecognized","unexpected", ""}) {auto bad=fresh;bad.error_code=code;assert(!cycle.failed(bad));}
    {auto bad=fresh;bad.root+=8;assert(!cycle.failed(bad));bad=fresh;bad.button+=8;assert(!cycle.failed(bad));
     bad=fresh;bad.closure+=8;assert(!cycle.failed(bad));bad=fresh;bad.scene+=8;assert(!cycle.failed(bad));bad=fresh;bad.modal+=8;assert(!cycle.failed(bad));}
    r.fault=true;cycle.observe_busy(r,state);assert(!cycle.observed_busy);r.fault=false;
    make_string(error_renderer+0x2d0,"");

    const char user[] = "one-time-fixture-name-long", pass[] = "not-a-real-password-fixture-long";
    dispatch_allowed = false; before_dispatch = native_calls;
    assert(account_controls::fill_login(r, scene, tree, user, strlen(user), pass, strlen(pass)) == account_controls::Result::blocked
        && native_calls == before_dispatch);
    dispatch_allowed = true;
    assert(account_controls::fill_login(r, scene, tree, user, strlen(user), pass, strlen(pass)) == account_controls::Result::ok);
    assert(deleted_wiped_temporaries == 2);
    akaine_cli::Json output; account_controls::write_state(output, account_controls::inspect(r, scene, tree));
    assert(!strstr(output.data, user) && !strstr(output.data, pass) && !strstr(output.data, "username") && !strstr(output.data, "password"));
    assert(account_controls::submit_login(r, scene, tree) == account_controls::Result::ok && releases == 3);
    clipping[password] = 2;
    assert(account_controls::fill_login(r, scene, tree, user, strlen(user), pass, strlen(pass)) == account_controls::Result::field_rejected);
    Reader readback; const Address user_text = readback.get<Address>(username + 0x488) + 0x720, pass_text = readback.get<Address>(password + 0x488) + 0x720;
    assert(string_value(user_text).empty() && string_value(pass_text).empty());
    put<Address>(submit_closure, 0x38, password); assert(!account_controls::inspect(r, scene, tree).can_fill); put<Address>(submit_closure, 0x38, username);
    const Address extra = node(0x11111); tree.add(extra, scene); assert(account_controls::inspect(r, scene, tree).blocked); --tree.count;
    const Address tos_dialog = node(0x1af8480), tos_content = node(0x1b4d3e8);
    const Address tos_link = node(0x1a8ece0, "button_tos"), privacy_link = node(0x1a8ece0, "button_privacy");
    const Address tos_closure = closure(0x1afa800), privacy_closure = closure(0x1adb4c8);
    put<unsigned char>(tos_dialog, 0x340, 1); put<Address>(tos_content, 0x148, tos_dialog);
    put<Address>(tos_link, 0x148, tos_content); put<Address>(privacy_link, 0x148, tos_content);
    bind(tos_link, tos_closure); bind(privacy_link, privacy_closure);
    put<Address>(tos_closure, 8, scene); put<Address>(privacy_closure, 8, scene);
    tree.add(tos_dialog, scene); tree.add(tos_content, tos_dialog); tree.add(tos_link, tos_content); tree.add(privacy_link, tos_content);
    state = account_controls::inspect(r, scene, tree);
    assert(!strcmp(state.kind, "login_terms_required") && state.blocked
        && !state.can_open && !state.can_login_open && !state.can_fill && !state.can_submit && !state.can_accept_terms);
    const unsigned before_terms_action = native_calls;
    assert(account_controls::login_open(r, scene, tree) == account_controls::Result::unavailable && native_calls == before_terms_action);
    put<Address>(privacy_closure, 8, modal);
    assert(strcmp(account_controls::inspect(r, scene, tree).kind, "login_terms_required"));
    put<Address>(privacy_closure, 8, scene);
    put<Address>(tos_content, 0x148, main);
    assert(strcmp(account_controls::inspect(r, scene, tree).kind, "login_terms_required"));
    put<Address>(tos_content, 0x148, tos_dialog);
    const Address agree_button = node(0x1a8ece0, "button1"), agree_outer = closure(0x1b4aec8);
    const Address agree_inner = closure(0x1a99f50), agree_continuation = closure(0x1b7fb38);
    put<Address>(tos_dialog, 0x308, tos_content); put<Address>(tos_dialog, 0x320, agree_button);
    put<Address>(agree_button, 0x148, tos_content); put<Address>(agree_button, 0x400, agree_outer);
    put<Address>(agree_outer, 0x10, tos_dialog); put<Address>(agree_outer, 0x40, agree_inner);
    put<Address>(agree_inner, 0x10, scene); put<Address>(agree_inner, 0x40, agree_continuation);
    put<Address>(agree_continuation, 8, modal); put<Address>(agree_continuation, 0x10, scene);
    tree.add(agree_button, tos_content); tree.add(login, root);
    state = account_controls::inspect(r, scene, tree);
    assert(!strcmp(state.kind, "login_terms_required") && state.can_accept_terms);
    const unsigned before_user_terms = native_calls;
    assert(account_controls::login_open(r, scene, tree) == account_controls::Result::unavailable && native_calls == before_user_terms);
    dispatch_allowed = false;
    assert(account_controls::accept_terms(r, scene, tree) == account_controls::Result::blocked && native_calls == before_user_terms);
    dispatch_allowed = true; owner_thread = false;
    assert(account_controls::accept_terms(r, scene, tree) == account_controls::Result::blocked && native_calls == before_user_terms);
    owner_thread = true;
    assert(account_controls::accept_terms(r, scene, tree) == account_controls::Result::ok && native_calls == before_user_terms + 1
        && released_button == agree_button);
    put<Address>(agree_inner, 0, module.base + 0x1b34d70);
    assert(!account_controls::inspect(r, scene, tree).can_accept_terms);
    assert(account_controls::accept_terms(r, scene, tree) == account_controls::Result::unavailable);
    put<Address>(agree_inner, 0, module.base + 0x1a99f50);
    put<Address>(agree_continuation, 0x10, modal); assert(!account_controls::inspect(r, scene, tree).can_accept_terms);
    put<Address>(agree_continuation, 0x10, scene);
    put<unsigned char>(tos_dialog, 0x302, 1); assert(!account_controls::inspect(r, scene, tree).can_accept_terms);
    put<unsigned char>(tos_dialog, 0x302, 0);
    bind(agree_button, tos_closure); assert(!account_controls::inspect(r, scene, tree).can_accept_terms);
    bind(agree_button, 0);
    tree.count -= 6;
    assert(account_controls::valid_input("abc", 3));
    assert(account_controls::valid_input("\xe6\x97\xa5", 3));
    assert(!account_controls::valid_input("", 0) && !account_controls::valid_input("a\nb", 3));
    assert(!account_controls::valid_input("\xc0\xaf", 2) && !account_controls::valid_input("\xed\xa0\x80", 3));
    assert(!account_controls::valid_input("\xf4\x90\x80\x80", 4) && !account_controls::valid_input("\xe6\x97", 2));
    logout_fixtures();
    unsigned char* pin_byte = reinterpret_cast<unsigned char*>(module.base + ACCOUNT_PINS[0].address); *pin_byte ^= 1;
    assert(!account_controls::pins() && account_controls::fill_login(r, scene, tree, user, strlen(user), pass, strlen(pass)) == account_controls::Result::pin_mismatch);
    puts("PASS account pins, native ownership, thread guards, login fields, clipping cleanup, UTF-8 and secret-free status fixtures");
    for (void* p : owned_allocations) free(p);
}

void logout_fixtures() {
    using namespace account_controls;
    for (const char* argument : {"management_open", "logout", "delete_account"}) {
        char bytes[256];
        const int length=snprintf(bytes,sizeof(bytes),"AKCLI1 0123456789abcdef0123456789abcdef 11111111111111111111111111111111 1800000000123 account %s\n",argument);
        akaine_cli::Request parsed;
        assert(length>0 && Size(length)<sizeof(bytes));
        assert(akaine_cli::parse(bytes,Size(length),&parsed)==(strcmp(argument,"delete_account")!=0));
    }
    Reader r;
    const Address online = r.get<Address>(r.get<Address>(module.base + 0x1bf23c0) + 0x80);
    put<unsigned char>(online, 0x124, 1);
    const Address scene = node(0x1b2e5a0), main = node(0x1b4d3e8), network = node(0x1b503d8);
    const Address owner = node(0x1b2d7b0), content = node(0x1b4d3e8);
    const Address sync = node(0x1a8ece0, "sync_button"), sync_callback = closure(0x1b6f640);
    const Address management_button = node(0x1a8ece0, "account_management_button"), management_callback = closure(0x1ac75b0);
    put<Address>(scene, 0x328, main); put<Address>(network, 0x2d8, owner);
    put<Address>(owner, 0x2a8, content); put<Address>(owner, 0x2b0, network);
    bind(sync, sync_callback); put<Address>(sync_callback, 8, owner);
    bind(management_button, management_callback); put<Address>(management_callback, 8, owner);
    UiTree tree; tree.has_modal = true; tree.modal = network;
    tree.add(scene); tree.add(main, scene); tree.add(network, scene); tree.add(owner, network);
    tree.add(content, owner); tree.add(sync, content); tree.add(management_button, content);
    auto state = inspect(r, scene, tree);
    assert(!strcmp(state.kind, "logged_in_menu") && state.can_management_open && !state.can_logout);
    put<unsigned char>(network, 0x308, 1); assert(!inspect(r, scene, tree).can_management_open); put<unsigned char>(network, 0x308, 0);
    const unsigned before = native_calls;
    assert(management_open(r, scene, tree) == Result::ok && native_calls == before + 1 && released_button == management_button);
    put<Address>(management_callback, 8, scene); assert(!inspect(r, scene, tree).can_management_open);
    put<Address>(management_callback, 8, owner);
    const Address dialog = node(0x1af8480), root = node(0x1b4d3e8), custom = node(0x1b4d3e8);
    const Address destructive_sibling = node(0x1a8ece0), logout_button = node(0x1a8ece0), logout_callback = closure(0x1adc920);
    put<Address>(dialog, 0x308, root); put<Address>(dialog, 0x318, custom);
    put<Address>(logout_callback, 8, owner); put<Address>(logout_callback, 0x10, destructive_sibling);
    put<Address>(logout_callback, 0x18, logout_button); put<Address>(logout_callback, 0x20, dialog); bind(logout_button, logout_callback);
    tree.add(dialog, scene); tree.add(root, dialog); tree.add(custom, root);
    tree.add(destructive_sibling, custom); tree.add(logout_button, custom);
    state = inspect(r, scene, tree);
    assert(!strcmp(state.kind, "account_management") && !state.blocked && state.can_logout && !state.can_management_open);
    put<unsigned char>(network, 0x308, 1); assert(!inspect(r, scene, tree).can_logout); put<unsigned char>(network, 0x308, 0);
    const unsigned before_logout = native_calls;
    dispatch_allowed = false; assert(logout(r, scene, tree) == Result::blocked && native_calls == before_logout);
    dispatch_allowed = true; owner_thread = false; assert(logout(r, scene, tree) == Result::blocked && native_calls == before_logout);
    owner_thread = true;
    assert(logout(r, scene, tree) == Result::ok && native_calls == before_logout + 1 && released_button == logout_button);
    for (Size offset : {Size(8), Size(0x10), Size(0x18), Size(0x20)}) {
        const Address saved = r.get<Address>(logout_callback + offset);
        put<Address>(logout_callback, offset, scene); assert(!inspect(r, scene, tree).can_logout);
        put<Address>(logout_callback, offset, saved);
    }
    for (Size offset : {Size(0x1c0), Size(0x1c1), Size(0x312), Size(0x314)}) {
        put<unsigned char>(logout_button, offset, 0); assert(!inspect(r, scene, tree).can_logout);
        put<unsigned char>(logout_button, offset, 1);
    }
    put<Address>(logout_callback, 0, module.base + 0x1b52da8); // Exact delete callback never accepted.
    assert(!inspect(r, scene, tree).can_logout); put<Address>(logout_callback, 0, module.base + 0x1adc920);
    put<Address>(logout_button, 0x400, management_callback); assert(!inspect(r, scene, tree).can_logout); put<Address>(logout_button, 0x400, 0);
    const Address duplicate = node(0x1a8ece0); bind(duplicate, logout_callback); tree.add(duplicate, custom);
    assert(!inspect(r, scene, tree).can_logout); --tree.count;
    const Address extra = node(0x11111); tree.add(extra, scene); assert(!inspect(r, scene, tree).can_logout); --tree.count;
    put<unsigned char>(dialog, 0x302, 1); assert(!inspect(r, scene, tree).can_logout); put<unsigned char>(dialog, 0x302, 0);
    put<unsigned char>(dialog, 0x340, 1); assert(!inspect(r, scene, tree).can_logout); put<unsigned char>(dialog, 0x340, 0);
    put<unsigned char>(online, 0x124, 2); assert(!inspect(r, scene, tree).can_logout); put<unsigned char>(online, 0x124, 1);
    pointers[module.base + 0x1adc920 + 0x30] = module.base + 0x15e2c10;
    assert(!inspect(r, scene, tree).can_logout); pointer(0x1adc920 + 0x30, 0x16e130c);
    auto* byte = reinterpret_cast<unsigned char*>(module.base + LOGOUT_PINS[0].address); *byte ^= 1;
    assert(logout(r, scene, tree) == Result::pin_mismatch); *byte ^= 1;
    assert(inspect(r, scene, tree).can_logout);
    // Logout confirms the native replacement scene, not the original management scene.
    AccountView fresh; fresh.kind = "main_menu"; fresh.signed_in_known = true;
    fresh.signed_in = false; fresh.blocked = false; fresh.can_open = true; fresh.scene = scene + 0x100000;
    assert(logout_confirmed(fresh, true, false, true, false));
    assert(!logout_confirmed(fresh, false, false, true, false));
    assert(!logout_confirmed(fresh, true, true, true, false));
    assert(!logout_confirmed(fresh, true, false, false, false));
    assert(!logout_confirmed(fresh, true, false, true, true));
    for (int variation=0; variation<5; ++variation) {
        auto bad=fresh;
        if (variation==0) bad.signed_in_known=false;
        if (variation==1) bad.signed_in=true;
        if (variation==2) bad.blocked=true;
        if (variation==3) bad.can_open=false;
        if (variation==4) bad.kind="account_management";
        assert(!logout_confirmed(bad,true,false,true,false));
    }
    puts("PASS logout exact management/button ownership, delete exclusion, duplicate, modal, flags, thread and dispatch guards");
}

void credential_fixtures() {
    using namespace account_controls;
    static_assert(!std::is_copy_constructible_v<CredentialBuffer>);
    akaine_cli::Request request;
    strcpy(request.id, "0123456789abcdef0123456789abcdef");
    strcpy(request.session, "abcdef0123456789abcdef0123456789");
    strcpy(request.command, "account"); strcpy(request.argument, "fill"); request.expires = 11000;
    const uint64_t now = 10000;
    std::vector<unsigned char> payload(CREDENTIAL_HEADER_SIZE);
    memcpy(payload.data(), "AKCRED1\n", 8); memcpy(payload.data() + 8, request.session, 32);
    memcpy(payload.data() + 40, request.id, 32); payload[72] = 4; payload[74] = 5;
    for (const char c : std::string("testdummy")) payload.push_back(static_cast<unsigned char>(c));
    CredentialBuffer output;
    assert(parse_credential(payload.data(), payload.size(), request, request.session, now, output) == CredentialResult::ok);
    assert(output.username_size == 4 && output.password_size == 5 && !strcmp(output.username, "test") && !strcmp(output.password, "dummy"));
    output.clear();
    const auto wiped = [&] {
        for (char c : output.username) assert(c == 0);
        for (char c : output.password) assert(c == 0);
        assert(!output.username_size && !output.password_size);
    };
    for (Size size = 0; size < payload.size(); ++size) {
        strcpy(output.password, "sentinel");
        assert(parse_credential(payload.data(), size, request, request.session, now, output) != CredentialResult::ok); wiped();
    }
    for (Size index : {Size(0), Size(8), Size(40), Size(73), Size(75), Size(80)}) {
        auto bad = payload; bad[index] = index == 80 ? 0 : static_cast<unsigned char>(bad[index] ^ 1);
        assert(parse_credential(bad.data(), bad.size(), request, request.session, now, output) != CredentialResult::ok); wiped();
    }
    assert(parse_credential(payload.data(), payload.size(), request, nullptr, now, output) == CredentialResult::rejected); wiped();
    assert(parse_credential(payload.data(), payload.size(), request, request.session, request.expires, output) == CredentialResult::expired); wiped();
    char temporary[] = "/tmp/akaine-credential-fixture-XXXXXX";
    assert(mkdtemp(temporary)); assert(chmod(temporary, 0700) == 0);
    credential_test_directory = open(temporary, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    assert(credential_test_directory >= 0);
    const auto write_payload = [&](const std::vector<unsigned char>& bytes, mode_t mode = 0600) {
        const int fd = openat(credential_test_directory, "credential", O_WRONLY | O_CREAT | O_EXCL, mode);
        assert(fd >= 0 && write(fd, bytes.data(), bytes.size()) == ssize_t(bytes.size())); close(fd);
    };
    const auto absent = [&] {
        struct stat st{};
        assert(fstatat(credential_test_directory, "credential", &st, AT_SYMLINK_NOFOLLOW) == -1 && errno == ENOENT);
        assert(fstatat(credential_test_directory, "credential.inflight", &st, AT_SYMLINK_NOFOLLOW) == -1 && errno == ENOENT);
    };
    assert(load_credential(credential_test_directory, request, request.session, now, output) == CredentialResult::missing); wiped();
    write_payload(payload);
    assert(load_credential(credential_test_directory, request, request.session, now, output) == CredentialResult::ok);
    assert(credential_reads_unlinked == 1 && !strcmp(output.password, "dummy")); absent(); output.clear(); wiped();
    write_payload(payload);
    assert(load_credential(credential_test_directory, request, request.session, request.expires, output) == CredentialResult::expired); absent(); wiped();
    auto wrong = payload; wrong[40] ^= 1; write_payload(wrong);
    assert(load_credential(credential_test_directory, request, request.session, now, output) == CredentialResult::rejected); absent(); wiped();
    std::vector<unsigned char> oversized(CREDENTIAL_FILE_LIMIT + 1, 'x'); write_payload(oversized);
    assert(load_credential(credential_test_directory, request, request.session, now, output) == CredentialResult::rejected); absent(); wiped();
    write_payload(payload, 0644);
    assert(load_credential(credential_test_directory, request, request.session, now, output) == CredentialResult::rejected); wiped();
    assert(unlinkat(credential_test_directory, "credential", 0) == 0);
    write_payload(payload); assert(linkat(credential_test_directory, "credential", credential_test_directory, "other", 0) == 0);
    assert(load_credential(credential_test_directory, request, request.session, now, output) == CredentialResult::rejected); wiped();
    assert(unlinkat(credential_test_directory, "credential", 0) == 0 && unlinkat(credential_test_directory, "other", 0) == 0);
    const int target = openat(credential_test_directory, "target", O_WRONLY | O_CREAT | O_EXCL, 0600); assert(target >= 0); close(target);
    assert(symlinkat("target", credential_test_directory, "credential") == 0);
    assert(load_credential(credential_test_directory, request, request.session, now, output) == CredentialResult::rejected); wiped();
    assert(unlinkat(credential_test_directory, "credential", 0) == 0 && unlinkat(credential_test_directory, "target", 0) == 0);
    assert(mkfifoat(credential_test_directory, "credential", 0600) == 0);
    assert(load_credential(credential_test_directory, request, request.session, now, output) == CredentialResult::rejected); wiped();
    assert(unlinkat(credential_test_directory, "credential", 0) == 0);
    write_payload(payload); assert(fchmod(credential_test_directory, 0755) == 0);
    assert(load_credential(credential_test_directory, request, request.session, now, output) == CredentialResult::rejected); wiped();
    assert(fchmod(credential_test_directory, 0700) == 0 && unlinkat(credential_test_directory, "credential", 0) == 0);
    close(credential_test_directory); credential_test_directory = -1; assert(rmdir(temporary) == 0);
    alignas(CredentialBytes) unsigned char raw_storage[sizeof(CredentialBytes)];
    auto* raw = new (raw_storage) CredentialBytes; memset(raw->data, 'x', sizeof(raw->data)); raw->~CredentialBytes();
    for (unsigned char c : raw_storage) assert(c == 0);
    alignas(CredentialBuffer) unsigned char output_storage[sizeof(CredentialBuffer)] = {};
    auto* ephemeral = new (output_storage) CredentialBuffer;
    memset(ephemeral->username, 'x', sizeof(ephemeral->username)); memset(ephemeral->password, 'y', sizeof(ephemeral->password));
    ephemeral->username_size = 64; ephemeral->password_size = 256; ephemeral->~CredentialBuffer();
    // Padding is not a credential; only the owned byte arrays and size fields are asserted.
    for (Size i = 0; i < 65 + 257; ++i) assert(output_storage[i] == 0);
    puts("PASS credentials exact binary framing, identity, expiry, UTF-8, metadata guards, unlink-before-read and buffer wiping fixtures");
}
