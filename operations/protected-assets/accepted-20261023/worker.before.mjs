var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// src/index.mjs
var DEFAULT_ALLOWED_FILES = /* @__PURE__ */ new Set([
  "0.aff",
  "1.aff",
  "2.aff",
  "3.aff",
  "4.aff",
  "base.ogg",
  "3.ogg",
  "4.ogg",
  "preview.ogg",
  "base.jpg",
  "base_256.jpg",
  "1080_base.jpg",
  "1080_base_256.jpg"
]);
var encoder = new TextEncoder();
function hex(bytes) {
  return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
}
__name(hex, "hex");
function timingSafeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) {
    return false;
  }
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}
__name(timingSafeEqual, "timingSafeEqual");
async function hmacHex(secret, payload) {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(payload));
  return hex(new Uint8Array(signature));
}
__name(hmacHex, "hmacHex");
function parseProtectedPath(pathname) {
  const prefix = pathname.startsWith("/protected/songs/") ? "/protected/songs/" : pathname.startsWith("/songs/") ? "/songs/" : null;
  if (!prefix) {
    return null;
  }
  const tail = pathname.slice(prefix.length);
  const parts = tail.split("/");
  if (parts.length !== 2 || !parts[0] || !parts[1]) {
    return null;
  }
  return {
    songId: decodeURIComponent(parts[0]),
    fileName: decodeURIComponent(parts[1])
  };
}
__name(parseProtectedPath, "parseProtectedPath");
function parseLegacySongPath(pathname) {
  const prefix = "/songs/";
  if (!pathname.startsWith(prefix)) {
    return null;
  }
  const tail = pathname.slice(prefix.length);
  const parts = tail.split("/");
  if (parts.length !== 2 || !parts[0] || !parts[1]) {
    return null;
  }
  return {
    songId: decodeURIComponent(parts[0]),
    fileName: decodeURIComponent(parts[1])
  };
}
__name(parseLegacySongPath, "parseLegacySongPath");
function parsePrivateStoragePath(pathname) {
  const prefix = "/private/songs/";
  if (!pathname.startsWith(prefix)) {
    return null;
  }
  const tail = pathname.slice(prefix.length);
  const parts = tail.split("/");
  if (parts.length !== 2 || !parts[0] || !parts[1]) {
    return null;
  }
  return {
    songId: decodeURIComponent(parts[0]),
    fileName: decodeURIComponent(parts[1])
  };
}
__name(parsePrivateStoragePath, "parsePrivateStoragePath");
var RELEASE1002_ASSET_MANIFEST = {"KikaiNoTsubasa":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"SomniomancerNullSet":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"amega_0natsu0":["0.aff","1.aff","2.aff","base.ogg"],"amega_17sai":["0.aff","1.aff","2.aff","base.ogg"],"amega_absurdities":["0.aff","1.aff","2.aff","base.ogg"],"amega_aidenteiteimerutodaun":["0.aff","1.aff","2.aff","base.ogg"],"amega_aidoru":["0.aff","1.aff","2.aff","base.ogg"],"amega_ainozansi":["0.aff","1.aff","2.aff","base.ogg"],"amega_aliceinreitouko":["0.aff","1.aff","2.aff","base.ogg"],"amega_animaru":["0.aff","1.aff","2.aff","base.ogg"],"amega_arkhe":["0.aff","1.aff","2.aff","base.ogg"],"amega_ascensiontoheaven":["0.aff","1.aff","2.aff","base.ogg"],"amega_blueplanet":["0.aff","1.aff","2.aff","base.ogg"],"amega_bluestar":["0.aff","1.aff","2.aff","base.ogg"],"amega_byims":["0.aff","1.aff","2.aff","base.ogg"],"amega_catalinesie":["0.aff","1.aff","2.aff","base.ogg"],"amega_chanyaoge":["0.aff","1.aff","2.aff","3.aff","base.ogg"],"amega_cosmosbt":["0.aff","1.aff","2.aff","base.ogg"],"amega_damidami":["0.aff","1.aff","2.aff","base.ogg"],"amega_daybreakfrontline":["0.aff","1.aff","2.aff","base.ogg"],"amega_doukeinotubasa":["0.aff","1.aff","2.aff","base.ogg"],"amega_dreamflower":["0.aff","1.aff","2.aff","base.ogg"],"amega_echopp":["0.aff","1.aff","2.aff","3.aff","base.ogg"],"amega_eggdrasil":["0.aff","1.aff","2.aff","base.ogg"],"amega_finalresonance":["0.aff","1.aff","2.aff","base.ogg"],"amega_fukakai":["0.aff","1.aff","2.aff","base.ogg"],"amega_hadinotseenthesun":["0.aff","1.aff","2.aff","base.ogg"],"amega_haikeigonenmaenobokue":["0.aff","1.aff","2.aff","base.ogg"],"amega_hananibourei":["0.aff","1.aff","2.aff","base.ogg"],"amega_hananotou":["0.aff","1.aff","2.aff","base.ogg"],"amega_handsup":["0.aff","1.aff","2.aff","3.aff","base.ogg"],"amega_haruurara":["0.aff","1.aff","2.aff","base.ogg"],"amega_hathor":["0.aff","1.aff","2.aff","base.ogg"],"amega_hecatoncheir":["0.aff","1.aff","2.aff","base.ogg"],"amega_hezhe":["0.aff","1.aff","2.aff","base.ogg"],"amega_himegotokuraishisutaazu":["0.aff","1.aff","2.aff","base.ogg"],"amega_hoshinootoshimono":["0.aff","1.aff","2.aff","base.ogg"],"amega_hoshizoratoraberu":["0.aff","1.aff","2.aff","base.ogg"],"amega_hyouryuu":["0.aff","1.aff","2.aff","base.ogg"],"amega_imprisonedxii":["0.aff","1.aff","2.aff","base.ogg"],"amega_inakute":["0.aff","1.aff","2.aff","3.aff","base.ogg"],"amega_inochinikirawareteiru":["0.aff","1.aff","2.aff","base.ogg"],"amega_iyahontosemishigure":["0.aff","1.aff","2.aff","base.ogg"],"amega_jigokuniochiru":["0.aff","1.aff","2.aff","base.ogg"],"amega_kafkapv":["0.aff","1.aff","2.aff","base.ogg"],"amega_kaikou":["0.aff","1.aff","2.aff","base.ogg"],"amega_kizuturai":["0.aff","1.aff","2.aff","base.ogg"],"amega_kokodeikiteru":["0.aff","1.aff","2.aff","base.ogg"],"amega_kousenka":["0.aff","1.aff","2.aff","base.ogg"],"amega_kuusouressha":["0.aff","1.aff","2.aff","base.ogg"],"amega_kyokounotou":["0.aff","1.aff","2.aff","base.ogg"],"amega_kyoukasuigetsu":["0.aff","1.aff","2.aff","base.ogg"],"amega_lavibavellabion":["0.aff","1.aff","2.aff","base.ogg"],"amega_lifeispianoex":["0.aff","1.aff","2.aff","base.ogg"],"amega_machikadotangenttv":["0.aff","1.aff","2.aff","base.ogg"],"amega_mefisuto":["0.aff","1.aff","2.aff","base.ogg"],"amega_moujikinatugaowarukara":["0.aff","1.aff","2.aff","base.ogg"],"amega_murimurisinkaron":["0.aff","1.aff","2.aff","base.ogg"],"amega_musehuixiang":["0.aff","1.aff","2.aff","base.ogg"],"amega_natsuitsuka":["0.aff","1.aff","2.aff","base.ogg"],"amega_natukage":["0.aff","1.aff","2.aff","base.ogg"],"amega_nonbreath1":["0.aff","1.aff","2.aff","base.ogg"],"amega_nonbreath2":["0.aff","1.aff","2.aff","3.aff","base.ogg"],"amega_ongakuwoyameta":["0.aff","1.aff","2.aff","base.ogg"],"amega_ordermade":["0.aff","1.aff","2.aff","base.ogg"],"amega_otokodane":["0.aff","1.aff","2.aff","base.ogg"],"amega_ours":["0.aff","1.aff","2.aff","base.ogg"],"amega_philia093":["0.aff","1.aff","2.aff","base.ogg"],"amega_proi":["0.aff","1.aff","2.aff","base.ogg"],"amega_raisedeaou":["0.aff","1.aff","2.aff","base.ogg"],"amega_ratking":["0.aff","1.aff","2.aff","base.ogg"],"amega_redreamingangel":["0.aff","1.aff","2.aff","3.aff","4.aff","base.ogg"],"amega_ruukii":["0.aff","1.aff","2.aff","base.ogg"],"amega_sanketushoujo":["0.aff","1.aff","2.aff","base.ogg"],"amega_sekainohimitu":["0.aff","1.aff","2.aff","base.ogg"],"amega_seraphim":["0.aff","1.aff","2.aff","base.ogg"],"amega_seventina":["0.aff","1.aff","2.aff","base.ogg"],"amega_shinyahaikai":["0.aff","1.aff","2.aff","base.ogg"],"amega_sidequestking":["0.aff","1.aff","2.aff","base.ogg"],"amega_siturakuen":["0.aff","1.aff","2.aff","base.ogg"],"amega_snowmix":["0.aff","1.aff","2.aff","base.ogg"],"amega_sonnamonne":["0.aff","1.aff","2.aff","base.ogg"],"amega_sonogunjou":["0.aff","1.aff","2.aff","base.ogg"],"amega_soranomusica":["0.aff","1.aff","2.aff","base.ogg"],"amega_sorrowaway":["0.aff","1.aff","2.aff","base.ogg"],"amega_sparkle":["0.aff","1.aff","2.aff","base.ogg"],"amega_sskippu":["0.aff","1.aff","2.aff","base.ogg"],"amega_sugarlife":["0.aff","1.aff","2.aff","base.ogg"],"amega_summertimerecord":["0.aff","1.aff","2.aff","base.ogg"],"amega_supaakuru":["0.aff","1.aff","2.aff","base.ogg"],"amega_suzume":["0.aff","1.aff","2.aff","base.ogg"],"amega_tenkuunohana":["0.aff","1.aff","2.aff","base.ogg"],"amega_tenshitoakumato":["0.aff","1.aff","2.aff","base.ogg"],"amega_thisgame":["0.aff","1.aff","2.aff","3.aff","base.ogg"],"amega_tokimekirendezvoustv":["0.aff","1.aff","2.aff","base.ogg"],"amega_toukyoujoukuu":["0.aff","1.aff","2.aff","3.aff","base.ogg"],"amega_tribios":["0.aff","1.aff","2.aff","base.ogg"],"amega_vanishedbl":["0.aff","1.aff","2.aff","base.ogg"],"amega_vanpaia":["0.aff","1.aff","2.aff","base.ogg"],"amega_vortex":["0.aff","1.aff","base.ogg"],"amega_yoikagentetragon":["0.aff","1.aff","2.aff","base.ogg"],"amega_yoimachicantare":["0.aff","1.aff","2.aff","base.ogg"],"amega_young":["0.aff","1.aff","2.aff","base.ogg"],"amega_zuttosorawomiteita":["0.aff","1.aff","2.aff","base.ogg"],"blackyuzurisa70minmix":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"c2_666669":["0.aff","1.aff","2.aff","base.ogg"],"c2_arcaeden":["kick.wav","0.aff","1.aff","2.aff","4.aff","base.ogg"],"c2_axiumdivergence":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"c2_begleseeker":["0.aff","1.aff","2.aff","base.ogg"],"c2_spoontechsociety":["0.aff","1.aff","2.aff","base.ogg"],"c2_theratf":["0.aff","1.aff","2.aff","base.ogg"],"c2_xnnocence":["0.aff","1.aff","base.ogg"],"deicide":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"dnn_amazingmightyyyy":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"dnn_amazingmighyyyy":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"dnn_androb":["0.aff","1.aff","2.aff","base.ogg"],"dnn_androb_f1aa8498":["0.aff","1.aff","2.aff","base.ogg"],"dnn_aphilosophicalwanderer":["0.aff","1.aff","2.aff","base.ogg"],"dnn_arqeid":["0.aff","1.aff","2.aff","base.ogg"],"dnn_bbb":["0.aff","1.aff","2.aff","base.ogg"],"dnn_beaflower":["0.aff","1.aff","2.aff","base.ogg"],"dnn_blazingair":["0.aff","1.aff","2.aff","base.ogg"],"dnn_carrot":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"dnn_chantsayyeah":["0.aff","1.aff","2.aff","base.ogg"],"dnn_chasing":["0.aff","1.aff","2.aff","base.ogg"],"dnn_crowdedourcity":["0.aff","1.aff","2.aff","base.ogg"],"dnn_dashi":["0.aff","1.aff","2.aff","base.ogg"],"dnn_elusive":["0.aff","1.aff","2.aff","base.ogg"],"dnn_emancipator":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"dnn_farawaylight":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"dnn_feixingzhi":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"dnn_glitchinmysystem":["0.aff","1.aff","2.aff","base.ogg"],"dnn_glitchnerds":["0.aff","1.aff","2.aff","base.ogg"],"dnn_guinevere":["0.aff","1.aff","2.aff","base.ogg"],"dnn_hexperus":["0.aff","1.aff","2.aff","base.ogg"],"dnn_hhh":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"dnn_huoyuanjia":["0.aff","1.aff","2.aff","base.ogg"],"dnn_hyp3rtribe":["0.aff","1.aff","2.aff","base.ogg"],"dnn_iidx":["0.aff","1.aff","2.aff","base.ogg"],"dnn_infbit":["0.aff","1.aff","2.aff","base.ogg"],"dnn_issen":["0.aff","1.aff","2.aff","base.ogg"],"dnn_itsbeensolong":["0.aff","1.aff","2.aff","base.ogg"],"dnn_jinitaimei":["0.aff","1.aff","2.aff","base.ogg"],"dnn_kalacakla":["0.aff","1.aff","2.aff","base.ogg"],"dnn_kungfuemp":["0.aff","1.aff","2.aff","base.ogg"],"dnn_lance":["0.aff","1.aff","2.aff","base.ogg"],"dnn_landscape":["0.aff","1.aff","2.aff","base.ogg"],"dnn_liftoff_d4084bed":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"dnn_melodyoflove":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"dnn_midnightlady_aki":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"dnn_minazuki":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"dnn_moonglow":["0.aff","1.aff","2.aff","base.ogg"],"dnn_n3v3r_g3t_ov3r":["0.aff","1.aff","2.aff","base.ogg"],"dnn_newrules":["0.aff","1.aff","2.aff","base.ogg"],"dnn_nighttheateretude":["0.aff","1.aff","2.aff","base.ogg"],"dnn_noscope":["0.aff","1.aff","2.aff","base.ogg"],"dnn_oldgold":["0.aff","1.aff","2.aff","base.ogg"],"dnn_peachpit":["0.aff","1.aff","2.aff","base.ogg"],"dnn_radianceofdream":["0.aff","1.aff","2.aff","base.ogg"],"dnn_ray":["0.aff","1.aff","2.aff","base.ogg"],"dnn_requillio":["0.aff","1.aff","2.aff","base.ogg"],"dnn_rio7ous":["0.aff","1.aff","2.aff","base.ogg"],"dnn_rnrmonsta":["0.aff","1.aff","2.aff","base.ogg"],"dnn_saintelmo":["0.aff","1.aff","2.aff","base.ogg"],"dnn_sakuramaze":["0.aff","1.aff","2.aff","base.ogg"],"dnn_sendan_life":["0.aff","1.aff","2.aff","base.ogg"],"dnn_sendan_life_7ecc9c22":["0.aff","1.aff","2.aff","base.ogg"],"dnn_sequencebreaker":["0.aff","1.aff","2.aff","base.ogg"],"dnn_sparkle":["0.aff","1.aff","2.aff","base.ogg"],"dnn_specta":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"dnn_speculation":["0.aff","1.aff","2.aff","base.ogg"],"dnn_speedking":["0.aff","1.aff","2.aff","base.ogg"],"dnn_starq":["0.aff","1.aff","2.aff","base.ogg"],"dnn_stresstest":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"dnn_stresstest_b3dce6cc":["0.aff","1.aff","2.aff","base.ogg"],"dnn_submergeserenade":["0.aff","1.aff","2.aff","base.ogg"],"dnn_synthesis":["0.aff","1.aff","2.aff","base.ogg"],"dnn_theprimaryplasm":["0.aff","1.aff","2.aff","base.ogg"],"dnn_toli":["0.aff","1.aff","2.aff","base.ogg"],"dnn_traxxendenza":["0.aff","1.aff","2.aff","base.ogg"],"dnn_truthseeker":["0.aff","1.aff","2.aff","base.ogg"],"dnn_ververg":["0.aff","1.aff","2.aff","base.ogg"],"dnn_violetcorner":["0.aff","1.aff","2.aff","base.ogg"],"dnn_wilt":["0.aff","1.aff","2.aff","base.ogg"],"dnn_withmylastbreath":["0.aff","1.aff","2.aff","base.ogg"],"dnn_zitronectar":["0.aff","1.aff","2.aff","base.ogg"],"doomsdaythundertempest":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"duplicityshade":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"findersx_9876734123":["0.aff","1.aff","2.aff","base.ogg"],"findersx_adastraperaspera":["0.aff","1.aff","2.aff","base.ogg"],"findersx_anima":["0.aff","1.aff","2.aff","base.ogg"],"findersx_anohianoheya":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"findersx_aphasia_tg":["0.aff","1.aff","2.aff","base.ogg"],"findersx_apocalypsenow":["0.aff","1.aff","2.aff","base.ogg"],"findersx_astronomia":["0.aff","1.aff","2.aff","base.ogg"],"findersx_believelight":["0.aff","1.aff","2.aff","base.ogg"],"findersx_berrygo":["0.aff","1.aff","2.aff","base.ogg"],"findersx_bloodypurity":["0.aff","1.aff","2.aff","base.ogg"],"findersx_boundedquietude":["0.aff","1.aff","2.aff","base.ogg"],"findersx_cirnosperfectmath":["0.aff","1.aff","2.aff","base.ogg"],"findersx_daichinisakusenritsu":["0.aff","1.aff","2.aff","base.ogg"],"findersx_dancerofsaramandora":["0.aff","1.aff","2.aff","base.ogg"],"findersx_dangeroooousjungle":["0.aff","1.aff","2.aff","base.ogg"],"findersx_danzai":["0.aff","1.aff","2.aff","base.ogg"],"findersx_defection":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"findersx_disappearance":["0.aff","1.aff","2.aff","base.ogg"],"findersx_dontletyoudown":["0.aff","1.aff","2.aff","base.ogg"],"findersx_endtime":["0.aff","1.aff","2.aff","base.ogg"],"findersx_epicsaxguy":["0.aff","1.aff","2.aff","base.ogg"],"findersx_etabetaita":["0.aff","1.aff","2.aff","base.ogg"],"findersx_felysfinalremix":["0.aff","1.aff","2.aff","base.ogg"],"findersx_gekka":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"findersx_ghostrule":["0.aff","1.aff","2.aff","base.ogg"],"findersx_hatsunemikunogekishou":["0.aff","1.aff","2.aff","base.ogg"],"findersx_helpmeerin":["0.aff","1.aff","2.aff","base.ogg"],"findersx_imustsayno":["0.aff","1.aff","2.aff","base.ogg"],"findersx_infinityheaven":["0.aff","1.aff","2.aff","base.ogg"],"findersx_internetsurvivor":["0.aff","1.aff","2.aff","base.ogg","boom.wav"],"findersx_jinsei":["0.aff","1.aff","2.aff","base.ogg"],"findersx_kamipoina":["0.aff","1.aff","2.aff","base.ogg"],"findersx_kokushimusou":["0.aff","1.aff","2.aff","base.ogg"],"findersx_kusaregedou":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"findersx_latentkingdom":["0.aff","1.aff","2.aff","base.ogg"],"findersx_loveriver":["0.aff","1.aff","2.aff","base.ogg"],"findersx_matsuyoinightbug":["0.aff","1.aff","2.aff","base.ogg"],"findersx_neverland":["0.aff","1.aff","2.aff","base.ogg","arc.wav"],"findersx_nightofknightsrmx":["0.aff","1.aff","2.aff","base.ogg"],"findersx_nonbreathoblige":["0.aff","1.aff","2.aff","base.ogg"],"findersx_nosferatu":["0.aff","1.aff","2.aff","base.ogg"],"findersx_onandon":["0.aff","1.aff","2.aff","base.ogg"],"findersx_ourovoros":["0.aff","1.aff","2.aff","base.ogg"],"findersx_palescreen":["0.aff","1.aff","2.aff","base.ogg"],"findersx_quiq":["0.aff","1.aff","2.aff","base.ogg"],"findersx_qzkagorequiem":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"findersx_qzkagorequiem_16ccf932":["0.aff","1.aff","2.aff","base.ogg"],"findersx_radiance":["0.aff","1.aff","2.aff","base.ogg"],"findersx_raidboss":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"findersx_reendofadream":["0.aff","1.aff","2.aff","base.ogg"],"findersx_requiemcataclysm":["0.aff","1.aff","2.aff","base.ogg"],"findersx_retribution":["0.aff","1.aff","2.aff","base.ogg","voice.wav"],"findersx_sacredruin":["0.aff","1.aff","2.aff","base.ogg"],"findersx_sanctuary":["0.aff","1.aff","2.aff","base.ogg"],"findersx_senior3":["0.aff","1.aff","2.aff","base.ogg"],"findersx_shadowshape":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"findersx_shinkaishoujo":["0.aff","1.aff","2.aff","base.ogg"],"findersx_shuuten":["0.aff","1.aff","2.aff","base.ogg"],"findersx_song":["0.aff","1.aff","2.aff","base.ogg"],"findersx_tempestla":["0.aff","1.aff","2.aff","base.ogg"],"findersx_tenkuunoyoake":["0.aff","1.aff","2.aff","base.ogg"],"findersx_terrasphere":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"findersx_tetris":["0.aff","1.aff","2.aff","base.ogg"],"findersx_thesamsara":["0.aff","1.aff","2.aff","base.ogg"],"findersx_tiamat":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"findersx_tokumei":["0.aff","1.aff","2.aff","base.ogg"],"findersx_unleashedworld":["0.aff","1.aff","2.aff","base.ogg"],"findersx_valkyrierevolutia":["0.aff","1.aff","2.aff","base.ogg"],"findersx_vengeanceofthev":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"findersx_vertexbeta":["0.aff","1.aff","2.aff","base.ogg"],"findersx_viiibitexplorer":["0.aff","1.aff","2.aff","base.ogg"],"findersx_viyella_s_melancholy":["0.aff","1.aff","2.aff","base.ogg"],"findersx_viyellasdestiny":["0.aff","1.aff","2.aff","base.ogg"],"findersx_wizdomiot":["0.aff","1.aff","2.aff","base.ogg"],"findersx_worldsendloneliness":["0.aff","1.aff","2.aff","base.ogg"],"findersx_xaleidscopix":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"findersx_zenmaishoujodokei":["0.aff","1.aff","2.aff","base.ogg"],"heatabnormal":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"ifinfinity":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"itz62gd_alteregou":["0.aff","1.aff","2.aff","base.ogg","bisa.wav","wha.wav"],"itz62gd_arc":["0.aff","1.aff","2.aff","base.ogg","ex.wav"],"itz62gd_arcaholy":["0.aff","1.aff","2.aff","base.ogg"],"itz62gd_btt":["0.aff","1.aff","2.aff","base.ogg","none.wav"],"itz62gd_crazy":["0.aff","1.aff","2.aff","base.ogg"],"itz62gd_desiveeeee":["0.aff","1.aff","2.aff","base.ogg"],"itz62gd_disgusting":["bao.wav","bruh.wav","gangguan.wav","xianbei.wav","zhsa.wav","0.aff","1.aff","2.aff","base.ogg"],"itz62gd_dlm":["0.aff","1.aff","2.aff","base.ogg"],"itz62gd_fart":["0.aff","1.aff","2.aff","base.ogg","ex.wav"],"itz62gd_ifieee":["0.aff","1.aff","2.aff","base.ogg","argh.wav","bruh.wav","zhuyikan.wav"],"itz62gd_jx":["0.aff","1.aff","2.aff","base.ogg","none.wav"],"itz62gd_lajinv":["0.aff","1.aff","2.aff","base.ogg"],"itz62gd_lost_far_dl_young":["0.aff","1.aff","2.aff","base.ogg","ex.wav","gangguan.wav"],"itz62gd_maxsad_itz62igd":["0.aff","1.aff","2.aff","base.ogg"],"itz62gd_mowang":["0.aff","1.aff","2.aff","base.ogg"],"itz62gd_oshab":["0.aff","1.aff","2.aff","base.ogg"],"itz62gd_pee":["0.aff","1.aff","2.aff","base.ogg","none.wav"],"itz62gd_qzk":["0.aff","1.aff","2.aff","base.ogg"],"itz62gd_r":["0.aff","1.aff","2.aff","base.ogg","augh.wav","bruh.wav","none.wav"],"itz62gd_szhh":["0.aff","1.aff","2.aff","base.ogg","none.wav"],"itz62gd_teeeeera":["0.aff","1.aff","2.aff","base.ogg"],"itz62gd_wv":["0.aff","1.aff","2.aff","base.ogg"],"itz62gd_zuiqiang":["0.aff","1.aff","2.aff","base.ogg"],"jtapper_trick_heart":["0.aff","1.aff","2.aff","base.ogg"],"killa_death_ay":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"mythsorbis":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"phenoph_duplicityshade":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"phenoph_mythsorbis":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"qzkagorequiem":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"rez129_accelerate":["0.aff","1.aff","2.aff","base.ogg"],"rez129_anc2025s":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"rez129_anc2025s_8a57e9c0":["0.aff","1.aff","2.aff","base.ogg"],"rez129_antinomicqueen":["0.aff","1.aff","2.aff","base.ogg"],"rez129_assaulting":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"rez129_assaulting_a528cfe7":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"rez129_beirshuang":["0.aff","1.aff","2.aff","base.ogg"],"rez129_cantare":["0.aff","1.aff","2.aff","base.ogg"],"rez129_csqn":["zaijian.wav","0.aff","1.aff","2.aff","4.aff","base.ogg"],"rez129_cyberattack":["0.aff","1.aff","2.aff","base.ogg"],"rez129_cyberneticvampire":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"rez129_darkdragonfire":["0.aff","1.aff","2.aff","base.ogg"],"rez129_digitallifehacker":["0.aff","1.aff","2.aff","base.ogg"],"rez129_eureka":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"rez129_foolishofme":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"rez129_furendoshitai":["0.aff","1.aff","2.aff","base.ogg"],"rez129_futarinostartbutton":["0.aff","1.aff","2.aff","base.ogg"],"rez129_galaxyeggplant":["0.aff","1.aff","2.aff","base.ogg"],"rez129_gloxinia":["0.aff","1.aff","2.aff","base.ogg"],"rez129_hanabi":["0.aff","1.aff","2.aff","base.ogg"],"rez129_harvestmoonnight":["0.aff","1.aff","2.aff","base.ogg"],"rez129_heracles":["0.aff","1.aff","2.aff","base.ogg"],"rez129_higashi":["0.aff","1.aff","2.aff","base.ogg"],"rez129_hop":["0.aff","1.aff","2.aff","base.ogg","hop.wav","ma.wav","qlosso.wav","suck.wav","wmas.wav","yexue.wav"],"rez129_hugandkill":["0.aff","1.aff","2.aff","base.ogg"],"rez129_innocentarrogance":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"rez129_inorganyxprayer":["0.aff","1.aff","2.aff","base.ogg"],"rez129_kaiminanmin":["0.aff","1.aff","2.aff","base.ogg"],"rez129_kakuen":["0.aff","1.aff","2.aff","base.ogg"],"rez129_khronostasiskatharsis":["0.aff","1.aff","2.aff","base.ogg"],"rez129_lanota_vibeyvibey_9_9":["0.aff","1.aff","2.aff","base.ogg"],"rez129_liar":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"rez129_liar_23b9ab7a":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"rez129_lostcivilization":["0.aff","1.aff","2.aff","4.aff","base.ogg","Alert.wav","fail.wav","goofyahh.wav","q.wav"],"rez129_love2000":["0.aff","1.aff","2.aff","base.ogg"],"rez129_memoria":["0.aff","1.aff","2.aff","base.ogg"],"rez129_memories":["0.aff","1.aff","2.aff","base.ogg"],"rez129_moonofnoon":["0.aff","1.aff","2.aff","base.ogg","Alert.wav","COCACOLAESPUMA.wav","OOF.wav","OOF10.wav","OOF11.wav","OOF13.wav","OOF15.wav","OOF16.wav","OOF2.wav","OOF3.wav","OOF4.wav","OOF5.wav","OOF6.wav","OOF7.wav","OOF8.wav","OOF9.wav","aur.wav","bbb.wav","bruh.wav","bruh2.wav","goofyahh.wav","isntthatamazing.wav","n0n.wav","n1n.wav","wys2x.wav"],"rez129_namelesspassion":["0.aff","1.aff","2.aff","base.ogg"],"rez129_niebelungen":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"rez129_panicbounceattack":["0.aff","1.aff","2.aff","base.ogg"],"rez129_realworld":["0.aff","1.aff","2.aff","base.ogg"],"rez129_replayandaction":["0.aff","1.aff","2.aff","base.ogg"],"rez129_romiandrobotsspacetravel":["0.aff","1.aff","2.aff","base.ogg"],"rez129_sayonaraplanetwars":["0.aff","1.aff","2.aff","base.ogg"],"rez129_seraphim_anf":["0.aff","1.aff","2.aff","base.ogg"],"rez129_shikashikidays":["0.aff","1.aff","2.aff","base.ogg"],"rez129_sparkle":["0.aff","1.aff","2.aff","base.ogg"],"rez129_spearofjusticemrmremix":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"rez129_speculation":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"rez129_spiderdance":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"rez129_spiderdance_3b837ae9":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"rez129_synthesizedangel":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"rez129_takenohana":["0.aff","1.aff","2.aff","base.ogg"],"rez129_themiracleofamethyst":["0.aff","1.aff","2.aff","base.ogg"],"rez129_theotherside":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"rez129_tokyoteddybear":["0.aff","1.aff","2.aff","base.ogg"],"rez129_torinoshi":["0.aff","1.aff","2.aff","base.ogg"],"rez129_ultimateforce":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"rez129_umikazemoment":["0.aff","1.aff","2.aff","base.ogg"],"rez129_unexpectederror_9_4":["0.aff","1.aff","2.aff","base.ogg"],"rez129_untroddenmorn":["0.aff","1.aff","2.aff","base.ogg"],"rez129_youmakemylife1up":["0.aff","1.aff","2.aff","base.ogg"],"seishunno_hacking":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"shuuten":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"silentlight":["0.aff","1.aff","2.aff","base.ogg"],"singlepack_silent_light_ftr_9":["0.aff","1.aff","2.aff","base.ogg"],"sp87_321":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"sp87_414perspeed":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"sp87_ambivalence":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"sp87_ascent":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"sp87_chushan":["0.aff","1.aff","2.aff","base.ogg"],"sp87_daisuke":["0.aff","1.aff","2.aff","base.ogg"],"sp87_danceroftheend":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"sp87_daydream":["0.aff","1.aff","2.aff","base.ogg"],"sp87_disorder":["0.aff","1.aff","2.aff","base.ogg"],"sp87_fractureray":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"sp87_fuliautoshooter":["0.aff","1.aff","2.aff","base.ogg"],"sp87_grabinschriftdergotter":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"sp87_hydra":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"sp87_invisibledragon":["0.aff","1.aff","2.aff","base.ogg"],"sp87_letsrockroaringmix":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"sp87_luminousentitieslostheart":["0.aff","1.aff","2.aff","base.ogg"],"sp87_occhocorestless":["0.aff","1.aff","2.aff","base.ogg"],"sp87_odysseia":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"sp87_opia":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"sp87_rabbitintheblackroom":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"sp87_reimei":["0.aff","1.aff","2.aff","base.ogg"],"sp87_rgb":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"sp87_rushhour":["0.aff","1.aff","2.aff","base.ogg"],"sp87_secretillumination":["0.aff","1.aff","2.aff","base.ogg"],"sp87_sparklenewlife":["0.aff","1.aff","2.aff","base.ogg"],"sp87_squarelake":["0.aff","1.aff","2.aff","base.ogg"],"sp87_stardust_ray":["0.aff","1.aff","2.aff","base.ogg"],"sp87_theatorecreatore":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"sp87_tiamat":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"sp87_valhallazero":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"sp87_valsqotch":["0.aff","1.aff","2.aff","base.ogg"],"sp87_wolgallon":["0.aff","1.aff","2.aff","base.ogg"],"sp87_worldsendloneliness":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"sptx_altair":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"sptx_cilpher":["0.aff","1.aff","2.aff","base.ogg"],"sptx_cr":["0.aff","1.aff","2.aff","base.ogg"],"sptx_doki":["0.aff","1.aff","2.aff","base.ogg"],"sptx_ed3":["0.aff","1.aff","2.aff","base.ogg"],"sptx_eligos":["0.aff","1.aff","2.aff","base.ogg"],"sptx_eq":["0.aff","1.aff","2.aff","base.ogg"],"sptx_exxtrajudgement":["0.aff","1.aff","2.aff","base.ogg"],"sptx_felys":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"sptx_galaxyblaster_by_sptxzx_ftr10":["0.aff","1.aff","2.aff","base.ogg"],"sptx_genocide_saw_heaven":["0.aff","1.aff","2.aff","base.ogg"],"sptx_heilenwelt":["0.aff","1.aff","2.aff","base.ogg"],"sptx_ine":["0.aff","1.aff","2.aff","base.ogg"],"sptx_kaleidoscope":["0.aff","1.aff","2.aff","base.ogg"],"sptx_kotonoha":["0.aff","1.aff","2.aff","base.ogg"],"sptx_rice_fragrance":["0.aff","1.aff","2.aff","base.ogg"],"sptx_ringskycore":["0.aff","1.aff","2.aff","base.ogg"],"sptx_shadesoflight":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"sptx_song":["0.aff","1.aff","2.aff","base.ogg"],"testify1":["base.ogg","0.aff","1.aff","2.aff","3.aff","3.official615.aff"],"unlucky_worldseclipse":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_anti_corruption_byd_11":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"vegchi_astertale":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_breakingdawn":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"vegchi_brightness_ftr8":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_crimsonate":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_ego_eimi_long_ver":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_elysian":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_etr10":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"vegchi_eve_avenir_byd":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"vegchi_eveavenir":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"vegchi_everlasting_eternity":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_exotogibanashi":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"vegchi_flapclap":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"vegchi_ftr9":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_heartache":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_hot_limit":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_imitator":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_loschen":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"vegchi_lost_str3ngth":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_milkyway":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_milkyway_3abf9a48":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_namelesspassion":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"vegchi_paradox_in_the_mirror_ftr10":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_prosperite":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_ray_future_9":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_return_to_bloom":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"vegchi_secretillumination_vegchi":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_seishunno_hacking_1":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"vegchi_song":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"vegchi_song_1f69a245":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_song_27407a19":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_song_59390146":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"vegchi_song_ed6ab49e":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_starlit_doze":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"vegchi_starrycolors_10":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_stellalude":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_taohuan":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_urur_u_l_u_lu":["0.aff","1.aff","2.aff","base.ogg"],"vegchi_yimenghongchen_future_9":["0.aff","1.aff","2.aff","base.ogg"],"vengeanceofthev":["0.aff","1.aff","2.aff","4.aff","base.ogg"],"xaleidscopix":["0.aff","1.aff","2.aff","4.aff","base.ogg"]};
function parseManifest(env) {
  return RELEASE1002_ASSET_MANIFEST;
}
__name(parseManifest, "parseManifest");
function allowedPrefixes(env) {
  return String(env.ASSET_SONG_ID_PREFIXES || "").split(",").map((value) => value.trim()).filter(Boolean);
}
__name(allowedPrefixes, "allowedPrefixes");
function hasAllowedPrefix(env, songId) {
  return allowedPrefixes(env).some((prefix) => songId.startsWith(prefix));
}
__name(hasAllowedPrefix, "hasAllowedPrefix");
function isFanSong(env, songId) {
  const manifest = parseManifest(env);
  return Boolean(
    manifest && Object.prototype.hasOwnProperty.call(manifest, songId) && Array.isArray(manifest[songId]) || hasAllowedPrefix(env, songId)
  );
}
__name(isFanSong, "isFanSong");
function isFileAllowed(env, songId, fileName) {
  const manifest = parseManifest(env);
  if (manifest) {
    const files = manifest[songId];
    if (Array.isArray(files)) return files.includes(fileName);
    if (hasAllowedPrefix(env, songId)) return DEFAULT_ALLOWED_FILES.has(fileName);
    return false;
  }
  return DEFAULT_ALLOWED_FILES.has(fileName);
}
__name(isFileAllowed, "isFileAllowed");
function contentType(fileName) {
  if (fileName.endsWith(".ogg")) return "audio/ogg";
  if (fileName.endsWith(".aff")) return "text/plain; charset=utf-8";
  if (fileName.endsWith(".jpg") || fileName.endsWith(".jpeg")) return "image/jpeg";
  if (fileName.endsWith(".mp4")) return "video/mp4";
  return "application/octet-stream";
}
__name(contentType, "contentType");
async function verifySignedRequest(request, env, nowSeconds = null) {
  const url = new URL(request.url);
  const parsed = parseProtectedPath(url.pathname);
  if (!parsed) {
    return { ok: false, status: 404, reason: "not_found" };
  }
  const compactToken = url.searchParams.get("t") || "";
  if (compactToken) {
    const [uid2 = "", exp2 = "", sig2 = ""] = compactToken.split(".");
    if (!uid2 || !exp2 || !sig2 || compactToken.split(".").length !== 3) {
      return { ok: false, status: 403, reason: "missing_signature_fields", ...parsed };
    }
    const expNumber2 = Number(exp2);
    const now2 = nowSeconds == null ? Math.floor(Date.now() / 1e3) : nowSeconds;
    if (!Number.isFinite(expNumber2) || expNumber2 <= now2) {
      return { ok: false, status: 403, reason: "expired", uid: uid2, ...parsed };
    }
    if (!env.ASSET_SIGNING_SECRET) {
      return { ok: false, status: 500, reason: "missing_worker_secret", uid: uid2, ...parsed };
    }
    if (!isFileAllowed(env, parsed.songId, parsed.fileName)) {
      return { ok: false, status: 403, reason: "file_not_allowed", uid: uid2, ...parsed };
    }
    const payload2 = [
      request.method.toUpperCase(),
      url.pathname,
      uid2,
      parsed.songId,
      parsed.fileName,
      exp2
    ].join("\n");
    const expected2 = (await hmacHex(env.ASSET_SIGNING_SECRET, payload2)).slice(0, 32);
    if (!timingSafeEqual(expected2, sig2)) {
      return { ok: false, status: 403, reason: "bad_signature", uid: uid2, ...parsed };
    }
    return { ok: true, uid: uid2, exp: expNumber2, nonce: null, ...parsed };
  }
  const uid = url.searchParams.get("uid") || "";
  const exp = url.searchParams.get("exp") || "";
  const nonce = url.searchParams.get("nonce") || "";
  const sig = url.searchParams.get("sig") || "";
  if (!uid || !exp || !nonce || !sig) {
    return { ok: false, status: 403, reason: "missing_signature_fields", ...parsed };
  }
  const expNumber = Number(exp);
  const now = nowSeconds == null ? Math.floor(Date.now() / 1e3) : nowSeconds;
  if (!Number.isFinite(expNumber) || expNumber <= now) {
    return { ok: false, status: 403, reason: "expired", uid, ...parsed };
  }
  if (!env.ASSET_SIGNING_SECRET) {
    return { ok: false, status: 500, reason: "missing_worker_secret", uid, ...parsed };
  }
  if (!isFileAllowed(env, parsed.songId, parsed.fileName)) {
    return { ok: false, status: 403, reason: "file_not_allowed", uid, ...parsed };
  }
  const payload = [
    request.method.toUpperCase(),
    url.pathname,
    uid,
    parsed.songId,
    parsed.fileName,
    exp,
    nonce
  ].join("\n");
  const expected = await hmacHex(env.ASSET_SIGNING_SECRET, payload);
  if (!timingSafeEqual(expected, sig)) {
    return { ok: false, status: 403, reason: "bad_signature", uid, ...parsed };
  }
  return { ok: true, uid, exp: expNumber, nonce, ...parsed };
}
__name(verifySignedRequest, "verifySignedRequest");
function anonymizeIp(ip) {
  if (!ip) return "unknown";
  if (ip.includes(".")) {
    const parts = ip.split(".");
    if (parts.length === 4) {
      parts[3] = "0";
      return parts.join(".");
    }
  }
  if (ip.includes(":")) {
    return `${ip.split(":").slice(0, 3).join(":")}::/48`;
  }
  return "unknown";
}
__name(anonymizeIp, "anonymizeIp");
function audit(env, request, result, status) {
  const requestId = request.headers.get("cf-ray") || crypto.randomUUID();
  const event = {
    event: "asset_download",
    status,
    reason: result.reason || "ok",
    uid: result.uid || null,
    song_id: result.songId || null,
    file_name: result.fileName || null,
    request_id: requestId,
    ip_prefix: anonymizeIp(request.headers.get("cf-connecting-ip")),
    asn: String(request.cf?.asn || "unknown"),
    country: request.cf?.country || "unknown",
    colo: request.cf?.colo || "unknown",
    method: request.method.toUpperCase(),
    timestamp: (/* @__PURE__ */ new Date()).toISOString()
  };
  console.log(JSON.stringify(event));
  if (env.ASSET_AUDIT) {
    env.ASSET_AUDIT.writeDataPoint({
      indexes: [event.song_id || "_invalid"],
      blobs: [
        event.event,
        String(event.status),
        event.reason,
        event.uid || "unknown",
        event.song_id || "unknown",
        event.file_name || "unknown",
        event.request_id,
        event.ip_prefix,
        event.asn,
        event.country,
        event.colo,
        event.method
      ],
      doubles: [event.status]
    });
  }
}
__name(audit, "audit");

var PRIVATE_CACHE_MAX_BYTES = 33554432;
function parseSingleRange(value, totalSize) {
  if (!value) return null;
  if (!Number.isSafeInteger(totalSize) || totalSize < 0) return { invalid: true };
  const match = /^bytes=(\d*)-(\d*)$/i.exec(value.trim());
  if (!match || !match[1] && !match[2]) return { invalid: true };
  if (!match[1]) {
    const suffixLength = Number(match[2]);
    if (!Number.isSafeInteger(suffixLength) || suffixLength <= 0 || totalSize === 0) return { invalid: true };
    const length = Math.min(suffixLength, totalSize);
    return { offset: totalSize - length, length };
  }
  const offset = Number(match[1]);
  const requestedEnd = match[2] ? Number(match[2]) : totalSize - 1;
  if (!Number.isSafeInteger(offset) || !Number.isSafeInteger(requestedEnd) || offset < 0 || requestedEnd < offset || offset >= totalSize) return { invalid: true };
  const end = Math.min(requestedEnd, totalSize - 1);
  return { offset, length: end - offset + 1 };
}
__name(parseSingleRange, "parseSingleRange");
function assetHeaders(object, fileName) {
  const headers = new Headers();
  headers.set("Content-Type", object.httpMetadata?.contentType || contentType(fileName));
  headers.set("Cache-Control", "private, max-age=300");
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("Accept-Ranges", "bytes");
  if (object.httpEtag) headers.set("ETag", object.httpEtag);
  return headers;
}
__name(assetHeaders, "assetHeaders");
function canonicalAssetUrl(url) {
  const canonical = new URL(url.toString());
  canonical.search = "";
  canonical.hash = "";
  return canonical.toString();
}
__name(canonicalAssetUrl, "canonicalAssetUrl");
function cacheRequestFor(url, rangeHeader) {
  const headers = new Headers();
  if (rangeHeader) headers.set("Range", rangeHeader);
  return new Request(canonicalAssetUrl(url), { method: "GET", headers });
}
__name(cacheRequestFor, "cacheRequestFor");
function privateCachedResponse(cached, method) {
  const headers = new Headers(cached.headers);
  headers.set("Cache-Control", "private, max-age=300");
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("Accept-Ranges", "bytes");
  return new Response(method === "HEAD" ? null : cached.body, { status: cached.status, headers });
}
__name(privateCachedResponse, "privateCachedResponse");
var index_default = {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const privateStorage = parsePrivateStoragePath(url.pathname);
    if (privateStorage) {
      audit(env, request, {
        ...privateStorage,
        reason: "private_storage_path_disabled"
      }, 403);
      return new Response("private_storage_path_disabled", { status: 403 });
    }
    const legacy = parseLegacySongPath(url.pathname);
    const legacyFan = legacy && isFanSong(env, legacy.songId);
    const hasSignature = ["t", "uid", "exp", "nonce", "sig"].some((key2) => url.searchParams.has(key2));
    if (legacyFan && !hasSignature) {
      audit(env, request, {
        ...legacy,
        reason: "legacy_public_path_disabled"
      }, 403);
      return new Response("legacy_public_path_disabled", { status: 403 });
    }
    if (legacy && !legacyFan) {
      audit(env, request, { reason: "not_found" }, 404);
      return new Response("not_found", { status: 404 });
    }
    if (request.method !== "GET" && request.method !== "HEAD") {
      audit(env, request, {
        ...parseProtectedPath(url.pathname) || {},
        reason: "method_not_allowed"
      }, 405);
      return new Response("method not allowed", { status: 405 });
    }
    const verified = await verifySignedRequest(request, env);
    if (!verified.ok) {
      audit(env, request, verified, verified.status);
      return new Response(verified.reason, { status: verified.status });
    }
    const key = `private/songs/${verified.songId}/${verified.fileName}`;
    const rangeHeader = request.headers.get("Range");
    const cache = caches.default;
    const cacheRequest = cacheRequestFor(url, rangeHeader);
    if (request.method === "GET" && !rangeHeader) {
      try {
        const cached = await cache.match(cacheRequest);
        if (cached && cached.status >= 200 && cached.status < 300) {
          audit(env, request, { ...verified, reason: "cache_hit" }, cached.status);
          return privateCachedResponse(cached, request.method);
        }
      } catch (error) {
        console.error(JSON.stringify({ event: "asset_cache_read_error", song_id: verified.songId, file_name: verified.fileName, message: String(error) }));
      }
    }
    let object;
    try {
      object = rangeHeader
        ? await env.AKAINE_ASSETS.get(key, { range: request.headers })
        : await env.AKAINE_ASSETS.get(key);
    } catch (error) {
      console.error(JSON.stringify({ event: "asset_gateway_error", song_id: verified.songId, file_name: verified.fileName, message: String(error) }));
      audit(env, request, { ...verified, reason: "r2_gateway_error" }, 502);
      return new Response("asset gateway unavailable", { status: 502 });
    }
    if (!object) {
      audit(env, request, { ...verified, reason: "r2_not_found" }, 404);
      return new Response("not found", { status: 404 });
    }
    if (!object.body) {
      audit(env, request, { ...verified, reason: "r2_body_unavailable" }, 502);
      return new Response("asset body unavailable", { status: 502 });
    }
    const headers = assetHeaders(object, verified.fileName);
    if (rangeHeader) {
      const objectRange = object.range;
      if (!objectRange || !Number.isSafeInteger(objectRange.offset) || !Number.isSafeInteger(objectRange.length) || objectRange.length <= 0) {
        headers.set("Content-Range", `bytes */${object.size}`);
        headers.set("Content-Length", "0");
        audit(env, request, { ...verified, reason: "range_not_satisfiable" }, 416);
        return new Response(null, { status: 416, headers });
      }
      const end = objectRange.offset + objectRange.length - 1;
      headers.set("Content-Range", `bytes ${objectRange.offset}-${end}/${object.size}`);
      headers.set("Content-Length", String(objectRange.length));
      audit(env, request, verified, 206);
      return new Response(request.method === "HEAD" ? null : object.body, { status: 206, headers });
    }
    headers.set("Content-Length", String(object.size));
    if (request.method === "HEAD") {
      audit(env, request, verified, 200);
      return new Response(null, { status: 200, headers });
    }
    const response = new Response(object.body, { status: 200, headers });
    if (object.size <= PRIVATE_CACHE_MAX_BYTES) {
      const cachedHeaders = new Headers(headers);
      cachedHeaders.set("Cache-Control", "public, s-maxage=86400");
      const cacheKey = new Request(canonicalAssetUrl(url), { method: "GET" });
      const cacheResponse = new Response(response.clone().body, { status: 200, headers: cachedHeaders });
      ctx.waitUntil(cache.put(cacheKey, cacheResponse));
    }
    audit(env, request, verified, 200);
    return response;
  }
};
export {
  index_default as default,
  hmacHex,
  parseLegacySongPath,
  parsePrivateStoragePath,
  parseProtectedPath,
  verifySignedRequest
};
//# sourceMappingURL=index.js.map
