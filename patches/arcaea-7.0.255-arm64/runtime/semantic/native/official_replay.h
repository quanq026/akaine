#pragma once
#include "official32/modern/modern_replay.h"
#include "official32/finale/finale_replay.h"
#include "official32/legacy/legacy_replay.h"

namespace akaine_official {
enum class Family : uint8_t { Modern, Finale, Legacy };
enum class CallbackPolicy : uint8_t { Native, Replay, Denied };
inline CallbackPolicy callbackPolicy(bool registered,bool ready,bool identity) {
    if (!registered) return CallbackPolicy::Native;
    return ready && identity ? CallbackPolicy::Replay : CallbackPolicy::Denied;
}
struct OfficialProfile {
    const char* song;
    Family family;
    unsigned variant;
    unsigned size;
    Address vtable, init, update, finish;
};
inline constexpr OfficialProfile official_profiles[] = {
    {"arghena",Family::Modern,0,0x330,0x1aab340,0x12c9038,0xa11370,0x1007888},
    {"designant",Family::Modern,1,0x380,0x1ac9e98,0x17c4c18,0x10e5124,0xc39a34},
    {"alterego",Family::Modern,2,0x340,0x1b3a9a0,0x148f630,0x113b944,0xafe9f0},
    {"dreadarea",Family::Modern,3,0x300,0x1abc5e0,0xc29e9c,0x133503c,0x15b9414},
    {"cataclysmcry",Family::Modern,4,0x300,0x1ad9060,0xcacca4,0x98c314,0x15b9414},
    {"deinosphainein",Family::Modern,5,0x340,0x1b47b80,0x1480774,0x95c0e4,0x15b9414},
    {"ember",Family::Modern,6,0x300,0x1b6e930,0x1557b34,0x133503c,0x1460b84},
    {"sacrosanct",Family::Modern,7,0x300,0x1a98730,0x83520c,0x133503c,0x12fd3a4},
    {"astralquant",Family::Modern,8,0x300,0x1ac7018,0x88b42c,0x133503c,0x15b9414},
    {"undyingmacula",Family::Modern,9,0x3a0,0x1aec6c8,0xd411d4,0x9895b8,0x190742c},
    {"desive",Family::Modern,10,0x300,0x1b3e360,0x10a6b94,0x133503c,0x15b9414},
    {"lamentrain",Family::Modern,11,0x310,0x1ab11b8,0x16ce69c,0x128e1b8,0x150fd18},
    {"yourbestnightmare",Family::Modern,12,0x300,0x1a87760,0x187cc48,0x133503c,0x15b9414},
    {"infinitestrife",Family::Finale,0,0x300,0x1b7dee8,0xcf737c,0x133503c,0x15b9414},
    {"worldender",Family::Finale,1,0x300,0x1b7dee8,0xcf737c,0x133503c,0x15b9414},
    {"pentiment",Family::Finale,2,0x300,0x1b7dee8,0xcf737c,0x133503c,0x15b9414},
    {"arcanaeden",Family::Finale,3,0x300,0x1b7dee8,0xcf737c,0x133503c,0x15b9414},
    {"testify",Family::Finale,4,0x310,0x1b90f50,0x10f58a0,0xe1a8ac,0x160c7f0},
    {"last",Family::Finale,5,0x320,0x1b62708,0xb8a498,0x7f3028,0x1247a84},
    {"lasteternity",Family::Finale,6,0x320,0x1b62708,0xb8a498,0x7f3028,0x1247a84},
    {"grievouslady",Family::Legacy,0,0x300,0x1a90bd0,0xab0000,0x133503c,0x15b9414},
    {"fractureray",Family::Legacy,1,0x300,0x1abe460,0xaf8694,0x133503c,0x15b9414},
    {"aegleseeker",Family::Legacy,2,0x390,0x1a89110,0x1135ab8,0xa8db9c,0x1207f70},
    {"singularity",Family::Legacy,3,0x310,0x1b40738,0xc71958,0xb3620c,0x1899aa4},
    {"arcahv",Family::Legacy,4,0x300,0x1b022d8,0x7bf690,0x196e03c,0xca5aec},
    {"tempestissimo",Family::Legacy,5,0x370,0x1b37588,0x12d50e0,0x18af9f4,0xfb5af4},
    {"axiumcrisis",Family::Legacy,6,0x300,0x1ad6c70,0x101da2c,0x1a11ab4,0x15b9414},
    {"etherstrike",Family::Legacy,7,0x320,0x1aa2dd0,0x13b7dd4,0xd6476c,0x8e6fd8},
    {"antagonism",Family::Legacy,8,0x300,0x1b0b1d8,0xda9b80,0x133503c,0xff8960},
    {"dantalion",Family::Legacy,8,0x300,0x1b0b1d8,0xda9b80,0x133503c,0xff8960},
    {"equilibrium",Family::Legacy,8,0x300,0x1b0b1d8,0xda9b80,0x133503c,0xff8960},
    {"ifi",Family::Legacy,8,0x300,0x1b0b1d8,0xda9b80,0x133503c,0xff8960},
};
static_assert(sizeof(official_profiles)/sizeof(official_profiles[0])==32);
inline const OfficialProfile* officialProfile(const char* song) {
    if (song) for (const auto& p:official_profiles) if (std::strcmp(song,p.song)==0) return &p;
    return nullptr;
}
inline bool isLastProfile(const OfficialProfile& p) {
    return p.family==Family::Finale && isLastEnding(static_cast<FinaleId>(p.variant));
}
inline bool mandatoryGameplay(const OfficialProfile& p) {
    return p.family==Family::Modern && (p.variant==10 || p.variant==12);
}
inline bool transitionTarget(const OfficialProfile& p, unsigned type) {
    return p.family==Family::Legacy && ((p.variant==0 && type==1) || (p.variant==1 && type==3));
}
inline bool preserveStoryModifier(const OfficialProfile& p,unsigned type,bool enabled,unsigned finale_intent=0) {
    const bool owned_finale_intro = p.family==Family::Finale && p.variant<4 && type==5
        && finale_intent>=1 && finale_intent<=4;
    return type!=0 && !(enabled && (transitionTarget(p,type) || owned_finale_intro));
}
inline Address progressOriginal(unsigned op) {
    return op<6 ? last_progress_calls[op].original : 0;
}
inline bool skipLastProgress(const OfficialProfile* p,bool registered,bool failed,unsigned op) {
    (void)failed;
    return p && registered && isLastProfile(*p) && op<6;
}
template<class Host> Address createOfficial(const OfficialProfile& p,Address scene,Host& h) {
    if (p.family==Family::Modern) return createModernReplay(static_cast<ModernId>(p.variant),scene,h);
    if (p.family==Family::Finale) return createFinaleReplay(static_cast<FinaleId>(p.variant),h);
    return official32::legacy::createLegacyReplay(static_cast<official32::legacy::Profile>(p.variant),h);
}
template<class Host> bool initOfficial(const OfficialProfile& p,Address m,Host& h) {
    if (p.family==Family::Modern) return initModernReplay(static_cast<ModernId>(p.variant),m,h);
    if (p.family==Family::Finale) {
        if (p.variant==4) return h.template call<bool>(p.init,m);
        return initFinaleReplay(static_cast<FinaleId>(p.variant),m,h);
    }
    return official32::legacy::init(static_cast<official32::legacy::Profile>(p.variant),m,h);
}
template<class Host> uint64_t finishOfficial(const OfficialProfile& p,Address m,Address cb,uint32_t failed,Host& h) {
    h.template put<uint32_t>(m+0x2b8,0);
    if (p.family==Family::Modern) return finishModernReplay(static_cast<ModernId>(p.variant),m,cb,failed,h);
    if (p.family==Family::Finale) {
        if (p.variant==4) return h.template call<uint64_t>(p.finish,m,cb,failed);
        return finishFinaleReplay(static_cast<FinaleId>(p.variant),m,cb,failed,h);
    }
    const auto id=static_cast<official32::legacy::Profile>(p.variant);
    if (official32::legacy::skipProgressFinish(id)) return 0;
    auto result=h.template call<uint64_t>(p.finish,m,cb,failed);
    h.template put<uint32_t>(m+0x2b8,0);
    return result;
}
} // namespace akaine_official
