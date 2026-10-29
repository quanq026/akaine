#pragma once
#include <cmath>
#include <cstddef>
#include <limits>

// Pure QA predicate only. The adapter must prove exact native identities and a
// complete bounded tree, including protected Button children, before calling.
namespace group_visit_geometry {
constexpr std::size_t MAX_NODES = 64, NO_PARENT = MAX_NODES;
constexpr double PADDING = 512.0;
enum class Kind { Unknown, Group, Node, Button, Sprite, Label };
struct Node {
    Kind kind = Kind::Unknown;
    std::size_t parent = NO_PARENT;
    double x = 0, y = 0, sx = 1, sy = 1;
    double anchor_x = 0, anchor_y = 0, width = 0, height = 0;
    double rotation_x = 0, rotation_y = 0, skew_x = 0, skew_y = 0;
    double qx = 0, qy = 0, qz = 0, qw = 1;
    bool ignore_anchor = false, children_complete = false;
};
struct Input {
    const Node* nodes = nullptr;
    std::size_t count = 0;
    double parent_y = 0, viewport_height = 0;
    bool exact_group_identity = false, tree_complete = false;
    bool ancestor_chain_unit_scale_unrotated = false;
};
struct Result {
    bool validated = false, skip_visit = false;
    double minimum_y = 0, maximum_y = 0;
};
inline bool finite(double value) { return std::isfinite(value); }
inline bool native_float_range(double value) {
    // Keep float-rounding uncertainty far below the fixed 512px padding. Large
    // or compounded transforms remain native rather than guessing a bound.
    return finite(value) && std::abs(value) <= 1000000.0;
}
inline Result evaluate(const Input& input) {
    Result result;
    if (!input.nodes || !input.count || input.count > MAX_NODES || !input.exact_group_identity
            || !input.tree_complete || !input.ancestor_chain_unit_scale_unrotated
            || !native_float_range(input.parent_y) || !finite(input.viewport_height)
            || input.viewport_height <= 0 || input.viewport_height > 1000000.0) return result;
    double translations[MAX_NODES] = {}, scales[MAX_NODES] = {};
    double minimum = std::numeric_limits<double>::infinity();
    double maximum = -std::numeric_limits<double>::infinity();
    for (std::size_t index = 0; index < input.count; ++index) {
        const Node& node = input.nodes[index];
        const bool known_child = node.kind == Kind::Node || node.kind == Kind::Button
            || node.kind == Kind::Sprite || node.kind == Kind::Label;
        if ((index == 0 && (node.kind != Kind::Group || node.parent != NO_PARENT || node.sx != 1 || node.sy != 1))
                || (index && (!known_child || node.parent >= index))
                || !node.children_complete) return result;
        const double values[] = {node.x, node.y, node.sx, node.sy, node.anchor_x, node.anchor_y,
            node.width, node.height, node.rotation_x, node.rotation_y, node.skew_x, node.skew_y,
            node.qx, node.qy, node.qz, node.qw};
        for (double value : values) if (!native_float_range(value)) return result;
        if (node.width < 0 || node.height < 0 || node.sx == 0 || node.sy == 0
                || node.rotation_x != 0 || node.rotation_y != 0 || node.skew_x != 0 || node.skew_y != 0
                || node.qx != 0 || node.qy != 0 || node.qz != 0 || node.qw != 1) return result;
        const double parent_y = index ? translations[node.parent] : input.parent_y;
        const double parent_scale = index ? scales[node.parent] : 1.0;
        const double scaled_anchor = node.sy * node.anchor_y;
        const double adjusted_y = node.y + (node.ignore_anchor ? node.anchor_y : 0.0) - scaled_anchor;
        const double translated_delta = parent_scale * adjusted_y;
        const double translation = parent_y + translated_delta;
        const double scale = parent_scale * node.sy;
        const double extent = scale * node.height;
        const double other_y = translation + extent;
        if (!native_float_range(scaled_anchor) || !native_float_range(adjusted_y)
                || !native_float_range(translated_delta) || !native_float_range(translation)
                || !native_float_range(scale) || !native_float_range(extent) || !native_float_range(other_y)) return result;
        translations[index] = translation; scales[index] = scale;
        if (translation < minimum) minimum = translation;
        if (translation > maximum) maximum = translation;
        if (other_y < minimum) minimum = other_y;
        if (other_y > maximum) maximum = other_y;
    }
    result.validated = true;
    result.minimum_y = minimum; result.maximum_y = maximum;
    // Strict inequalities preserve touching/intersecting padding boundaries.
    result.skip_visit = maximum + PADDING < 0.0 || minimum - PADDING > input.viewport_height;
    return result;
}
} // namespace group_visit_geometry
