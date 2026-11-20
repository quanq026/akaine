#pragma once
// Official anomaly replay families and their shared dispatch contract.
#include <cstdint>
#include <cstring>

namespace akaine_official {
using Address = uintptr_t;
enum class ModernId : uint8_t {
  Arghena, Designant, AlterEgo, DreadArea, CataclysmCry, DeinosPhainein,
  Ember, Sacrosanct, AstralQuant, UndyingMacula, Desive, LamentRain,
  YourBestNightmare, None
};
inline constexpr const char* modern_ids[] = {
  "arghena", "designant", "alterego", "dreadarea", "cataclysmcry",
  "deinosphainein", "ember", "sacrosanct", "astralquant", "undyingmacula",
  "desive", "lamentrain", "yourbestnightmare"
};
inline ModernId modernId(const char* sid) {
  if (!sid) return ModernId::None;
  for (unsigned i=0; i<13; ++i)
    if (std::strcmp(sid, modern_ids[i])==0) return static_cast<ModernId>(i);
  return ModernId::None;
}

// Root host resolves only hash-qualified native functions and validated context.
template<class Host> Address createModernReplay(ModernId id, Address scene, Host& h) {
  Address m=0;
  switch (id) {
    case ModernId::Arghena: m=h.template call<Address>(0x189f500); break;
    case ModernId::Designant:
      m=h.template call<Address>(0x1819588,h.song_id_string(scene),false); break;
    case ModernId::AlterEgo: m=h.template call<Address>(0x133d938); break;
    case ModernId::DreadArea: m=h.template call<Address>(0x968c44,true); break;
    case ModernId::CataclysmCry: m=h.template call<Address>(0x819afc,true); break;
    case ModernId::DeinosPhainein: m=h.template call<Address>(0x1508dac); break;
    case ModernId::Ember: m=h.template call<Address>(0x13fe014,true); break;
    case ModernId::Sacrosanct: m=h.makeNode(0x300,0x1a98730); break;
    case ModernId::AstralQuant: m=h.makeNode(0x300,0x1ac7018); break;
    case ModernId::UndyingMacula: m=h.makeNode(0x3a0,0x1aec6c8); break;
    case ModernId::Desive: m=h.template call<Address>(0xfa0220); break;
    case ModernId::LamentRain:
      m=h.template call<Address>(0x14e56fc,true,h.template get<int32_t>(scene+0x320)); break;
    case ModernId::YourBestNightmare: m=h.template call<Address>(0x17e79e0); break;
    case ModernId::None: return 0;
  }
  if (!m) return 0;
  h.template put<uint32_t>(m+0x2b8,0);
  switch (id) {
    case ModernId::Designant: h.template put<uint32_t>(m+0x2f8,2); break;
    case ModernId::AlterEgo: h.template put<uint32_t>(m+0x330,2); break;
    case ModernId::DeinosPhainein: h.template put<uint8_t>(m+0x2f4,1); break;
    default: break;
  }
  return m;
}

template<class Host> void modernGaugePrefix(Address m, bool disable_gauge, Host& h) {
  auto play=h.template get<Address>(m+0x2d0);
  h.template call<void>(0xb9e0d0,play);
  h.template call<void>(0x1856110,play,0.2f);
  h.template call<void>(0xfa4320,play);
  h.template call<void>(0x79b000,play);
  if (disable_gauge) {
    auto gauge=h.template call<Address>(0x98b33c,play);
    auto fn=h.template get<Address>(h.template get<Address>(gauge)+0x150);
    // The host call helper accepts ELF VAs; this method comes from a loaded vtable.
    h.template call<void>(fn-h.base,gauge,false);
    gauge=h.template call<Address>(0x98b33c,play);
    h.template put<uint8_t>(gauge+0x3aa,1);
  }
}

template<class Host> bool initModernReplay(ModernId id, Address m, Host& h) {
  // Stock context binding (1866284) must precede this init wrapper.
  h.template put<uint32_t>(m+0x2b8,0);
  bool ok=true;
  switch (id) {
    case ModernId::Arghena: {
      h.template call<void>(0x16bdad8,m);
      h.template put<uint8_t>(m+0x326,0);
      auto scene=h.template get<Address>(m+0x2a0);
      auto video=h.template call<Address>(0x1929dc0,
          h.template get<Address>(m+0x2c8),h.song_id_string(scene));
      if (!video) return false;
      h.template put<uint32_t>(m+0x2f4,1);
      h.template put<Address>(m+0x2f8,video);
      h.schedule(m,0x1ae9f10,m);
      break;
    }
    case ModernId::Designant:
      h.template put<uint32_t>(m+0x2f8,2);
      ok=h.template call<bool>(0x17c4c18,m);
      // Native event keeps session health/visuals; this blocks its mastery write.
      h.template put<uint8_t>(m+0x329,1);
      break;
    case ModernId::AlterEgo:
      h.template put<uint32_t>(m+0x330,2);
      ok=h.template call<bool>(0x148f630,m); break;
    case ModernId::DreadArea:
      ok=h.template call<bool>(0xc29e9c,m); break;
    case ModernId::CataclysmCry:
      ok=h.template call<bool>(0xcacca4,m); break;
    case ModernId::DeinosPhainein:
      h.template put<uint8_t>(m+0x2f4,1);
      ok=h.template call<bool>(0x1480774,m); break;
    case ModernId::Ember: {
      // Native init writes story state before visuals, so replay runs only visuals.
      auto play=h.template get<Address>(m+0x2d0);
      h.template call<void>(0xfa4320,play);
      h.template call<void>(0x79b000,play);
      h.template call<void>(0x1856110,play,0.2f);
      h.template put<uint8_t>(m+0x2f4,1);
      break;
    }
    case ModernId::Sacrosanct: modernGaugePrefix(m,false,h); break;
    case ModernId::AstralQuant: modernGaugePrefix(m,true,h); break;
    case ModernId::UndyingMacula:
      // False builds all animated UI; true init also rewrites chart unlock progress.
      h.template put<uint8_t>(m+0x2f4,0);
      ok=h.template call<bool>(0xd411d4,m);
      h.template put<uint8_t>(m+0x2f4,1);
      break;
    case ModernId::Desive: ok=h.template call<bool>(0x10a6b94,m); break;
    case ModernId::LamentRain: ok=h.template call<bool>(0x16ce69c,m); break;
    case ModernId::YourBestNightmare: ok=h.template call<bool>(0x187cc48,m); break;
    case ModernId::None: return false;
  }
  h.template put<uint32_t>(m+0x2b8,0);
  return ok;
}

// Replay-specific finish is separate from normal GameSession score persistence.
template<class Host> uint64_t finishModernReplay(ModernId id, Address m,
    Address callback, uint32_t failed, Host& h) {
  h.template put<uint32_t>(m+0x2b8,0);
  if (id==ModernId::LamentRain)
    return h.template call<uint64_t>(0x150fd18,m,callback);
  (void)failed;
  return 0;
}
} // namespace akaine_official
#include <cstdint>
#include <cstring>

namespace akaine_official {
using FinaleAddress = uintptr_t;
enum class FinaleId : uint8_t { InfiniteStrife, WorldEnder, Pentiment, ArcanaEden, Testify, Last, LastEternity, None };
inline constexpr const char* finale_ids[] = {"infinitestrife","worldender","pentiment","arcanaeden","testify","last","lasteternity"};
inline FinaleId finaleId(const char* song) {
  if (!song) return FinaleId::None;
  for (unsigned i=0;i<7;++i)
    if (std::strcmp(song,finale_ids[i])==0) return static_cast<FinaleId>(i);
  return FinaleId::None;
}
inline constexpr bool isFinaleMinor(FinaleId id) {
  return static_cast<unsigned>(id)<4;
}
inline constexpr bool isLastEnding(FinaleId id) {
  return id==FinaleId::Last || id==FinaleId::LastEternity;
}
inline constexpr bool finaleIntroEnabled(int song_index,int game_mode,bool permitted,bool setting_enabled) {
  return song_index>=0 && song_index<=4 && game_mode==0 && permitted && setting_enabled;
}

// Creation is separate from stock context binding and virtual init.
template<class Host> FinaleAddress createFinaleReplay(FinaleId id,Host& h) {
  FinaleAddress modifier=0;
  if (isFinaleMinor(id)) modifier=h.makeNode(0x300,0x1b7dee8);
  else if (id==FinaleId::Testify) modifier=h.template call<FinaleAddress>(0x11e1d4c,uint32_t{2});
  else if (isLastEnding(id)) modifier=h.template call<FinaleAddress>(0xfb6550,false);
  if (modifier) h.template put<uint32_t>(modifier+0x2b8,0);
  return modifier;
}

template<class Host> bool initFinaleReplay(FinaleId id,FinaleAddress modifier,Host& h) {
  bool ok=false;
  if (isFinaleMinor(id)) ok=h.template call<bool>(0xcf737c,modifier);
  else if (isLastEnding(id)) {
    // True init rewrites HP/drain; mode2 after false init changes only the ending.
    h.template put<uint8_t>(modifier+0x2f4,0);
    ok=h.template call<bool>(0xb8a498,modifier);
    if (ok) h.template put<uint32_t>(modifier+0x2f8,2);
  }
  h.template put<uint32_t>(modifier+0x2b8,0);
  return ok;
}

// Install every Last progress guard below before exposing this finish wrapper.
template<class Host> uint64_t finishFinaleReplay(FinaleId id,FinaleAddress modifier,
    FinaleAddress callback,uint32_t failed,Host& h) {
  h.template put<uint32_t>(modifier+0x2b8,0);
  if (isLastEnding(id)) return h.template call<uint64_t>(0x1247a84,modifier,callback,failed);
  return 0;
}

struct LastProgressCall {
  FinaleAddress site;
  FinaleAddress original;
  uint8_t modifier_register;
};
inline constexpr LastProgressCall last_progress_calls[] = {
  {0x17efb70,0xea4644,19},
  {0x17efb7c,0x1823f40,19},
  {0x16afa94,0xc7bb48,23},
  {0x16afaa0,0x8dd9c4,23},
  {0x1716d74,0xc7bb48,23},
  {0x1716d80,0x8dd9c4,23},
};
// Replay branches skip this entire store+persist block to resume0x1716d68.
inline constexpr FinaleAddress last_reject_progress_block=0x1716ec0;
inline constexpr FinaleAddress last_reject_progress_resume=0x1716d68;
inline constexpr FinaleAddress last_reject_progress_store=0x1716ec8;
inline constexpr FinaleAddress last_reject_progress_persist=0x1716ecc;
static_assert(sizeof(last_progress_calls)/sizeof(last_progress_calls[0])==6);
static_assert(finaleIntroEnabled(0,0,true,true) && finaleIntroEnabled(4,0,true,true));
static_assert(!finaleIntroEnabled(-1,0,true,true) && !finaleIntroEnabled(5,0,true,true));
static_assert(!finaleIntroEnabled(1,1,true,true) && !finaleIntroEnabled(1,0,false,true));
static_assert(!finaleIntroEnabled(1,0,true,false));
} // namespace akaine_official

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
