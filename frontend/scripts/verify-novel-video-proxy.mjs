// Executable boundary test: Vite owns the token; renderer requests do not.
import assert from "node:assert/strict";
import crypto from "node:crypto";
import http from "node:http";
import { createServer } from "vite";

const upstreamPort = 18180;
const vitePort = 18181;
const token = "proxy-boundary-test-token";
const proxySecret = "proxy-boundary-test-secret";
const seen = [];
const issuedSessions = new Set();
const usedNonces = new Set();

function validateAssertion(request) {
  const timestamp = request.headers["x-novel-proxy-timestamp"];
  const nonce = request.headers["x-novel-proxy-nonce"];
  const assertion = request.headers["x-novel-proxy-assertion"];
  const session = request.headers.cookie?.match(/novel_video_session=([^;]+)/)?.[1] ?? "-";
  const message = [timestamp, nonce, request.method, request.url, session].join("\n");
  const expected = crypto.createHmac("sha256", proxySecret).update(message).digest("hex");
  return Boolean(timestamp && nonce && assertion && !usedNonces.has(nonce) && crypto.timingSafeEqual(Buffer.from(assertion), Buffer.from(expected)));
}

const upstream = http.createServer((request, response) => {
  seen.push({
    url: request.url,
    capability: request.headers["x-novel-video-capability"],
    proxyTimestamp: request.headers["x-novel-proxy-timestamp"],
    proxyNonce: request.headers["x-novel-proxy-nonce"],
    proxyAssertion: request.headers["x-novel-proxy-assertion"],
  });
  if (request.url === "/api/core/novel-video/session") {
    if (request.method !== "POST" || request.headers["x-novel-video-capability"] !== token || !validateAssertion(request)) {
      response.statusCode = 403;
      return response.end();
    }
    usedNonces.add(request.headers["x-novel-proxy-nonce"]);
    issuedSessions.add("opaque");
    response.setHeader("Set-Cookie", "novel_video_session=opaque; HttpOnly; SameSite=Strict");
  } else if (request.url?.startsWith("/api/core/novel-video/")) {
    const session = request.headers.cookie?.match(/novel_video_session=([^;]+)/)?.[1];
    if (!issuedSessions.has(session) || !validateAssertion(request)) {
      response.statusCode = 403;
      return response.end();
    }
    usedNonces.add(request.headers["x-novel-proxy-nonce"]);
  }
  response.setHeader("Content-Type", "application/json");
  response.end(JSON.stringify({ ok: true }));
});

await new Promise((resolve) => upstream.listen(upstreamPort, "127.0.0.1", resolve));
process.env.AI_MANGA_NOVEL_VIDEO_CAPABILITY = token;
process.env.AI_MANGA_NOVEL_PROXY_SECRET = proxySecret;
process.env.AI_MANGA_BACKEND_URL = `http://127.0.0.1:${upstreamPort}`;
process.env.AI_MANGA_VITE_PORT = String(vitePort);
const vite = await createServer({ configFile: "vite.config.ts", server: { host: "127.0.0.1", port: vitePort } });
await vite.listen();

async function request(path, options = {}) {
  const { includeOrigin = true, ...fetchOptions } = options;
  return fetch(`http://127.0.0.1:${vitePort}${path}`, {
    ...fetchOptions,
    headers: {
      Host: `127.0.0.1:${vitePort}`,
      ...(includeOrigin ? { Origin: `http://127.0.0.1:${vitePort}` } : {}),
      ...(fetchOptions.headers ?? {}),
    },
  });
}

async function rawRequest(path, { method = "GET", headers = {}, body } = {}) {
  return new Promise((resolve, reject) => {
    const outgoing = http.request({ hostname: "127.0.0.1", port: vitePort, path, method, headers }, (response) => {
      response.resume();
      response.on("end", () => resolve(response));
    });
    outgoing.on("error", reject);
    if (body) outgoing.write(body);
    outgoing.end();
  });
}

try {
  const session = await request("/api/core/novel-video/session", { method: "POST" });
  assert.equal(session.status, 200);
  assert.equal(seen.at(-1).capability, token);
  assert.ok(seen.at(-1).url === "/api/core/novel-video/session");
  const cookie = session.headers.get("set-cookie")?.split(";")[0];
  assert.equal(cookie, "novel_video_session=opaque");
  const normal = await request("/api/core/novel-video/projects/example", { headers: { Cookie: cookie } });
  assert.equal(normal.status, 200);
  assert.equal(seen.at(-1).capability, undefined);
  const sameOriginWithoutOrigin = await request("/api/core/novel-video/projects/example", {
    includeOrigin: false,
    headers: { Cookie: cookie, "Sec-Fetch-Site": "same-origin" },
  });
  assert.equal(sameOriginWithoutOrigin.status, 200);
  assert.ok(seen.at(-1).proxyAssertion);
  const sameOriginRefererWithoutFetchMetadata = await request("/api/core/novel-video/projects/example", {
    includeOrigin: false,
    headers: { Cookie: cookie, Referer: `http://127.0.0.1:${vitePort}/studio` },
  });
  assert.equal(sameOriginRefererWithoutFetchMetadata.status, 200);
  const nativeWithoutBrowserMetadata = await request("/api/core/novel-video/projects/example", {
    includeOrigin: false,
    headers: { Cookie: cookie },
  });
  assert.equal(nativeWithoutBrowserMetadata.status, 200);
  const hostileRefererWithoutFetchMetadata = await request("/api/core/novel-video/projects/example", {
    includeOrigin: false,
    headers: { Cookie: cookie, Referer: "https://evil.invalid/attack" },
  });
  assert.equal(hostileRefererWithoutFetchMetadata.status, 403);
  const crossSiteSafe = await request("/api/core/novel-video/projects/example", {
    includeOrigin: false,
    headers: { Cookie: cookie, "Sec-Fetch-Site": "cross-site" },
  });
  assert.equal(crossSiteSafe.status, 403);
  const hostileHost = await rawRequest("/api/core/novel-video/projects/example", {
    headers: { Cookie: cookie, Host: "evil.invalid", "Sec-Fetch-Site": "same-origin" },
  });
  assert.equal(hostileHost.statusCode, 403);
  const hostileOrigin = await request("/api/core/novel-video/projects/example", {
    headers: { Cookie: cookie, Origin: "https://evil.invalid" },
  });
  assert.equal(hostileOrigin.status, 403);
  const unsafeWithoutOrigin = await request("/api/core/novel-video/projects", {
    method: "POST",
    includeOrigin: false,
    headers: { Cookie: cookie, "Content-Type": "application/json", "Sec-Fetch-Site": "same-origin" },
    body: "{}",
  });
  assert.equal(unsafeWithoutOrigin.status, 403);
  const events = await request("/api/core/novel-video/runs/run-1/events?after=0&limit=1&stream=false", { headers: { Cookie: cookie } });
  assert.equal(events.status, 200);
  const duplicateQuery = await request("/api/core/novel-video/runs/run-1/events?after=0&after=1&limit=1", { headers: { Cookie: cookie } });
  assert.equal(duplicateQuery.status, 200);
  const sessionQuery = await request("/api/core/novel-video/session?unexpected=1", { method: "POST" });
  assert.equal(sessionQuery.status, 403);
  const ordinaryQuery = await request("/api/core/novel-video/projects/example?unexpected=1", { headers: { Cookie: cookie } });
  assert.equal(ordinaryQuery.status, 403);
  const sessionNamedResource = await request("/api/core/novel-video/projects/session-not-handshake", { headers: { Cookie: cookie } });
  assert.equal(sessionNamedResource.status, 200);
  const encoded = await request("/api/core/novel-video/%2fsession", { method: "POST" });
  assert.equal(encoded.status, 403);
  const doubleEncoded = await request("/api/core/novel-video/%252fsession", { method: "POST" });
  assert.equal(doubleEncoded.status, 403);
  const unicodeEncoded = await request("/api/core/novel-video/projects/%E8%B4%AA%E7%8B%BC", { headers: { Cookie: cookie } });
  assert.equal(unicodeEncoded.status, 403);
  const trailingSlash = await request("/api/core/novel-video/session/", { method: "POST" });
  assert.equal(trailingSlash.status, 403);
  assert.equal(seen.at(-1).capability, undefined);
  const direct = await fetch(`http://127.0.0.1:${upstreamPort}/api/core/novel-video/projects/example`, { headers: { Cookie: cookie } });
  assert.equal(direct.status, 403);
  const forged = await fetch(`http://127.0.0.1:${upstreamPort}/api/core/novel-video/projects/example`, {
    headers: { Cookie: cookie, "X-Novel-Proxy-Timestamp": String(Math.floor(Date.now() / 1000)), "X-Novel-Proxy-Nonce": "forged-nonce-012345678901", "X-Novel-Proxy-Assertion": "00".repeat(32) },
  });
  assert.equal(forged.status, 403);
  const generic = await request("/api/legacy/ping", {
    headers: {
      "X-Novel-Proxy-Timestamp": "1234567890",
      "X-Novel-Proxy-Nonce": "forged-generic-nonce",
      "X-Novel-Proxy-Assertion": "forged-generic-assertion",
      "X-Novel-Video-Capability": "forged-generic-capability",
    },
  });
  assert.equal(generic.status, 200);
  assert.equal(seen.at(-1).proxyTimestamp, undefined);
  assert.equal(seen.at(-1).proxyNonce, undefined);
  assert.equal(seen.at(-1).proxyAssertion, undefined);
  assert.equal(seen.at(-1).capability, undefined);
  assert.ok(!JSON.stringify(await session.json()).includes(token));
} finally {
  await vite.close();
  await new Promise((resolve) => upstream.close(resolve));
}
