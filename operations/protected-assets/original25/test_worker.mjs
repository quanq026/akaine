import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { readFileSync } from 'node:fs';

const { default: worker, hmacHex, parseProtectedPath } = await import(pathToFileURL(process.argv[2]));
const replacements = JSON.parse(readFileSync(new URL('./audio-replacements.json', import.meta.url)));
const secret = 'synthetic-original25-test-secret';
globalThis.caches = { default: { match: async () => null, put: async () => {} } };
const received = [];
const env = {
  ASSET_SIGNING_SECRET: secret,
  AKAINE_ASSETS: { get: async key => {
    received.push(key);
    return { size: 3, body: new Uint8Array([1, 2, 3]), httpEtag: 'test' };
  } },
};
const ctx = { waitUntil: promise => promise };
async function signed(path, song, file, compact = false) {
  const exp = String(Math.floor(Date.now() / 1000) + 300);
  const fields = ['GET', path, 'disposable', song, file, exp];
  if (!compact) fields.push('test-nonce');
  const signature = await hmacHex(secret, fields.join('\n'));
  const query = compact
    ? new URLSearchParams({ t: `disposable.${exp}.${signature.slice(0, 32)}` })
    : new URLSearchParams({ uid: 'disposable', exp, nonce: 'test-nonce', sig: signature });
  return new Request(`https://arcapi-v3.akai.id.vn${path}?${query}`);
}
for (const row of replacements) {
  const id = `${row.target_song_id}/${row.file}`;
  for (const compact of [false, true]) {
    const request = await signed(`/protected/songs/original25/${id}`, row.target_song_id, row.file, compact);
    assert.equal((await worker.fetch(request, env, ctx)).status, 200);
    assert.equal(received.at(-1), row.key);
    const transplanted = new Request(request.url.replace('/original25/', '/'));
    const before = received.length;
    assert.equal((await worker.fetch(transplanted, env, ctx)).status, 403);
    assert.equal(received.length, before);
  }
  const old = await signed(`/protected/songs/${id}`, row.target_song_id, row.file);
  assert.equal((await worker.fetch(old, env, ctx)).status, 200);
  assert.equal(received.at(-1), `private/songs/${id}`);
}
for (const id of ['aurora_sayonarahatsukoi/base.ogg', 'KikaiNoTsubasa/2.aff']) {
  const [song, file] = id.split('/');
  const request = await signed(`/protected/songs/original25/${id}`, song, file);
  assert.equal((await worker.fetch(request, env, ctx)).status, 200);
  assert.equal(received.at(-1), `private/songs/${id}`);
}
assert.equal(parseProtectedPath('/protected/songs/original25/a/b/c'), null);
for (const path of ['/protected/songs/original25/aurora_bf2e0923/base.ogg', '/private/songs/aurora_bf2e0923/base.ogg']) {
  assert.equal((await worker.fetch(new Request(`https://arcapi-v3.akai.id.vn${path}`), env, ctx)).status, 403);
}
assert.equal((await worker.fetch(new Request('https://cdn.akai.id.vn/private/candidates/aurora-full-base-20261025-original/songs/aurora_bf2e0923/base.ogg'), env, ctx)).status, 404);
console.log('PASS: 50 replacements, legacy paths, both signatures, replay isolation, fallback and unsigned denial');
