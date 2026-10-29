#pragma once
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
