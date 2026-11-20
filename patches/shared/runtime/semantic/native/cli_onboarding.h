#pragma once
#include "onboarding_pins.h"

bool onboarding_pins() {
    for (const auto& pin : CLI_ONBOARDING_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    return true;
}
bool onboarding_reaches(Reader& h, Address child, Address parent) {
    Address seen[16] = {};
    for (Size i = 0; i < 16 && child; ++i) {
        if (child == parent) return true;
        if (!h.readable(child, 0x1c2) || h.get<unsigned char>(child + 0x1c0) != 1
            || h.get<unsigned char>(child + 0x1c1) != 1) return false;
        for (Size j = 0; j < i; ++j) if (seen[j] == child) return false;
        seen[i] = child; child = h.get<Address>(child + 0x148);
    }
    return false;
}
bool onboarding_callback(Reader& h, Address closure, Address type, Address owner, Address invoke) {
    Address actual = 0;
    return h.readable(closure, 16) && h.get<Address>(closure) == module.base + type
        && h.get<Address>(closure + 8) == owner
        && static_pointer(module.base + type + 0x30, &actual) && actual == module.base + invoke && !h.fault;
}
// Only the three ordinary onboarding callbacks proved against this exact core.
bool onboarding_button(Reader& h, Address dialog, bool secondary, bool single,
    Address inner_type, Address owner, Address invoke, CliUiAction& action) {
    if (!h.readable(dialog, 0x350) || h.get<Address>(dialog) != module.base + 0x1af8480
        || h.get<unsigned char>(dialog + 0x1c0) != 1 || h.get<unsigned char>(dialog + 0x1c1) != 1
        || h.get<unsigned char>(dialog + 0x301) != unsigned(single)
        || h.get<unsigned char>(dialog + 0x302) != 0 || h.get<unsigned char>(dialog + 0x340) != 1) return false;
    const Size field = single ? 0x330 : secondary ? 0x328 : 0x320;
    const Address node = h.get<Address>(dialog + field);
    if (!h.readable(node, 0x449) || h.get<Address>(node) != module.base + 0x1a8ece0
        || h.get<unsigned char>(node + 0x1c0) != 1 || h.get<unsigned char>(node + 0x1c1) != 1
        || h.get<unsigned char>(node + 0x312) != 1 || h.get<unsigned char>(node + 0x314) != 1
        || h.get<unsigned char>(node + 0x448) != 0 || !onboarding_reaches(h, node, dialog)
        || !ui_name(h, node, single ? "button3" : secondary ? "button2" : "button1")
        || h.get<Address>(node + 0x398) || h.get<Address>(node + 0x3a0) || h.get<Address>(node + 0x3a8)
        || h.get<Address>(node + 0x3d0)) return false;
    const Address closure = h.get<Address>(node + 0x400);
    const Address type = single ? 0x1b1a2d8 : secondary ? 0x1ac34b0 : 0x1b4aec8;
    const Address wrapper_invoke = single ? 0x9ad6f4 : secondary ? 0x11b1d84 : 0x1411494;
    Address actual = 0;
    if (!h.readable(closure, 0x48) || h.get<Address>(closure) != module.base + type
        || h.get<Address>(closure + 0x10) != dialog
        || !static_pointer(module.base + type + 0x30, &actual) || actual != module.base + wrapper_invoke
        || !onboarding_callback(h, h.get<Address>(closure + 0x40), inner_type, owner, invoke)) return false;
    action.node = node; action.closure = closure;
    return !h.fault;
}
bool capture_onboarding(Reader& h, Address scene, const UiTree& tree, CliUiState& out) {
    if (!tree.valid || tree.loading || !onboarding_pins()) return false;
    Address panel = 0, dialogs[2] = {}; Size count = 0;
    for (Size i = 0; i < tree.inspected; ++i) {
        const Address node = tree.queue[i].node;
        if (h.get<unsigned char>(node + 0x1c1) != 1) continue;
        const Address vt = h.get<Address>(node); char klass[240] = {};
        if (!ui_class(vt, klass)) return false;
        if (vt == module.base + 0x1ac3640) {
            if (panel || h.get<unsigned char>(node + 0x1c0) != 1) return false;
            panel = node;
        } else if (vt == module.base + 0x1af8480) {
            if (count == 2) return false;
            dialogs[count++] = node;
        } else if (strstr(klass, "Dialog") || strstr(klass, "Overlay") || strstr(klass, "Popup")
            || strstr(klass, "Loading") || strstr(klass, "Transition")) return false;
    }
    if (panel && count == 0 && h.readable(panel, 0x330) && h.get<Address>(panel + 0x148) == scene
        && h.get<Address>(panel + 0x328) == scene + 0x2f8) {
        const Address close = h.get<Address>(panel + 0x2c8);
        if (!h.readable(close, 0x449) || h.get<Address>(close) != module.base + 0x1a8ece0
            || h.get<unsigned char>(close + 0x1c0) != 1 || h.get<unsigned char>(close + 0x1c1) != 1
            || h.get<unsigned char>(close + 0x312) != 1 || h.get<unsigned char>(close + 0x314) != 1
            || h.get<Address>(close + 0x3d0) || !onboarding_reaches(h, close, panel)) return false;
        const Address wrapper = h.get<Address>(close + 0x400);
        if (!h.readable(wrapper, 0x48) || h.get<Address>(wrapper) != module.base + 0x1b73478
            || h.get<Address>(wrapper + 0x10) != panel
            || !onboarding_callback(h, h.get<Address>(wrapper + 0x40), 0x1b3f6a8, scene + 0x2f8, 0x1620450)) return false;
        out.onboarding_settings_ready = true; out.identity.flags[4] = 1;
        return false;
    }
    CliUiAction action; Address target = 0, offset = 0, inner = 0;
    unsigned stage = 0;
    if (!panel && count == 1 && h.get<Address>(dialogs[0] + 0x148) == scene
        && onboarding_button(h, dialogs[0], false, true, 0x1b6e038, scene, 0x98ab54, action)) {
        target = dialogs[0]; stage = 1;
        action.name = "onboarding_setup"; action.label = "Setup"; out.onboarding_stage = "welcome";
    } else if (panel && count && h.readable(panel, 0x330) && h.get<Address>(panel + 0x148) == scene
        && h.get<Address>(panel + 0x328) == scene + 0x2f8) {
        Address calibration = 0;
        for (Size i = 0; i < count; ++i) {
            CliUiAction cancel;
            const Address node = h.get<Address>(dialogs[i] + 0x328);
            if (!h.readable(node, 0x408)) continue;
            const Address wrapper = h.get<Address>(node + 0x400);
            if (!h.readable(wrapper, 0x48)) continue;
            const Address callback = h.get<Address>(wrapper + 0x40);
            if (!h.readable(callback, 16)) continue;
            const Address owner = h.get<Address>(callback + 8);
            if (!h.readable(owner, 0x5f8) || h.get<Address>(owner) != module.base + 0x1ad4218
                || !onboarding_reaches(h, owner, panel) || h.get<unsigned char>(owner + 0x5d8) != 0
                || h.get<Address>(owner + 0x5e0) != h.get<Address>(owner + 0x5e8)
                || h.get<Address>(dialogs[i] + 0x148) != scene
                || !onboarding_button(h, dialogs[i], true, false, 0x1b31300, owner, 0x185aee4, cancel)) continue;
            if (calibration) return false;
            calibration = dialogs[i]; offset = owner; action = cancel;
        }
        if (!calibration) return false;
        if (count == 1) {
            target = calibration; stage = 2;
            action.name = "onboarding_cancel"; action.label = "Cancel offset setup"; out.onboarding_stage = "offset_setup";
        } else {
            const Address warning = dialogs[0] == calibration ? dialogs[1] : dialogs[0];
            if (h.get<Address>(warning + 0x148) != scene
                || !onboarding_button(h, warning, false, false, 0x1a99ce0, offset, 0x9ef864, action)) return false;
            inner = h.get<Address>(action.closure + 0x40);
            if (!h.readable(inner, 0x18) || h.get<Address>(inner + 0x10) != calibration) return false;
            target = warning; stage = 3;
            action.name = "onboarding_skip"; action.label = "Confirm skip offset setup"; out.onboarding_stage = "offset_skip_confirmation";
        }
    }
    bool ancestors_enabled = false;
    for (Size i = 0; i < tree.inspected; ++i)
        if (tree.queue[i].node == action.node && tree.queue[i].ancestors_enabled) ancestors_enabled = true;
    if (!stage || !ancestors_enabled || h.fault) { out.onboarding_stage = nullptr; return false; }
    out.actions[0] = action; out.action_count = 1; out.reason = nullptr;
    out.identity.modal = target; out.identity.modal_type = module.base + 0x1af8480;
    out.identity.flags[2] = stage; out.identity.nodes[2] = panel; out.identity.nodes[3] = offset;
    out.identity.callbacks[2] = h.get<Address>(action.closure + 0x40);
    out.identity.callbacks[3] = inner;
    return !h.fault;
}
