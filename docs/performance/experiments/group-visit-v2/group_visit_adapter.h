#pragma once
#include "group_visit_geometry.h"
#include <cstdint>
#include <cstring>
#include <initializer_list>

namespace group_visit_adapter {
using Address = uintptr_t;
constexpr Address GROUP = 0x1a993f0, NODE = 0x1b4d3e8, BUTTON = 0x1a8ece0;
constexpr Address SPRITE = 0x1aa0128, LABEL = 0x1adae68, SCALE9 = 0x1ac2238;
constexpr unsigned MAX_MEMBERS = 256, MAX_CHILDREN = 512;
struct Slab {
    unsigned char bytes[0x1c3]{};
    template<class T> T get(unsigned offset) const { T value{}; std::memcpy(&value, bytes + offset, sizeof(value)); return value; }
};
inline bool plus(Address pointer, Address offset, Address* out) {
    if (!pointer || offset > ~Address(0) - pointer) return false;
    *out = pointer + offset; return true;
}
template<class Reader, class T> bool field(Reader& reader, Address pointer, Address offset, T* out) {
    Address at = 0; return plus(pointer, offset, &at) && reader.read(at, out, sizeof(*out));
}
template<class Reader> bool children(Reader& reader, Address node, unsigned offset, Address* out, unsigned limit, unsigned* count) {
    Address vector = 0; if (!field(reader, node, offset, &vector)) return false;
    *count = 0; if (!vector) return true;
    Address values[3]{};
    if ((vector & 7) || !reader.read(vector, values, sizeof(values))) return false;
    const Address begin = values[0], end = values[1], cap = values[2];
    if ((begin & 7) || end < begin || cap < end || (end - begin) % 8 || (cap - begin) % 8
            || end - begin > Address(limit) * 8 || cap - begin > 65536) return false;
    *count = unsigned((end - begin) / 8);
    return !*count || (begin && reader.read(begin, out, *count * sizeof(Address)));
}
inline bool geometry(const Slab& raw, group_visit_geometry::Node* out) {
    auto number = [&](unsigned at) { return double(raw.get<float>(at)); };
    out->rotation_x = number(0x14); out->rotation_y = number(0x18);
    out->qx = number(0x1c); out->qy = number(0x20); out->qz = number(0x24); out->qw = number(0x28);
    out->sx = number(0x2c); out->sy = number(0x30); out->x = number(0x38); out->y = number(0x3c);
    out->skew_x = number(0x44); out->skew_y = number(0x48);
    out->anchor_x = number(0x4c); out->anchor_y = number(0x50);
    out->width = number(0x5c); out->height = number(0x60);
    if (raw.get<uint8_t>(0x1c2) > 1 || number(0x40) != 0 || !std::isfinite(number(0x34))) return false;
    out->ignore_anchor = raw.get<uint8_t>(0x1c2) != 0;
    return true;
}
inline bool identity_rotation(const group_visit_geometry::Node& node) {
    return node.rotation_x == 0 && node.rotation_y == 0 && node.skew_x == 0 && node.skew_y == 0
        && node.qx == 0 && node.qy == 0 && node.qz == 0 && node.qw == 1;
}
inline uint32_t deferred_flags(uint32_t current, uint32_t incoming) {
    return incoming & 3 ? current | 0x10u | (incoming & 2u) : current;
}
template<class Native> inline void forward_native(Native native, Address self, Address renderer, Address transform, uint32_t flags, uint32_t extra) {
    native(self, renderer, transform, flags, extra);
}
template<class Reader> bool polygon(Reader& reader, Address sprite, group_visit_geometry::Node* node) {
    struct Triangles { Address vertices, indices; uint32_t vertex_count, index_count; } triangles{};
    Address vt = 0;
    if (!reader.read(sprite, &vt, sizeof(vt)) || vt != reader.base + SPRITE
            || !field(reader, sprite, 0x468, &triangles) || !triangles.vertices || !triangles.indices
            || (triangles.vertices & 3) || (triangles.indices & 1)
            || triangles.vertex_count < 3 || triangles.vertex_count > 64
            || triangles.index_count < 3 || triangles.index_count > 384 || triangles.index_count % 3) return false;
    // Actual native vertex layout: float positionXYZ, packed color4B, float UV2 =24B.
    struct Vertex { float x, y, z; uint32_t color; float u, v; } vertices[64]{};
    static_assert(sizeof(Vertex) == 24);
    uint16_t indices[384]{};
    if (!reader.read(triangles.vertices, vertices, triangles.vertex_count * sizeof(Vertex))
            || !reader.read(triangles.indices, indices, triangles.index_count * sizeof(uint16_t))) return false;
    double min_x = 1e6, min_y = 1e6, max_x = -1e6, max_y = -1e6;
    for (unsigned index = 0; index < triangles.vertex_count; ++index) {
        const auto& value = vertices[index];
        if (!group_visit_geometry::native_float_range(value.x) || !group_visit_geometry::native_float_range(value.y)
                || value.z != 0 || !std::isfinite(value.u) || !std::isfinite(value.v)) return false;
        if (value.x < min_x) min_x = value.x;
        if (value.x > max_x) max_x = value.x;
        if (value.y < min_y) min_y = value.y;
        if (value.y > max_y) max_y = value.y;
    }
    for (unsigned index = 0; index < triangles.index_count; ++index) if (indices[index] >= triangles.vertex_count) return false;
    node->kind = group_visit_geometry::Kind::Sprite; node->x = min_x; node->y = min_y;
    node->width = max_x - min_x; node->height = max_y - min_y; node->children_complete = true;
    return true;
}
template<class Reader> bool should_skip(Reader& reader, Address self, Address renderer, Address parent_matrix, uint32_t incoming) {
    using namespace group_visit_geometry;
    if (incoming & ~3u) return false;
    Address director = 0, scene = 0, list = 0, inner = 0, expected_renderer = 0;
    Address scene_vt = 0, list_vt = 0;
    if (!reader.read(reader.base + 0x1bee0a0, &director, 8) || !field(reader, director, 0x140, &scene)
            || !field(reader, director, 0x198, &expected_renderer) || renderer != expected_renderer
            || !reader.read(scene, &scene_vt, 8) || scene_vt != reader.base + 0x1ad2260
            || !field(reader, scene, 0x398, &list) || !reader.read(list, &list_vt, 8)
            || list_vt != reader.base + 0x1b039c0 || !field(reader, list, 0x748, &inner)) return false;
    Address chain[] = {scene, list, inner}; Address types[] = {0x1ad2260, 0x1b039c0, 0x1af2d48};
    Address director_vt = 0;
    if (!reader.read(director, &director_vt, 8) || director_vt != reader.base + 0x1b5eaf8) return false;
    double parent_y = 0, viewport_height = 0;
    for (unsigned i = 0; i < 3; ++i) {
        Slab raw; Node node;
        if (!reader.read(chain[i], &raw, sizeof(raw)) || raw.get<Address>(0) != reader.base + types[i]
                || (i && raw.get<Address>(0x148) != chain[i - 1]) || raw.get<uint8_t>(0x1c1) != 1
                || raw.get<Address>(0x128)
                || (raw.get<uint32_t>(0x130) & ~(i ? 0x33u : 0x73u))
                || !geometry(raw, &node) || !identity_rotation(node) || node.sx != 1 || node.sy != 1) return false;
        if (!i) viewport_height = node.height;
        parent_y += node.y + (node.ignore_anchor ? node.anchor_y : 0) - node.anchor_y;
    }
    float matrix[16]{};
    if (!reader.read(parent_matrix, matrix, sizeof(matrix))) return false;
    for (unsigned i = 0; i < 16; ++i) {
        const float expected = i == 0 || i == 5 || i == 10 || i == 15 ? 1.f : 0.f;
        if (!std::isfinite(matrix[i]) || (i != 12 && i != 13 && matrix[i] != expected)) return false;
    }
    if (!native_float_range(parent_y) || std::abs(parent_y - matrix[13]) > 0.05) return false;
    Slab group;
    if (!reader.read(self, &group, sizeof(group)) || group.get<Address>(0) != reader.base + GROUP
            || group.get<Address>(0x148) != inner || group.get<uint8_t>(0x1c1) != 1) return false;
    unsigned char group_layout[7]{}; float header_height = 0;
    if (!reader.read(self + 0x5a1, group_layout, sizeof(group_layout)) || group_layout[0] != 1 || group_layout[1] != 1) return false;
    std::memcpy(&header_height, group_layout + 3, sizeof(header_height));
    if (header_height != group.get<float>(0x60)) return false;
    Address top[MAX_CHILDREN]{}; unsigned top_count = 0, self_occurrences = 0;
    if (!children(reader, inner, 0x140, top, MAX_CHILDREN, &top_count)) return false;
    for (unsigned i = 0; i < top_count; ++i) if (top[i] == self) ++self_occurrences;
    if (self_occurrences != 1) return false;
    Address member_range[2]{}; Address members[MAX_MEMBERS]{};
    if (!reader.read(self + 0x500, member_range, sizeof(member_range)) || member_range[1] < member_range[0]
            || (member_range[0] & 7) || (member_range[1] - member_range[0]) % 8
            || member_range[1] - member_range[0] > MAX_MEMBERS * 8) return false;
    const unsigned member_count = unsigned((member_range[1] - member_range[0]) / 8);
    if (member_count && !reader.read(member_range[0], members, member_count * 8)) return false;
    for (unsigned i = 0; i < member_count; ++i) {
        if (!members[i]) return false;
        for (unsigned j = 0; j < i; ++j) if (members[i] == members[j]) return false;
    }
    if (!reader.members_hidden(members, member_count, reader.base + 0x1b177d0)) return false;
    Node nodes[MAX_NODES]{}; Address addresses[MAX_NODES]{}; unsigned count = 1, real_count = 1;
    nodes[0].kind = Kind::Group; nodes[0].parent = NO_PARENT; addresses[0] = self;
    if (!geometry(group, &nodes[0])) return false;
    unsigned skipped_members = 0; bool member_seen[MAX_MEMBERS]{};
    for (unsigned cursor = 0; cursor < count; ++cursor) {
        if (!addresses[cursor]) continue; // Synthetic actual-polygon rectangle.
        const Address current = addresses[cursor]; Slab raw;
        if (!reader.read(current, &raw, sizeof(raw))) return false;
        const Address type = raw.get<Address>(0) - reader.base;
        if (type != GROUP && type != NODE && type != BUTTON && type != SPRITE && type != LABEL && type != SCALE9) return false;
        if (cursor && raw.get<Address>(0x148) != addresses[nodes[cursor].parent]) return false;
        if (raw.get<uint8_t>(0x1c1) > 1) return false;
        if (!raw.get<uint8_t>(0x1c1)) { // Native visible early return precedes dirty adaptation.
            const auto parent = nodes[cursor].parent;
            nodes[cursor] = {}; nodes[cursor].kind = Kind::Node; nodes[cursor].parent = parent;
            nodes[cursor].children_complete = true; continue;
        }
        const auto parent = nodes[cursor].parent;
        if (raw.get<Address>(0x128)) return false;
        if (raw.get<uint32_t>(0x130) & ~0x33u) return false;
        if (!geometry(raw, &nodes[cursor])) return false;
        nodes[cursor].parent = parent;
        nodes[cursor].kind = !cursor ? Kind::Group : type == BUTTON ? Kind::Button
            : type == SPRITE || type == SCALE9 ? Kind::Sprite : type == LABEL ? Kind::Label : Kind::Node;
        if (type == BUTTON) {
            uint8_t dirty[3]{};
            if (!reader.read(current + 0x503, dirty, 3) || dirty[0] || dirty[1] || dirty[2]) return false;
        }
        if (type == LABEL) {
            if (!reader.label_clean(current)) return false;
        }
        if (type == SPRITE || type == SCALE9) {
            Address sprite = current;
            if (type == SCALE9) {
                unsigned char state[9]{}; uint8_t dirty = 0;
                if (!reader.read(current + 0x2d0, state, sizeof(state))
                        || !field(reader, current, 0x330, &dirty) || state[8] != 1 || dirty) return false;
                std::memcpy(&sprite, state, sizeof(sprite));
            }
            if (count == MAX_NODES || !polygon(reader, sprite, &nodes[count])) return false;
            nodes[count].parent = cursor; addresses[count++] = 0;
        }
        for (unsigned offset : {0x140u, 0x2a0u}) {
            if (offset == 0x2a0 && type != GROUP && type != BUTTON) continue;
            Address children_values[MAX_CHILDREN]{}; unsigned children_count = 0;
            if (!children(reader, current, offset, children_values, !cursor ? MAX_CHILDREN : 32, &children_count)) return false;
            for (unsigned index = 0; index < children_count; ++index) {
                const Address child = children_values[index]; if (!child) return false;
                bool member = false;
                for (unsigned j = 0; j < member_count; ++j) if (members[j] == child) {
                    if (member_seen[j]) return false;
                    member_seen[j] = true; member = true;
                }
                if (member) { if (cursor || offset != 0x140) return false; ++skipped_members; continue; }
                for (unsigned j = 0; j < count; ++j) if (addresses[j] == child) return false;
                if (count == MAX_NODES) return false;
                nodes[count].parent = cursor; addresses[count++] = child; ++real_count;
            }
        }
        nodes[cursor].children_complete = true;
    }
    if (skipped_members != member_count || real_count < 7) return false;
    Address visuals[10]{};
    if (!reader.read(self + 0x550, visuals, sizeof(visuals))) return false;
    for (unsigned slot : {0u, 1u, 2u, 5u, 6u, 7u, 8u, 9u}) {
        const Address pointer = visuals[slot];
        if (!pointer) continue;
        bool found = false; for (unsigned i = 0; i < count; ++i) if (addresses[i] == pointer) found = true;
        if (!found) return false;
    }
    Input input{nodes, count, matrix[13], viewport_height, true, true, true};
    const auto result = evaluate(input);
    if (!result.validated || !result.skip_visit) return false;
    const uint32_t old_flags = group.get<uint32_t>(0x130), flags = deferred_flags(old_flags, incoming);
    return flags == old_flags || reader.write_flags(self + 0x130, flags);
}
} // namespace group_visit_adapter
