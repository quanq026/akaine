#pragma once

namespace official32::legacy {

using Address = __UINTPTR_TYPE__;
using UInt = __UINT32_TYPE__;
using Int = __INT32_TYPE__;
using Byte = unsigned char;

enum class Profile { GrievousLady, FractureRay, Aegleseeker, Singularity, Arcahv,
                     Tempestissimo, AxiumCrisis, EtherStrike, TempestPrerequisite };

struct Contract {
    Profile profile;
    const char* song;
    UInt size;
    Address vtable;
    Address creator;
    Address nativeInit;
    bool skipProgressFinish;
};

inline constexpr Contract contracts[] = {
    {Profile::GrievousLady, "grievouslady", 0x300, 0x1a90bd0, 0, 0xab0000, false},
    {Profile::FractureRay, "fractureray", 0x300, 0x1abe460, 0, 0xaf8694, false},
    {Profile::Aegleseeker, "aegleseeker", 0x390, 0x1a89110, 0x961e14, 0x1135ab8, true},
    {Profile::Singularity, "singularity", 0x310, 0x1b40738, 0x19f9bb8, 0xc71958, true},
    {Profile::Arcahv, "arcahv", 0x300, 0x1b022d8, 0x1976684, 0x7bf690, true},
    {Profile::Tempestissimo, "tempestissimo", 0x370, 0x1b37588, 0xaacbfc, 0x12d50e0, false},
    {Profile::AxiumCrisis, "axiumcrisis", 0x300, 0x1ad6c70, 0, 0x101da2c, false},
    {Profile::EtherStrike, "etherstrike", 0x320, 0x1aa2dd0, 0x150a148, 0x13b7dd4, false},
    {Profile::TempestPrerequisite, "antagonism", 0x300, 0x1b0b1d8, 0, 0xda9b80, true},
    {Profile::TempestPrerequisite, "dantalion", 0x300, 0x1b0b1d8, 0, 0xda9b80, true},
    {Profile::TempestPrerequisite, "equilibrium", 0x300, 0x1b0b1d8, 0, 0xda9b80, true},
    {Profile::TempestPrerequisite, "ifi", 0x300, 0x1b0b1d8, 0, 0xda9b80, true},
};

// Native creators autorelease. The factory owner retains once after assigning GameScene+0x308.
template<class Host>
Address createLegacyReplay(Profile profile, Host& host) {
    Address modifier = 0;
    switch (profile) {
    case Profile::GrievousLady: modifier = host.makeNode(0x300, 0x1a90bd0); break;
    case Profile::FractureRay: modifier = host.makeNode(0x300, 0x1abe460); break;
    case Profile::Aegleseeker: modifier = host.template call<Address>(0x961e14); break;
    case Profile::Singularity: modifier = host.template call<Address>(0x19f9bb8); break;
    case Profile::Arcahv: modifier = host.template call<Address>(0x1976684, Int{1}); break;
    case Profile::Tempestissimo: modifier = host.template call<Address>(0xaacbfc, Int{0}); break;
    case Profile::AxiumCrisis:
        modifier = host.makeNode(0x300, 0x1ad6c70);
        if (modifier) host.template call<void>(0xe65708, modifier + 0x2f8);
        break;
    case Profile::EtherStrike: modifier = host.template call<Address>(0x150a148); break;
    case Profile::TempestPrerequisite: modifier = host.makeNode(0x300, 0x1b0b1d8); break;
    }
    if (modifier) host.template put<Int>(modifier + 0x2b8, 0);
    return modifier;
}

// Host calls use ELF VAs; the caller must register only normal, permitted replay actors.
template<class Host>
bool init(Profile profile, Address modifier, Host& host) {
    switch (profile) {
    case Profile::GrievousLady:
        return (host.template call<UInt>(0xab0000, modifier) & 1) != 0;
    case Profile::FractureRay:
        return (host.template call<UInt>(0xaf8694, modifier) & 1) != 0;
    case Profile::Aegleseeker: {
        // Preset replay state also reaches native callback setup with another partner.
        host.template put<Int>(modifier + 0x2f4, 2);
        const auto result = host.template call<UInt>(0x1135ab8, modifier);
        host.template put<Int>(modifier + 0x2f4, 2);
        return (result & 1) != 0;
    }
    case Profile::Singularity:
        // Native init includes a story write; its replay payload is local activation/layout.
        host.template put<Byte>(modifier + 0x2f4, 1);
        host.template call<void>(0xcaeda8,
            host.template get<Address>(modifier + 0x2c8), Int{12});
        return true;
    case Profile::Arcahv:
        return (host.template call<UInt>(0x7bf690, modifier) & 1) != 0;
    case Profile::AxiumCrisis:
        host.template put<Byte>(modifier + 0x2f4, 1);
        return (host.template call<UInt>(0x101da2c, modifier) & 1) != 0;
    case Profile::EtherStrike:
        host.template put<Byte>(modifier + 0x2f4, 1);
        return (host.template call<UInt>(0x13b7dd4, modifier) & 1) != 0;
    case Profile::Tempestissimo:
        return (host.template call<UInt>(0x12d50e0, modifier) & 1) != 0;
    case Profile::TempestPrerequisite:
        return (host.template call<UInt>(0xda9b80, modifier) & 1) != 0;
    }
    return false;
}

inline bool skipProgressFinish(Profile profile) {
    return profile == Profile::Aegleseeker || profile == Profile::Singularity ||
           profile == Profile::Arcahv || profile == Profile::TempestPrerequisite;
}

inline UInt initScope(Profile profile) {
    return profile == Profile::AxiumCrisis ? 1 : profile == Profile::EtherStrike ? 2 :
           profile == Profile::Tempestissimo ? 3 : 0;
}

} // namespace official32::legacy
