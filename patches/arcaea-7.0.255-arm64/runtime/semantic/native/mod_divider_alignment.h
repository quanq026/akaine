#pragma once

struct ModDividerPoint { float x, y; };

static bool mod_align_divider(OfficialHost& h, Address node, Address content) {
    const Address base = module.base;
    if (!node || !content || h.get<Address>(node) != base + 0x1b0d7b0
        || h.get<Address>(content) != base + 0x1b4d3e8) return false;
    const Address children = h.get<Address>(node + 0x140);
    const Address begin = h.get<Address>(children);
    const Address end = h.get<Address>(children + 8);
    if (h.fault || !begin || end != begin + sizeof(Address)) return false;
    const Address sprite = h.get<Address>(begin);
    if (h.get<Address>(sprite) != base + 0x1aa0128) return false;
    const ModDividerPoint size = h.get<ModDividerPoint>(sprite + 0x5c);
    const ModDividerPoint position = h.get<ModDividerPoint>(sprite + 0x38);
    const ModDividerPoint anchor = h.get<ModDividerPoint>(content + 0x54);
    const ModDividerPoint content_size = h.get<ModDividerPoint>(content + 0x5c);
    const float scale = size.y / 457.0f;
    if (h.fault || !(scale > 0.1f && scale < 8.0f)
        || __builtin_fabsf(size.x / 110.0f - scale) > 0.001f
        || !((anchor.x == 0.0f && anchor.y == 0.0f)
             || (anchor.x == 0.5f && anchor.y == 0.5f))
        || content_size.x != 110.0f || content_size.y != 457.0f) return false;
    // This NodeReader skips the setter for CSB's default (.5,.5), leaving Node at (0,0).
    const ModDividerPoint centered = {0.5f, 0.5f};
    h.call<void>(0xec4b3c, content, Address(&centered));
    // Preserve the native box/anchor and its renderer-dependent sprite geometry.
    h.call<void>(0x134d7a4, sprite, false);
    if (h.get<unsigned char>(sprite + 0x1c1) != 0 || h.fault) return false;
    h.call<void>(0x18372e8, content, scale);
    h.call<void>(0xd8cbe8, content, Address(&position));
    h.call<void>(0xefd848, node, content);
    return !h.fault;
}
