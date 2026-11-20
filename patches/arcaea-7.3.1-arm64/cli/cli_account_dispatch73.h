struct alignas(8) ModString { unsigned char bytes[24]{}; };
static_assert(sizeof(ModString)==24);

bool process_readable(Address at,Size length,bool write) {
    return monitor_maps::Snapshot{}.contains(at,length,write);
}

#include "account_adapter73.h"
#include "account_credentials73.h"

account_controls::SubmitCycle pending_login_submit;

const char* account_error(account_controls::Result result) {
    using Result=account_controls::Result;
    switch (result) {
        case Result::ok: return nullptr;
        case Result::unavailable: return "ACCOUNT_UNAVAILABLE";
        case Result::blocked: return "ACCOUNT_BLOCKED";
        case Result::field_rejected: return "FIELD_REJECTED";
        default: return "NATIVE_GUARD";
    }
}

bool account_confirmed(const char* action,const account_controls::AccountView& account) {
    const char* kind=account.kind;
    if (!strcmp(action,"open")) return !account.blocked &&
        (!strcmp(kind,"logged_in_menu") || !strcmp(kind,"logged_out_menu"));
    if (!strcmp(action,"login_open")) return !strcmp(kind,"login_terms_required") ||
        (!account.blocked && !strcmp(kind,"login"));
    if (!strcmp(action,"terms_accept")) return !account.blocked && !strcmp(kind,"login");
    if (!strcmp(action,"submit")) return account.signed_in_known && account.signed_in;
    if (!strcmp(action,"management_open"))
        return !account.blocked && account.signed_in_known && account.signed_in &&
               account.can_logout && !strcmp(kind,"account_management");
    if (!strcmp(action,"logout"))
        return account_controls::logout_confirmed(account,true,false,true,false);
    return false;
}

const char* account_action(const Request& request,Reader& reader,Address scene,const UiTree& tree) {
    using namespace account_controls;
    const char* action=request.argument;
    if (!strcmp(action,"open")) return account_error(account_controls::open(reader,scene,tree));
    if (!strcmp(action,"login_open")) return account_error(login_open(reader,scene,tree));
    if (!strcmp(action,"terms_accept")) return account_error(accept_terms(reader,scene,tree));
    if (!strcmp(action,"submit")) return account_error(submit_login(reader,scene,tree,&pending_login_submit));
    if (!strcmp(action,"management_open")) return account_error(management_open(reader,scene,tree));
    if (!strcmp(action,"logout")) return account_error(logout(reader,scene,tree));
    if (strcmp(action,"fill")) return "INVALID_ARGUMENT";
    CredentialBuffer credential;
    if (load_credential(directory,request,session,clock_value(CLOCK_REALTIME,1000),credential)!=CredentialResult::ok)
        return "CREDENTIAL_REJECTED";
    if (!cli_dispatch_allowed()) return "EXPIRED";
    return account_error(fill_login(reader,scene,tree,credential.username,credential.username_size,
                                    credential.password,credential.password_size));
}
