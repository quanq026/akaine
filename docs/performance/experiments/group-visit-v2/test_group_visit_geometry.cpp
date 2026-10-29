#include <cassert>
#include <cmath>
#include <cstdio>
#include <limits>
#include "group_visit_geometry.h"
using namespace group_visit_geometry;
struct Fixture {
    Node nodes[4];
    Input input;
    Fixture() {
        nodes[0].kind = Kind::Group; nodes[0].width = 600; nodes[0].height = 40; nodes[0].children_complete = true;
        nodes[1].kind = Kind::Button; nodes[1].parent = 0; nodes[1].width = 600; nodes[1].height = 40; nodes[1].children_complete = true;
        nodes[2].kind = Kind::Sprite; nodes[2].parent = 1; nodes[2].width = 300; nodes[2].height = 40; nodes[2].children_complete = true;
        nodes[3].kind = Kind::Label; nodes[3].parent = 0; nodes[3].width = 200; nodes[3].height = 20; nodes[3].children_complete = true;
        input = {nodes, 4, 0, 1080, true, true, true};
    }
    Result get() { return evaluate(input); }
};
int main() {
    Fixture f;
    assert(f.get().validated && !f.get().skip_visit);
    f.nodes[0].y = -600; assert(f.get().skip_visit);
    f.nodes[0].y = -552; assert(!f.get().skip_visit); // Highest point -512 touches padding.
    f.nodes[0].y = -553; assert(f.get().skip_visit);
    f.nodes[0].y = 1592; assert(!f.get().skip_visit);
    f.nodes[0].y = 1593; assert(f.get().skip_visit);
    f.nodes[0].y = -600; f.nodes[3].y = 600; assert(!f.get().skip_visit); // Offscreen group with visible label.
    f.nodes[3].y = 0; f.nodes[2].y = 600; assert(!f.get().skip_visit); // Protected Button child must join union.
    f.nodes[2].y = 0; f.nodes[0].height = 241704; assert(!f.get().skip_visit); // Open group intersects viewport.
    f.nodes[0].height = 40; f.nodes[0].y = 0;
    f.nodes[1].y = 100; f.nodes[1].sy = 2; f.nodes[1].anchor_y = 10;
    f.nodes[2].y = 5; f.nodes[2].sy = 3; f.nodes[2].anchor_y = 2; f.nodes[2].height = 4;
    auto result = f.get(); assert(result.validated && result.minimum_y == 0 && result.maximum_y == 160);
    // Button translation80, child translation78 and child extent24. Button's own top160 dominates.
    f.nodes[1].ignore_anchor = true; result = f.get(); assert(result.maximum_y == 170);
    f.nodes[1].sy = -2; f.nodes[1].ignore_anchor = false; result = f.get();
    assert(result.validated && result.minimum_y == 0 && result.maximum_y == 122);
    // Sprite's sy3 over reflected Button: translation122, extent-24; other roots remain included.
    f.nodes[1].sy = 2; f.input.parent_y = 50; result = f.get(); assert(result.minimum_y == 50 && result.maximum_y == 210);
    for (unsigned bad = 0; bad < 14; ++bad) {
        Fixture invalid;
        if (bad == 0) invalid.input.tree_complete = false;
        if (bad == 1) invalid.input.exact_group_identity = false;
        if (bad == 2) invalid.input.ancestor_chain_unit_scale_unrotated = false;
        if (bad == 3) invalid.nodes[2].kind = Kind::Unknown;
        if (bad == 4) invalid.nodes[1].children_complete = false;
        if (bad == 5) invalid.nodes[1].parent = 3;
        if (bad == 6) invalid.nodes[1].rotation_x = 0.0001;
        if (bad == 7) invalid.nodes[1].skew_y = 1;
        if (bad == 8) invalid.nodes[1].qz = 0.1;
        if (bad == 9) invalid.nodes[1].qw = -1;
        if (bad == 10) invalid.nodes[1].height = -1;
        if (bad == 11) invalid.nodes[1].y = std::numeric_limits<double>::quiet_NaN();
        if (bad == 12) invalid.nodes[1].sy = std::numeric_limits<double>::infinity();
        if (bad == 13) invalid.nodes[0].sy = 2;
        assert(!invalid.get().validated && !invalid.get().skip_visit);
    }
    Fixture large; large.nodes[0].y = 1e20; assert(!large.get().validated && !large.get().skip_visit);
    Fixture huge; huge.nodes[1].sy = 1e6; huge.nodes[2].sy = 1e6;
    assert(!huge.get().validated && !huge.get().skip_visit);
    Fixture bad_count; bad_count.input.count = MAX_NODES + 1;
    assert(!bad_count.get().validated && !bad_count.get().skip_visit);
    puts("PASS conservative padded Y union, descendant/protected-child inclusion, open-group safety, anchors/scales/reflection, unknown tree/transform/numeric fail-open");
}
