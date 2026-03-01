#!/usr/bin/env node

/**
 * Puppeteer capture script for Smallworld preview renders.
 *
 * Usage:
 *   node scripts/render-preview.mjs \
 *     --url "http://localhost:3000/render/preview?payload=..." \
 *     --output ./output.png \
 *     [--width 1536] \
 *     [--height 1024] \
 *     [--timeout 30000]
 */

import puppeteer from "puppeteer";

const NEXT_DEV_OVERLAY_HIDE_CSS = `
  nextjs-portal,
  [data-nextjs-toast],
  script[data-nextjs-dev-overlay="true"] {
    display: none !important;
  }
`;

// ---------------------------------------------------------------------------
// CLI argument parsing (no external deps)
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i++) {
    const arg = argv[i];
    if (arg.startsWith("--")) {
      const key = arg.slice(2);
      const next = argv[i + 1];
      if (next !== undefined && !next.startsWith("--")) {
        args[key] = next;
        i++; // skip the value
      } else {
        args[key] = true;
      }
    }
  }
  return args;
}

const args = parseArgs(process.argv);

const url = args.url;
const output = args.output;
const width = parseInt(args.width ?? "1536", 10);
const height = parseInt(args.height ?? "1024", 10);
const timeout = parseInt(args.timeout ?? "30000", 10);

if (!url) {
  console.error("Error: --url is required");
  process.exit(1);
}
if (!output) {
  console.error("Error: --output is required");
  process.exit(1);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  let browser;
  try {
    browser = await puppeteer.launch({
      headless: "new",
      args: [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--enable-webgl",
        "--ignore-gpu-blocklist",
      ],
    });

    const page = await browser.newPage();
    await page.setViewport({ width, height });
    await page.goto(url, { waitUntil: "domcontentloaded", timeout });
    await page.addStyleTag({ content: NEXT_DEV_OVERLAY_HIDE_CSS });

    // Wait for the render page to signal readiness
    await page.waitForFunction(
      "window.__SMALLWORLD_RENDER_READY__ === true",
      { timeout }
    );

    // Check for render-side errors
    const renderError = await page.evaluate(
      () => window.__SMALLWORLD_RENDER_ERROR__
    );
    if (renderError) {
      console.error(`Render error: ${renderError}`);
      process.exit(1);
    }

    // Capture screenshot
    await page.screenshot({ path: output, type: "png", fullPage: false });

    // Read and output frame state (anchor projections, etc.)
    const frameState = await page.evaluate(
      () => window.__SMALLWORLD_FRAME_STATE__
    );
    console.log(JSON.stringify(frameState || {}));

    await browser.close();
    process.exit(0);
  } catch (err) {
    console.error(`Capture failed: ${err.message || err}`);
    if (browser) {
      await browser.close().catch(() => {});
    }
    process.exit(1);
  }
}

main();
