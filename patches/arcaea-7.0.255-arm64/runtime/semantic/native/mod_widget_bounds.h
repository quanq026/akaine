#pragma once

static bool mod_extend_widget_bound(OfficialHost& h, Address scene) {
    const Address widget = h.get<Address>(scene + 0x338);
    if (h.fault || !process_readable(widget, 0x870, true)
        || h.get<Address>(widget) != module.base + 0x1b13b50) return false;
    const float maximum = h.get<float>(widget + 0x758);
    if (h.fault || (maximum != 0.0f && maximum != 55.0f)) return false;
    h.put<float>(widget + 0x758, 55.0f);
    h.put<unsigned char>(widget + 0x7e8, 1);
    return !h.fault;
}
