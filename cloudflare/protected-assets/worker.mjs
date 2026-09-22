const encoder = new TextEncoder();
let manifestCache;
let manifestCacheExpiresAt = 0;
const PRIVATE_CACHE_MAX_BYTES = 32 * 1024 * 1024;
const MANIFEST_CACHE_TTL_MS = 60 * 1000;

function hex(bytes) {
  return [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
}

function timingSafeEqual(left, right) {
  if (typeof left !== "string" || typeof right !== "string" || left.length !== right.length) return false;
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) {
    difference |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return difference === 0;
}

async function hmacHex(secret, value) {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return hex(new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(value))));
}

function parseSongPath(pathname, prefix) {
  if (!pathname.startsWith(prefix)) return null;
  const parts = pathname.slice(prefix.length).split("/");
  if (parts.length !== 2 || !parts[0] || !parts[1]) return null;
  try {
    return { songId: decodeURIComponent(parts[0]), fileName: decodeURIComponent(parts[1]) };
  } catch {
    return null;
  }
}

async function loadManifest(env, nowMs = Date.now()) {
  if (manifestCache && nowMs < manifestCacheExpiresAt) return manifestCache;
  const key = env.ASSET_MANIFEST_KEY || "private/asset-manifest.json";
  const object = await env.AKAINE_ASSETS.get(key);
  if (!object) throw new Error(`Asset manifest not found: ${key}`);
  const parsed = await object.json();
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Asset manifest must be a song-to-files object");
  }
  manifestCache = parsed;
  manifestCacheExpiresAt = nowMs + MANIFEST_CACHE_TTL_MS;
  return parsed;
}

async function verifySignedRequest(request, env, nowSeconds = Math.floor(Date.now() / 1000)) {
  const url = new URL(request.url);
  const parsed = parseSongPath(url.pathname, "/protected/songs/");
  if (!parsed) return { ok: false, status: 404, reason: "not_found" };
  const uid = url.searchParams.get("uid") || "";
  const expires = url.searchParams.get("exp") || "";
  const nonce = url.searchParams.get("nonce") || "";
  const signature = url.searchParams.get("sig") || "";
  if (!uid || !expires || !nonce || !signature) {
    return { ok: false, status: 403, reason: "missing_signature", ...parsed };
  }
  const expiresNumber = Number(expires);
  if (!Number.isSafeInteger(expiresNumber) || expiresNumber <= nowSeconds) {
    return { ok: false, status: 403, reason: "expired", ...parsed };
  }
  if (!env.ASSET_SIGNING_SECRET) {
    return { ok: false, status: 500, reason: "worker_secret_missing", ...parsed };
  }
  const manifest = await loadManifest(env);
  const allowed = manifest[parsed.songId];
  if (!Array.isArray(allowed) || !allowed.includes(parsed.fileName)) {
    return { ok: false, status: 403, reason: "file_not_allowed", ...parsed };
  }
  const payload = [
    request.method.toUpperCase(),
    url.pathname,
    uid,
    parsed.songId,
    parsed.fileName,
    expires,
    nonce,
  ].join("\n");
  const expected = await hmacHex(env.ASSET_SIGNING_SECRET, payload);
  if (!timingSafeEqual(expected, signature)) {
    return { ok: false, status: 403, reason: "bad_signature", ...parsed };
  }
  return { ok: true, ...parsed };
}

function contentType(fileName) {
  if (fileName.endsWith(".ogg")) return "audio/ogg";
  if (fileName.endsWith(".aff")) return "text/plain; charset=utf-8";
  if (fileName.endsWith(".jpg") || fileName.endsWith(".jpeg")) return "image/jpeg";
  if (fileName.endsWith(".png")) return "image/png";
  if (fileName.endsWith(".mp4")) return "video/mp4";
  if (fileName.endsWith(".wav")) return "audio/wav";
  return "application/octet-stream";
}

function assetHeaders(object, fileName) {
  const headers = new Headers();
  headers.set("Content-Type", object.httpMetadata?.contentType || contentType(fileName));
  headers.set("Cache-Control", "private, max-age=300");
  headers.set("Accept-Ranges", "bytes");
  headers.set("X-Content-Type-Options", "nosniff");
  if (object.httpEtag) headers.set("ETag", object.httpEtag);
  return headers;
}

function cacheKey(url) {
  const canonical = new URL(url);
  canonical.search = "";
  canonical.hash = "";
  return new Request(canonical, { method: "GET" });
}

function privateResponse(cached) {
  const headers = new Headers(cached.headers);
  headers.set("Cache-Control", "private, max-age=300");
  return new Response(cached.body, { status: cached.status, headers });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/private/")) {
      return new Response("private path", { status: 403 });
    }
    if (request.method !== "GET") {
      return new Response("method not allowed", { status: 405 });
    }
    let verified;
    try {
      verified = await verifySignedRequest(request, env);
    } catch {
      return new Response("asset service unavailable", { status: 503 });
    }
    if (!verified.ok) return new Response(verified.reason, { status: verified.status });

    const key = `private/songs/${verified.songId}/${verified.fileName}`;
    const range = request.headers.get("Range");
    const internalKey = cacheKey(url);
    if (!range) {
      const cached = await caches.default.match(internalKey);
      if (cached) return privateResponse(cached);
    }
    const object = range
      ? await env.AKAINE_ASSETS.get(key, { range: request.headers })
      : await env.AKAINE_ASSETS.get(key);
    if (!object?.body) return new Response("not found", { status: 404 });

    const headers = assetHeaders(object, verified.fileName);
    if (range) {
      if (!object.range) {
        headers.set("Content-Range", `bytes */${object.size}`);
        return new Response(null, { status: 416, headers });
      }
      const end = object.range.offset + object.range.length - 1;
      headers.set("Content-Range", `bytes ${object.range.offset}-${end}/${object.size}`);
      headers.set("Content-Length", String(object.range.length));
      return new Response(object.body, { status: 206, headers });
    }
    headers.set("Content-Length", String(object.size));
    const response = new Response(object.body, { status: 200, headers });
    if (object.size <= PRIVATE_CACHE_MAX_BYTES) {
      const cachedHeaders = new Headers(headers);
      cachedHeaders.set("Cache-Control", "public, s-maxage=86400");
      ctx.waitUntil(caches.default.put(
        internalKey,
        new Response(response.clone().body, { status: 200, headers: cachedHeaders }),
      ));
    }
    return response;
  },
};

export { hmacHex, loadManifest, parseSongPath, timingSafeEqual, verifySignedRequest };
