import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const localCapability = process.env.AI_MANGA_NOVEL_VIDEO_CAPABILITY;
const localBackendUrl = process.env.AI_MANGA_BACKEND_URL ?? "http://127.0.0.1:8000";
const localVitePort = Number(process.env.AI_MANGA_VITE_PORT ?? "5173");
const localProxySecret = process.env.AI_MANGA_NOVEL_PROXY_SECRET;
const configDirectory = path.dirname(fileURLToPath(import.meta.url));
if (!localCapability) {
  throw new Error("AI_MANGA_NOVEL_VIDEO_CAPABILITY must be supplied by run.bat");
}
if (!localProxySecret) {
  throw new Error("AI_MANGA_NOVEL_PROXY_SECRET must be supplied by run.bat");
}

export default defineConfig({
  plugins: [react(), novelVideoProxyBoundary()],
  resolve: {
    alias: {
      "@": path.resolve(configDirectory, "./src"),
    },
  },
  server: {
    host: "127.0.0.1",
    allowedHosts: ["127.0.0.1", "localhost"],
    port: localVitePort,
    proxy: {
      "/api": {
        target: localBackendUrl,
        changeOrigin: false,
        ws: false,
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq, request) => {
            // Browser input is never allowed to smuggle server-boundary
            // credentials through either the formal or legacy proxy surface.
            proxyReq.removeHeader("X-Novel-Proxy-Timestamp");
            proxyReq.removeHeader("X-Novel-Proxy-Nonce");
            proxyReq.removeHeader("X-Novel-Proxy-Assertion");
            proxyReq.removeHeader("X-Novel-Video-Capability");
            const formal = canonicalFormalRequest(request);
            if (!formal) return;
            const timestamp = String(Math.floor(Date.now() / 1000));
            const nonce = crypto.randomBytes(24).toString("base64url");
            const sessionId = sessionCookie(request.headers.cookie);
            const message = [timestamp, nonce, request.method ?? "", formal.target, sessionId].join("\n");
            const assertion = crypto.createHmac("sha256", localProxySecret).update(message).digest("hex");
            proxyReq.setHeader("X-Novel-Proxy-Timestamp", timestamp);
            proxyReq.setHeader("X-Novel-Proxy-Nonce", nonce);
            proxyReq.setHeader("X-Novel-Proxy-Assertion", assertion);
            if (formal.isSession) {
              proxyReq.setHeader("X-Novel-Video-Capability", localCapability);
            } else {
              proxyReq.removeHeader("X-Novel-Video-Capability");
            }
          });
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
  },
});

type ProxyRequest = { url?: string; method?: string; headers: Record<string, string | string[] | undefined> };

function canonicalFormalRequest(request: ProxyRequest): { pathname: string; target: string; isSession: boolean } | undefined {
  if (request.headers.upgrade) return undefined;
  const host = request.headers.host;
  if (host !== `127.0.0.1:${localVitePort}` && host !== `localhost:${localVitePort}`) return undefined;
  const allowedOrigins = new Set([
    `http://127.0.0.1:${localVitePort}`,
    `http://localhost:${localVitePort}`,
  ]);
  const method = (request.method ?? "GET").toUpperCase();
  const safeMethod = method === "GET" || method === "HEAD";
  const origin = request.headers.origin;
  const originValue = Array.isArray(origin) ? origin[0] : origin;
  const fetchSite = request.headers["sec-fetch-site"];
  const fetchSiteValue = Array.isArray(fetchSite) ? fetchSite[0] : fetchSite;
  const referer = request.headers.referer;
  const refererValue = Array.isArray(referer) ? referer[0] : referer;
  if (originValue !== undefined && !allowedOrigins.has(originValue)) return undefined;
  if (fetchSiteValue !== undefined && fetchSiteValue !== "same-origin" && fetchSiteValue !== "same-site") return undefined;
  if (refererValue !== undefined) {
    try {
      if (!allowedOrigins.has(new URL(refererValue).origin)) return undefined;
    } catch {
      return undefined;
    }
  }
  if (!safeMethod && (originValue === undefined || !allowedOrigins.has(originValue))) return undefined;
  // Safe native/test clients may omit browser metadata, but only after the
  // exact loopback Host check above. Browser requests carrying Fetch Metadata
  // must explicitly identify as same-origin/same-site.
  const raw = request.url ?? "";
  if ([...raw].some((character) => character.charCodeAt(0) > 0x7f)) return undefined;
  const queryIndex = raw.indexOf("?");
  const pathname = queryIndex < 0 ? raw : raw.slice(0, queryIndex);
  const query = queryIndex < 0 ? "" : raw.slice(queryIndex + 1);
  if (
    !pathname.startsWith("/api/core/novel-video/")
    || pathname.includes("%")
    || pathname.includes("\\")
    || pathname.includes("\0")
    || pathname.endsWith("/")
    || pathname.split("/").some((part) => part === "." || part === "..")
  ) return undefined;
  if (query) {
    if (!/^\/api\/core\/novel-video\/runs\/[^/]+\/events$/.test(pathname)) return undefined;
    if (query.includes("%") || query.includes("\\") || query.includes("\0")) return undefined;
    const valid = query.split("&").every((field) => {
      const equals = field.indexOf("=");
      if (equals < 1) return false;
      const key = field.slice(0, equals);
      const value = field.slice(equals + 1);
      if (key === "after" || key === "limit") return /^[0-9]+$/.test(value);
      if (key === "stream") return value === "0" || value === "1" || value === "true" || value === "false";
      return false;
    });
    if (!valid) return undefined;
  }
  const isSession = pathname === "/api/core/novel-video/session";
  if (isSession && (method !== "POST" || query)) return undefined;
  return { pathname, target: raw, isSession };
}

function sessionCookie(cookie: string | string[] | undefined): string {
  const header = Array.isArray(cookie) ? cookie.join("; ") : cookie ?? "";
  return header.split(";").map((part) => part.trim()).find((part) => part.startsWith("novel_video_session="))?.slice("novel_video_session=".length) ?? "-";
}

function novelVideoProxyBoundary() {
  return {
    name: "novel-video-proxy-boundary",
    configureServer(server: { middlewares: { use: (handler: (request: { url?: string; method?: string; headers: Record<string, string | string[] | undefined> }, response: { statusCode: number; end: () => void }, next: () => void) => void) => void } }) {
      server.middlewares.use((request, response, next) => {
        const raw = request.url ?? "";
        const formalPrefix = "/api/core/novel-video/";
        if (!raw.startsWith(formalPrefix)) return next();
        const malformed = raw.includes("%") || raw.includes("\\") || raw.includes("\0") || request.headers.upgrade;
        if (malformed || !canonicalFormalRequest(request)) {
          response.statusCode = 403;
          response.end();
          return;
        }
        next();
      });
    },
  };
}
