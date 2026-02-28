"use client";

import { Suspense, useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";

function PreviewRenderer() {
  const containerRef = useRef<HTMLDivElement>(null);
  const searchParams = useSearchParams();

  useEffect(() => {
    let destroyed = false;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let viewer: any = null;

    async function init() {
      try {
        const {
          initCesium,
          hasPreviewTerrainSupport,
          createPreviewTerrainProvider,
          createPreviewImageryProvider,
        } = await import("@/lib/cesium");
        const Cesium = await import("cesium");

        if (!hasPreviewTerrainSupport()) {
          document.body.dataset.previewError =
            "Preview capability unavailable";
          return;
        }

        const lat = parseFloat(searchParams.get("lat") || "");
        const lng = parseFloat(searchParams.get("lng") || "");
        const altitudeMeters = parseFloat(
          searchParams.get("altitudeMeters") || "",
        );
        const headingDegrees = parseFloat(
          searchParams.get("headingDegrees") || "",
        );
        const pitchDegrees = parseFloat(
          searchParams.get("pitchDegrees") || "",
        );
        const rollDegrees = parseFloat(
          searchParams.get("rollDegrees") || "",
        );
        const fovDegrees = parseFloat(searchParams.get("fovDegrees") || "");

        if (
          [
            lat,
            lng,
            altitudeMeters,
            headingDegrees,
            pitchDegrees,
            rollDegrees,
            fovDegrees,
          ].some((v) => !Number.isFinite(v))
        ) {
          document.body.dataset.previewError = "Invalid camera parameters";
          return;
        }

        initCesium();

        if (destroyed || !containerRef.current) return;

        const creditContainer = document.createElement("div");
        creditContainer.style.display = "none";

        const terrainProvider = await createPreviewTerrainProvider();

        if (destroyed) return;

        viewer = new Cesium.Viewer(containerRef.current, {
          terrainProvider: terrainProvider || undefined,
          animation: false,
          baseLayerPicker: false,
          fullscreenButton: false,
          geocoder: false,
          homeButton: false,
          infoBox: false,
          sceneModePicker: false,
          selectionIndicator: false,
          timeline: false,
          navigationHelpButton: false,
          navigationInstructionsInitiallyVisible: false,
          creditContainer,
          requestRenderMode: false,
          maximumRenderTimeChange: Infinity,
        });

        viewer.imageryLayers.removeAll();
        const imageryProvider = await createPreviewImageryProvider();
        viewer.imageryLayers.addImageryProvider(imageryProvider);

        viewer.camera.setView({
          destination: Cesium.Cartesian3.fromDegrees(
            lng,
            lat,
            altitudeMeters,
          ),
          orientation: {
            heading: Cesium.Math.toRadians(headingDegrees),
            pitch: Cesium.Math.toRadians(pitchDegrees),
            roll: Cesium.Math.toRadians(rollDegrees),
          },
        });

        viewer.camera.frustum.fov = Cesium.Math.toRadians(fovDegrees);

        const TIMEOUT = 20000;
        const startTime = Date.now();

        await new Promise<void>((resolve, reject) => {
          let settledFrames = 0;

          function checkReady() {
            if (destroyed) {
              reject(new Error("Destroyed"));
              return;
            }
            if (Date.now() - startTime > TIMEOUT) {
              reject(new Error("Render timeout"));
              return;
            }

            const globe = viewer.scene.globe;
            if (globe && globe.tilesLoaded) {
              settledFrames++;
              if (settledFrames >= 2) {
                resolve();
                return;
              }
            } else {
              settledFrames = 0;
            }

            requestAnimationFrame(checkReady);
          }

          requestAnimationFrame(checkReady);
        });

        if (destroyed) return;

        document.body.dataset.previewReady = "true";
      } catch (err) {
        if (!destroyed) {
          document.body.dataset.previewError =
            err instanceof Error ? err.message : String(err);
        }
      }
    }

    init();

    return () => {
      destroyed = true;
      if (viewer && !viewer.isDestroyed()) {
        viewer.destroy();
      }
    };
  }, [searchParams]);

  return (
    <div
      ref={containerRef}
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        width: "100vw",
        height: "100vh",
        margin: 0,
        padding: 0,
        overflow: "hidden",
      }}
    />
  );
}

export default function PreviewRenderPage() {
  return (
    <Suspense fallback={null}>
      <PreviewRenderer />
    </Suspense>
  );
}
