#pragma once
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
