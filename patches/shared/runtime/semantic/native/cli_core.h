#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string.h>

namespace akaine_cli {
constexpr size_t REQUEST_LIMIT = 512;
constexpr size_t ID_CAPACITY = 4096;
struct Request {
    char id[33] = {}, session[33] = {}, command[24] = {};
    char argument[257] = {};
    uint64_t expires = 0;
    int section = 0;
};
inline bool action_name(const char* text, size_t n) {
    constexpr const char* names[] = {"start_continue", "main_music", "pack_open", "pack_hint_continue", "main_hint_continue", "notification_hint_continue", "onboarding_setup", "onboarding_cancel", "onboarding_skip"};
    for (const char* name : names) if (strlen(name) == n && !memcmp(text, name, n)) return true;
    return false;
}
inline bool identifier(const char* text, size_t n) {
    if (!n || n > 64) return false;
    for (size_t i = 0; i < n; ++i) {
        const char c = text[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
              (c >= '0' && c <= '9') || c == '_' || c == '-')) return false;
    }
    return true;
}
inline bool decimal(const char* text, size_t n, unsigned maximum) {
    if (!n || n > 4 || (n > 1 && text[0] == '0')) return false;
    unsigned value = 0;
    for (size_t i = 0; i < n; ++i) {
        if (text[i] < '0' || text[i] > '9') return false;
        value = value * 10 + unsigned(text[i] - '0');
    }
    return value <= maximum;
}
inline bool action_token(const char* text, size_t n) {
    if (n < 18 || n > 64) return false;
    const size_t dot = n - 17;
    if (text[dot] != '.' || !action_name(text, dot)) return false;
    for (size_t i = 0; i < dot; ++i) if (!((text[i] >= 'a' && text[i] <= 'z') || text[i] == '_')) return false;
    for (size_t i = dot + 1; i < n; ++i)
        if (!((text[i] >= '0' && text[i] <= '9') || (text[i] >= 'a' && text[i] <= 'f'))) return false;
    return true;
}
inline bool hex_id(const char* value, size_t n) {
    if (n != 32) return false;
    for (size_t i = 0; i < n; ++i)
        if (!((value[i] >= '0' && value[i] <= '9') || (value[i] >= 'a' && value[i] <= 'f'))) return false;
    return true;
}
inline bool filter_argument(const char* text, size_t n) {
    if ((n == 6 && !memcmp(text, "status", 6)) || (n == 4 && !memcmp(text, "open", 4))
        || (n == 5 && (!memcmp(text, "close", 5) || !memcmp(text, "reset", 5)))) return true;
    if (n <= 6 || n > 177 || memcmp(text, "query:", 6) || (n - 6) % 4 == 1) return false;
    for (size_t i = 6; i < n; ++i) {
        const char c = text[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '-')) return false;
    }
    return true;
}
inline bool settings_argument(const char* text, size_t n) {
    if (n == 5 && !memcmp(text, "fps:", 4)) return text[4] == '0' || text[4] == '1';
    if ((n == 6 && !memcmp(text, "status", 6)) || (n == 4 && !memcmp(text, "open", 4))
        || (n == 5 && !memcmp(text, "close", 5))) return true;
    if (n > 6 && !memcmp(text, "speed:", 6)) {
        if (!decimal(text + 6, n - 6, 65)) return false;
        return n == 8; // Native note speed uses integer tenths, 10..65.
    }
    if (n <= 7 || memcmp(text, "offset:", 7)) return false;
    const bool negative = text[7] == '-';
    const size_t start = negative ? 8 : 7;
    return decimal(text + start, n - start, 2000)
        && (!negative || (n > start && text[start] != '0'));
}
inline bool parse(const char* bytes, size_t n, Request* output) {
    if (!output || n == 0 || n > REQUEST_LIMIT || bytes[n - 1] != '\n') return false;
    size_t at = 0, start[6] = {}, length[6] = {};
    for (size_t i = 0; i < 6; ++i) {
        start[i] = at;
        while (at < n - 1 && bytes[at] != ' ') {
            if (bytes[at] < 33 || bytes[at] > 126) return false;
            ++at;
        }
        length[i] = at - start[i];
        if (!length[i] || (i < 5 && (at >= n - 1 || bytes[at++] != ' '))) return false;
    }
    if (at != n - 1 || length[0] != 6 || memcmp(bytes, "AKCLI1", 6)
        || !hex_id(bytes + start[1], length[1]) || !hex_id(bytes + start[2], length[2])
        || length[3] > 20) return false;
    Request result;
    memcpy(result.id, bytes + start[1], 32);
    memcpy(result.session, bytes + start[2], 32);
    for (size_t i = 0; i < length[3]; ++i) {
        const char ch = bytes[start[3] + i];
        if (ch < '0' || ch > '9' || result.expires > (UINT64_MAX - unsigned(ch - '0')) / 10) return false;
        result.expires = result.expires * 10 + unsigned(ch - '0');
    }
    if (length[4] == 6 && !memcmp(bytes + start[4], "status", 6)
        && length[5] == 4 && !memcmp(bytes + start[5], "none", 4)) memcpy(result.command, "status", 7);
    else if (length[4] == 8 && !memcmp(bytes + start[4], "category", 8)
        && length[5] == 1 && (bytes[start[5]] == '7' || bytes[start[5]] == '8')) {
        memcpy(result.command, "category", 9);
        result.section = bytes[start[5]] - '0';
    } else if (length[4] == 2 && !memcmp(bytes + start[4], "ui", 2)
        && ((length[5] == 4 && !memcmp(bytes + start[5], "list", 4)) || action_token(bytes + start[5], length[5]))) {
        memcpy(result.command, "ui", 3);
        memcpy(result.argument, bytes + start[5], length[5]);
    } else {
        const char* command = bytes + start[4];
        const char* argument = bytes + start[5];
        const size_t cn = length[4], an = length[5];
        const bool song = cn == 11 && !memcmp(command, "song_select", 11) && identifier(argument, an);
        const bool pack = cn == 11 && !memcmp(command, "pack_select", 11) && identifier(argument, an);
        const bool pack_close = cn == 10 && !memcmp(command, "pack_close", 10) && an == 4 && !memcmp(argument, "none", 4);
        const bool difficulty = cn == 10 && !memcmp(command, "difficulty", 10) && decimal(argument, an, 4);
        const bool sort = cn == 4 && !memcmp(command, "sort", 4) && decimal(argument, an, 5);
        const bool group = cn == 5 && !memcmp(command, "group", 5) && decimal(argument, an, 5);
        const bool reverse = cn == 7 && !memcmp(command, "reverse", 7) && decimal(argument, an, 1);
        const bool replay = cn == 6 && !memcmp(command, "replay", 6) && decimal(argument, an, 1);
        const bool play = cn == 4 && !memcmp(command, "play", 4) && identifier(argument, an);
        const bool play_download = cn == 13 && !memcmp(command, "play_download", 13) && identifier(argument, an);
        const bool play_guide = cn == 10 && !memcmp(command, "play_guide", 10) && identifier(argument, an);
        const bool play_set_speed = cn == 14 && !memcmp(command, "play_set_speed", 14) && identifier(argument, an);
        const bool character = cn == 9 && !memcmp(command, "character", 9) &&
            ((an == 4 && (!memcmp(argument, "list", 4) || !memcmp(argument, "open", 4))) ||
             (an == 6 && !memcmp(argument, "status", 6)) || (an == 5 && !memcmp(argument, "close", 5)) || decimal(argument, an, 9999));
        const bool account = cn == 7 && !memcmp(command, "account", 7) &&
            ((an == 6 && !memcmp(argument, "status", 6)) || (an == 4 && !memcmp(argument, "open", 4)) ||
             (an == 10 && !memcmp(argument, "login_open", 10)) || (an == 12 && !memcmp(argument, "terms_accept", 12))
             || (an == 4 && !memcmp(argument, "fill", 4)) || (an == 6 && !memcmp(argument, "submit", 6))
                || (an == 15 && !memcmp(argument, "management_open", 15)) || (an == 6 && !memcmp(argument, "logout", 6)));
        const bool sync = cn == 4 && !memcmp(command, "sync", 4) &&
            ((an == 6 && !memcmp(argument, "status", 6)) || (an == 8 && !memcmp(argument, "download", 8)));
        const bool filter = cn == 6 && !memcmp(command, "filter", 6) && filter_argument(argument, an);
        const bool navigation = cn == 10 && !memcmp(command, "navigation", 10) &&
            ((an == 6 && !memcmp(argument, "status", 6)) || (an == 4 && !memcmp(argument, "back", 4))
             || (an == 8 && !memcmp(argument, "continue", 8)) || (an == 5 && !memcmp(argument, "retry", 5)));
        const bool gameplay = cn == 8 && !memcmp(command, "gameplay", 8) &&
            ((an == 6 && (!memcmp(argument, "status", 6) || !memcmp(argument, "resume", 6)))
             || (an == 5 && (!memcmp(argument, "pause", 5) || !memcmp(argument, "retry", 5)))
             || (an == 4 && !memcmp(argument, "quit", 4)));
        const bool skill = cn == 5 && !memcmp(command, "skill", 5) && an == 6
            && (!memcmp(argument, "status", 6) || (!memcmp(argument, "seal:", 5) && (argument[5] == '0' || argument[5] == '1')));
        const bool bundle = cn == 6 && !memcmp(command, "bundle", 6) &&
            ((an == 6 && !memcmp(argument, "status", 6)) || (an == 7 && !memcmp(argument, "confirm", 7))
             || (an == 13 && !memcmp(argument, "dismiss-error", 13)));
        const bool settings = cn == 8 && !memcmp(command, "settings", 8) && settings_argument(argument, an);
        if (!(song || pack || pack_close || difficulty || sort || group || reverse || replay || play || play_download || play_guide || play_set_speed || character || account || sync || filter || navigation || gameplay || skill || settings || bundle)) return false;
        if (cn >= sizeof(result.command) || an >= sizeof(result.argument)) return false;
        memcpy(result.command, command, cn); memcpy(result.argument, argument, an);
    }
    *output = result;
    return true;
}
inline const char* request_guard(const Request& request, const char* session, uint64_t now) {
    if (strcmp(request.session, session)) return "WRONG_SESSION";
    if (!now || request.expires <= now) return "EXPIRED";
    if (request.expires - now > 30000) return "INVALID_EXPIRY";
    return nullptr;
}
struct Ledger {
    char ids[ID_CAPACITY][33] = {};
    size_t count = 0;
    const char* remember(const char* id) {
        for (size_t i = 0; i < count; ++i) if (!strcmp(ids[i], id)) return "DUPLICATE";
        if (count == ID_CAPACITY) return "SESSION_LIMIT";
        memcpy(ids[count++], id, 33);
        return nullptr;
    }
};
inline bool section_ordinal(int section, int ordinal) {
    return (section == 7 && ordinal == 4) || (section == 8 && ordinal == 5);
}
inline bool six_stops(const float* values, size_t count) {
    constexpr float expected[] = {-2395, -1905, -1415, -925, -435, 55};
    if (count != 6) return false;
    for (size_t i = 0; i < 6; ++i) if (values[i] != expected[i]) return false;
    return true;
}
// Fixed output buffer; fail closed on overflow. All non-ASCII bytes are escaped.
struct Json {
    char data[16384] = {};
    size_t used = 0;
    bool good = true;
    void unicode(unsigned code) {
        char escape[7] = {'\\', 'u', "0123456789abcdef"[(code >> 12) & 15],
            "0123456789abcdef"[(code >> 8) & 15], "0123456789abcdef"[(code >> 4) & 15],
            "0123456789abcdef"[code & 15], 0};
        add(escape);
    }
    void add(const char* text) {
        size_t n = strlen(text);
        if (!good || n >= sizeof(data) - used) { good = false; return; }
        memcpy(data + used, text, n + 1); used += n;
    }
    void string(const char* text) {
        add("\"");
        for (size_t i = 0; text[i]; ++i) {
            unsigned char ch = static_cast<unsigned char>(text[i]);
            if (ch >= 0xc2 && ch <= 0xf4) {
                const size_t tails = ch < 0xe0 ? 1 : ch < 0xf0 ? 2 : 3;
                unsigned code = ch & (tails == 1 ? 0x1f : tails == 2 ? 0xf : 7);
                bool valid = true;
                for (size_t j = 1; j <= tails; ++j) {
                    const unsigned char next = static_cast<unsigned char>(text[i + j]);
                    if ((next & 0xc0) != 0x80) { valid = false; break; }
                    code = (code << 6) | (next & 0x3f);
                }
                if (valid && code >= (tails == 1 ? 0x80u : tails == 2 ? 0x800u : 0x10000u)
                    && code <= 0x10ffff && (code < 0xd800 || code > 0xdfff)) {
                    if (code <= 0xffff) unicode(code);
                    else { code -= 0x10000; unicode(0xd800 + (code >> 10)); unicode(0xdc00 + (code & 0x3ff)); }
                    i += tails;
                    continue;
                }
            }
            char one[2] = {char(ch), 0};
            char escape[7] = {'\\', 'u', '0', '0', "0123456789abcdef"[ch >> 4], "0123456789abcdef"[ch & 15], 0};
            if (ch == '"') add("\\\"");
            else if (ch == '\\') add("\\\\");
            else if (ch < 32 || ch > 126) add(escape);
            else add(one);
        }
        add("\"");
    }
};
}
