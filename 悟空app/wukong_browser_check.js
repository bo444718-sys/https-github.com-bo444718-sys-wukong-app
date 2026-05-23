#!/usr/bin/env node
"use strict";

const fs = require("fs");
const http = require("http");
const path = require("path");
const { execFileSync } = require("child_process");

const ROOT = __dirname;
const PWA = path.join(ROOT, "PWA");
const APP_JS = fs.readFileSync(path.join(PWA, "app.js"), "utf8");
const VERSION = (APP_JS.match(/APP_VERSION\s*=\s*"(\d+)"/) || [])[1];
const PUBLIC_URL_FILES = [
  "/Users/wangbo/.hermes/wukong_pwa/wukong_pwa_url.txt",
  path.join(ROOT, "wukong_pwa_url.txt"),
];
const GROUPS = [
  ["overviewGroup", "实时总览"],
  ["decisionGroup", "决策中心"],
  ["marketGroup", "市场信号"],
  ["telegramGroup", "Telegram"],
  ["installGroup", "我的"],
  ["filesGroup", "文件同步"],
];

if (!VERSION) {
  throw new Error("PWA/app.js missing APP_VERSION");
}

function contentType(filePath) {
  const ext = path.extname(filePath);
  return {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".apk": "application/vnd.android.package-archive",
    ".mobileconfig": "application/x-apple-aspen-config",
    ".txt": "text/plain; charset=utf-8",
  }[ext] || "application/octet-stream";
}

function startServer() {
  const server = http.createServer((request, response) => {
    const rawPath = new URL(request.url, "http://127.0.0.1").pathname;
    const pathname = rawPath === "/" ? "/index.html" : rawPath;
    const resolved = path.normalize(path.join(PWA, decodeURIComponent(pathname)));
    if (!resolved.startsWith(PWA)) {
      response.writeHead(403);
      response.end("Forbidden");
      return;
    }
    fs.stat(resolved, (statError, stat) => {
      if (statError || !stat.isFile()) {
        response.writeHead(404);
        response.end("Not found");
        return;
      }
      response.writeHead(200, {
        "Content-Type": contentType(resolved),
        "Content-Length": stat.size,
        "Cache-Control": "no-store",
      });
      if (request.method === "HEAD") {
        response.end();
        return;
      }
      fs.createReadStream(resolved).pipe(response);
    });
  });
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

function publicUrl() {
  for (const file of PUBLIC_URL_FILES) {
    try {
      const value = fs.readFileSync(file, "utf8").trim().replace(/\/+$/, "");
      if (value.startsWith("https://") || value.startsWith("http://")) return value;
    } catch {
      // Continue to the next known location.
    }
  }
  return "";
}

function publicDnsIp(hostname) {
  try {
    const output = execFileSync("nslookup", [hostname, "1.1.1.1"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });
    const addresses = output.split(/\n/).map((line) => line.split("Address:")[1]?.trim()).filter(Boolean);
    return addresses.find((address) => /^\d+\.\d+\.\d+\.\d+$/.test(address) && address !== "1.1.1.1") || "";
  } catch {
    return "";
  }
}

async function loadPlaywright() {
  try {
    return require("playwright");
  } catch {
    return require("/Users/wangbo/.npm/_npx/31e32ef8478fbf80/node_modules/playwright");
  }
}

async function waitForAppReady(page) {
  await page.waitForSelector("#appVersion", { state: "attached", timeout: 15000 });
  await page.waitForFunction(() => {
    const text = document.querySelector("#navFilesMeta")?.textContent || "";
    return /\d+\s*文件/.test(text);
  }, null, { timeout: 20000 }).catch(() => {});
}

async function checkTopGroups(page) {
  const results = [];
  for (const [groupId, label] of GROUPS) {
    const selector = `.top-section-map [data-group="${groupId}"]`;
    await page.locator(selector).click();
    await page.waitForTimeout(220);
    const state = await page.evaluate((id) => {
      const activeSections = [...document.querySelectorAll(".section-gated > .module-group")]
        .filter((element) => !element.hidden)
        .map((element) => element.id);
      const section = document.getElementById(id);
      const control = document.querySelector(`.top-section-map [data-group="${id}"]`);
      return {
        activeSections,
        visible: Boolean(section && !section.hidden),
        active: Boolean(section?.classList.contains("is-active")),
        pressed: control?.getAttribute("aria-pressed"),
        current: control?.getAttribute("aria-current"),
        controls: control?.getAttribute("aria-controls"),
        textLength: (section?.innerText || "").trim().length,
      };
    }, groupId);
    if (state.activeSections.length !== 1 || state.activeSections[0] !== groupId) {
      throw new Error(`group isolation failed ${groupId}: ${state.activeSections.join(",")}`);
    }
    if (!state.visible || !state.active || state.pressed !== "true" || state.current !== "true" || state.controls !== groupId) {
      throw new Error(`group state failed ${groupId}: ${JSON.stringify(state)}`);
    }
    if (state.textLength < 30) {
      throw new Error(`group content too short ${groupId}: ${state.textLength}`);
    }
    const title = await page.locator(`#${groupId}`).locator("h2").first().innerText();
    if (!title.includes(label)) {
      throw new Error(`group title mismatch ${groupId}: ${title}`);
    }
    results.push(groupId);
  }
  return results;
}

async function checkTapTargets(page, label) {
  const smallTargets = await page.evaluate(() => {
    return [...document.querySelectorAll(".top-section-map [data-group]")].map((button) => {
      const rect = button.getBoundingClientRect();
      return {
        group: button.dataset.group || "",
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      };
    }).filter((item) => item.width < 44 || item.height < 44);
  });
  if (smallTargets.length) {
    throw new Error(`${label} tap targets too small: ${JSON.stringify(smallTargets)}`);
  }
  return true;
}

async function checkImages(page, label) {
  const broken = await page.evaluate(() => {
    return [...document.images].map((image) => ({
      src: image.getAttribute("src") || image.currentSrc || "",
      alt: image.getAttribute("alt") || "",
      complete: image.complete,
      naturalWidth: image.naturalWidth,
      naturalHeight: image.naturalHeight,
      width: Math.round(image.getBoundingClientRect().width),
      height: Math.round(image.getBoundingClientRect().height),
    })).filter((image) => !image.complete || image.naturalWidth < 40 || image.naturalHeight < 40 || image.width < 24 || image.height < 24);
  });
  if (broken.length) {
    throw new Error(`${label} images failed to render: ${JSON.stringify(broken)}`);
  }
  return true;
}

async function checkManifest(page, baseUrl) {
  const manifest = await page.evaluate(async () => {
    const href = document.querySelector('link[rel="manifest"]')?.getAttribute("href") || "";
    const response = await fetch(new URL(href, location.href), { cache: "no-store" });
    return await response.json();
  });
  if (manifest.name !== "悟空" || manifest.short_name !== "悟空" || manifest.display !== "standalone") {
    throw new Error(`manifest identity mismatch: ${JSON.stringify(manifest)}`);
  }
  if (!String(manifest.start_url || "").includes(`v=${VERSION}`)) {
    throw new Error(`manifest start_url missing v${VERSION}: ${manifest.start_url}`);
  }
  const icons = manifest.icons || [];
  const requiredIcons = ["192x192", "512x512"];
  for (const size of requiredIcons) {
    const icon = icons.find((item) => String(item.sizes || "").includes(size) && item.type === "image/png");
    if (!icon) {
      throw new Error(`manifest icon ${size} missing`);
    }
    const status = await page.evaluate(async (src) => (await fetch(new URL(src, location.href), { method: "HEAD" })).status, icon.src);
    if (status !== 200) {
      throw new Error(`manifest icon ${size} failed HEAD ${status}`);
    }
  }
  const shortcuts = manifest.shortcuts || [];
  if (shortcuts.length < 3 || !shortcuts.every((item) => String(item.url || "").includes(`v=${VERSION}`))) {
    throw new Error(`manifest shortcuts incomplete: ${JSON.stringify(shortcuts)}`);
  }
  const appleIconStatus = await page.evaluate(async () => {
    const href = document.querySelector('link[rel="apple-touch-icon"]')?.getAttribute("href") || "";
    return href ? (await fetch(new URL(href, location.href), { method: "HEAD" })).status : 0;
  });
  if (appleIconStatus !== 200) {
    throw new Error(`apple touch icon failed HEAD ${appleIconStatus} at ${baseUrl}`);
  }
  return true;
}

async function checkAppPage(page, url, label) {
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 20000 }).catch(() => {});
  await waitForAppReady(page);
  const appVersion = await page.locator("#appVersion").innerText();
  const releaseVersion = await page.locator("#releaseVersion").innerText();
  const fileCount = await page.locator("#navFilesMeta").innerText().catch(() => "");
  const navCount = await page.locator(".top-section-map [data-group]").count();
  const groups = await checkTopGroups(page);
  const tapTargets = await checkTapTargets(page, label);
  const filePanelText = await page.locator("#filesGroup").innerText();
  const manifestReady = await checkManifest(page, url);
  await page.locator('.top-section-map [data-group="installGroup"]').click();
  await page.waitForTimeout(220);
  const imagesReady = await checkImages(page, label);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);

  if (appVersion !== `v${VERSION}` || releaseVersion !== `v${VERSION}`) {
    throw new Error(`${label} version mismatch app=${appVersion} release=${releaseVersion}`);
  }
  if (!fileCount.match(/\d+\s*文件/)) {
    throw new Error(`${label} file count missing: ${fileCount}`);
  }
  if (filePanelText.includes("wukong-android-debug.apk")) {
    throw new Error(`${label} debug APK is visible in file sync panel`);
  }
  if (filePanelText.includes("wukong-ios-signing-kit.zip") || filePanelText.includes("Wukong.zip")) {
    throw new Error(`${label} archive package is visible in file sync panel`);
  }
  if (navCount !== GROUPS.length || groups.length !== GROUPS.length) {
    throw new Error(`${label} section nav count failed nav=${navCount} groups=${groups.length}`);
  }
  if (overflow) {
    throw new Error(`${label} horizontal overflow detected`);
  }
  return { appVersion, releaseVersion, fileCount, navCount, groups, tapTargets, imagesReady, manifestReady, overflow };
}

async function main() {
  const server = await startServer();
  const port = server.address().port;
  const base = `http://127.0.0.1:${port}`;
  const liveBase = publicUrl();
  let browser;
  try {
    const { chromium } = await loadPlaywright();
    const liveHost = liveBase ? new URL(liveBase).hostname : "";
    const liveIp = liveHost ? publicDnsIp(liveHost) : "";
    const browserArgs = liveHost && liveIp ? [`--host-resolver-rules=MAP ${liveHost} ${liveIp}`] : [];
    browser = await chromium.launch({ headless: true, channel: "chrome", args: browserArgs });
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(`pageerror:${error.message}`));
    page.on("console", (message) => {
      if (message.type() === "error") {
        errors.push(`console:${message.text()}`);
      }
    });

    await page.goto(`${base}/install.html?v=${VERSION}&apkVersion=1`, { waitUntil: "networkidle" });
    const iosHref = await page.locator('a[href*="wukong-ios-install.mobileconfig"]').first().getAttribute("href");
    const apkHref = await page.locator('a[href*="wukong-android-release.apk"]').first().getAttribute("href");
    const privacyHref = await page.locator('a[href*="privacy.html"]').first().getAttribute("href");
    const signingLinks = await page.locator('a[href*="wukong-ios-signing-kit.zip"]').count();
    if (signingLinks) {
      throw new Error("install page exposes iOS signing kit");
    }
    if (!decodeURIComponent(iosHref).includes(`v=${VERSION}`)) {
      throw new Error(`iPhone link missing v${VERSION}: ${iosHref}`);
    }
    if (!decodeURIComponent(apkHref).includes(`v=${VERSION}`)) {
      throw new Error(`Android link missing v${VERSION}: ${apkHref}`);
    }
    if (!decodeURIComponent(privacyHref || "").includes(`v=${VERSION}`)) {
      throw new Error(`privacy link missing v${VERSION}: ${privacyHref}`);
    }
    const iosHead = await page.evaluate(async (href) => (await fetch(new URL(href, location.href), { method: "HEAD" })).status, iosHref);
    const apkHead = await page.evaluate(async (href) => (await fetch(new URL(href, location.href), { method: "HEAD" })).status, apkHref);
    const apkLength = await page.evaluate(async (href) => Number((await fetch(new URL(href, location.href), { method: "HEAD" })).headers.get("Content-Length") || 0), apkHref);
    if (iosHead !== 200 || apkHead !== 200) {
      throw new Error(`download HEAD failed ios=${iosHead} apk=${apkHead}`);
    }
    if (apkLength < 10_000_000) {
      throw new Error(`Android APK content length too small: ${apkLength}`);
    }
    await checkImages(page, "install-local");

    await page.waitForFunction(async () => Boolean(await navigator.serviceWorker.getRegistration()), null, { timeout: 10000 });
    const swScript = await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.getRegistration();
      return registration.active?.scriptURL || registration.installing?.scriptURL || "";
    });
    const cacheKeys = await page.evaluate(async () => await caches.keys());
    if (!swScript.includes(`sw.js?v=${VERSION}`)) {
      throw new Error(`SW script mismatch: ${swScript}`);
    }
    if (!cacheKeys.includes(`wukong-pwa-v${VERSION}`)) {
      throw new Error(`cache v${VERSION} missing: ${cacheKeys.join(",")}`);
    }

    await context.setOffline(true);
    await page.reload({ waitUntil: "domcontentloaded" });
    const offlineTitle = await page.locator("h1").first().innerText();
    if (offlineTitle.trim() !== "悟空") {
      throw new Error(`offline title mismatch: ${offlineTitle}`);
    }
    await context.setOffline(false);

    await page.goto(`${base}/index.html?v=${VERSION}`, { waitUntil: "networkidle" });
    const mobile = await checkAppPage(page, `${base}/index.html?v=${VERSION}`, "mobile-local");
    await page.setViewportSize({ width: 1365, height: 900 });
    const desktop = await checkAppPage(page, `${base}/index.html?v=${VERSION}`, "desktop-local");
    let publicPage = null;
    if (liveBase) {
      publicPage = await checkAppPage(page, `${liveBase}/index.html?v=${VERSION}&browserCheck=${Date.now()}`, "public");
    }
    if (errors.length) {
      throw new Error(errors.join("\n"));
    }

    console.log(JSON.stringify({ version: `v${VERSION}`, iosHead, apkHead, apkLength, swScript, cacheKeys, mobile, desktop, public: publicPage }, null, 2));
  } finally {
    if (browser) {
      await browser.close();
    }
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
