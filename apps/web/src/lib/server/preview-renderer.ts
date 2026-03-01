import { chromium, type Browser } from "playwright";

interface RenderParams {
  lat: number;
  lng: number;
  altitudeMeters: number;
  headingDegrees: number;
  pitchDegrees: number;
  rollDegrees: number;
  fovDegrees: number;
}

const RENDER_TIMEOUT = parseInt(
  process.env.PREVIEW_RENDER_TIMEOUT_MS || "20000",
  10
);
const RENDER_WIDTH = parseInt(
  process.env.PREVIEW_RENDER_WIDTH || "1280",
  10
);
const RENDER_HEIGHT = parseInt(
  process.env.PREVIEW_RENDER_HEIGHT || "720",
  10
);
const NEXT_DEV_OVERLAY_HIDE_CSS = `
  nextjs-portal,
  [data-nextjs-toast],
  script[data-nextjs-dev-overlay="true"] {
    display: none !important;
  }
`;

let browserInstance: Browser | null = null;
let renderInProgress = false;
const renderQueue: Array<{
  resolve: (buf: Buffer) => void;
  reject: (err: Error) => void;
  params: RenderParams;
}> = [];

async function getBrowser(): Promise<Browser> {
  if (!browserInstance || !browserInstance.isConnected()) {
    browserInstance = await chromium.launch({
      headless: true,
      args: ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
    });
  }
  return browserInstance;
}

async function processQueue(): Promise<void> {
  if (renderInProgress || renderQueue.length === 0) return;

  renderInProgress = true;
  const item = renderQueue.shift()!;

  try {
    const result = await doRender(item.params);
    item.resolve(result);
  } catch (err) {
    item.reject(err instanceof Error ? err : new Error(String(err)));
  } finally {
    renderInProgress = false;
    processQueue();
  }
}

async function doRender(params: RenderParams): Promise<Buffer> {
  const browser = await getBrowser();
  const page = await browser.newPage();

  try {
    await page.setViewportSize({ width: RENDER_WIDTH, height: RENDER_HEIGHT });

    const searchParams = new URLSearchParams({
      lat: String(params.lat),
      lng: String(params.lng),
      altitudeMeters: String(params.altitudeMeters),
      headingDegrees: String(params.headingDegrees),
      pitchDegrees: String(params.pitchDegrees),
      rollDegrees: String(params.rollDegrees),
      fovDegrees: String(params.fovDegrees),
    });

    // Use the app's own URL for the render page
    const baseUrl =
      process.env.PREVIEW_RENDER_BASE_URL || "http://localhost:3000";
    const url = `${baseUrl}/preview/render?${searchParams.toString()}`;

    await page.goto(url, {
      waitUntil: "domcontentloaded",
      timeout: RENDER_TIMEOUT,
    });
    await page.addStyleTag({ content: NEXT_DEV_OVERLAY_HIDE_CSS });

    // Wait for the ready marker
    await page.waitForFunction(
      () =>
        document.body.dataset.previewReady === "true" ||
        document.body.dataset.previewError != null,
      { timeout: RENDER_TIMEOUT }
    );

    // Check for error
    const error = await page.evaluate(
      () => document.body.dataset.previewError
    );
    if (error) {
      throw new Error(`Preview render error: ${error}`);
    }

    // Capture screenshot as JPEG
    const screenshot = await page.screenshot({
      type: "jpeg",
      quality: 82,
      fullPage: false,
    });

    return Buffer.from(screenshot);
  } finally {
    await page.close();
  }
}

export async function renderPreview(params: RenderParams): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    renderQueue.push({ resolve, reject, params });
    processQueue();
  });
}

export async function shutdownRenderer(): Promise<void> {
  if (browserInstance) {
    await browserInstance.close();
    browserInstance = null;
  }
}
