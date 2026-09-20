import assert from "node:assert/strict";
import { test } from "node:test";
import worker, { hmacHex, verifySignedRequest } from "./worker.mjs";

const secret = "test-only-secret";
const manifest = { demo_song: ["2.aff", "base.ogg"] };
const env = {
  ASSET_SIGNING_SECRET: secret,
  AKAINE_ASSETS: {
    async get(key) {
      if (key === "private/asset-manifest.json") {
        return { async json() { return manifest; } };
      }
      return null;
    },
  },
};

async function signedRequest(expires = 2000) {
  const path = "/protected/songs/demo_song/2.aff";
  const payload = ["GET", path, "42", "demo_song", "2.aff", String(expires), "abc"].join("\n");
  const signature = await hmacHex(secret, payload);
  return new Request(`https://assets.example.com${path}?uid=42&exp=${expires}&nonce=abc&sig=${signature}`);
}

test("accepts a valid server-compatible signature", async () => {
  const result = await verifySignedRequest(await signedRequest(), env, 1000);
  assert.equal(result.ok, true);
});

test("rejects an expired URL", async () => {
  const result = await verifySignedRequest(await signedRequest(999), env, 1000);
  assert.deepEqual([result.ok, result.status, result.reason], [false, 403, "expired"]);
});

test("rejects a file outside the manifest", async () => {
  const path = "/protected/songs/demo_song/secret.wav";
  const request = new Request(`https://assets.example.com${path}?uid=42&exp=2000&nonce=abc&sig=bad`);
  const result = await verifySignedRequest(request, env, 1000);
  assert.deepEqual([result.ok, result.status, result.reason], [false, 403, "file_not_allowed"]);
});

test("blocks direct private storage paths", async () => {
  const response = await worker.fetch(
    new Request("https://assets.example.com/private/songs/demo_song/2.aff"),
    env,
    { waitUntil() {} },
  );
  assert.equal(response.status, 403);
});

test("blocks an unsigned protected request before reading R2 content", async () => {
  const response = await worker.fetch(
    new Request("https://assets.example.com/protected/songs/demo_song/2.aff"),
    env,
    { waitUntil() {} },
  );
  assert.equal(response.status, 403);
});
