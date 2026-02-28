"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

interface RenderPayload {
  camera: {
    lat: number;
    lng: number;
    altMeters: number;
    headingDeg: number;
    pitchDeg: number;
    rollDeg: number;
    fovDeg: number;
  };
  viewport: {
    width: number;
    height: number;
  };
  cesiumIonToken?: string;
  mapboxAccessToken?: string;
  anchors?: Array<{
    id: string;
    lat: number;
    lng: number;
    altMeters: number;
    desiredNormalizedX: number;
    desiredNormalizedY: number;
  }>;
}

declare global {
  interface Window {
    __SMALLWORLD_RENDER_READY__?: boolean;
    __SMALLWORLD_RENDER_ERROR__?: string;
    __SMALLWORLD_FRAME_STATE__?: {
      anchors: Array<{
        id: string;
        projected: { x: number; y: number } | null;
        desiredNormalizedX: number;
        desiredNormalizedY: number;
      }>;
    };
    CESIUM_BASE_URL?: string;
  }
}

function decodePayload(encoded: string): RenderPayload {
  // base64url -> base64
  let base64 = encoded.replace(/-/g, "+").replace(/_/g, "/");
  // Add padding if needed
  while (base64.length % 4 !== 0) {
    base64 += "=";
  }
  const json = atob(base64);
  return JSON.parse(json) as RenderPayload;
}

function RenderPreviewInner() {
  const searchParams = useSearchParams();
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<InstanceType<typeof import("cesium").Viewer> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function init() {
      try {
        const payloadParam = searchParams.get("payload");
        if (!payloadParam) {
          throw new Error("Missing 'payload' query parameter");
        }

        const payload = decodePayload(payloadParam);

        if (!payload.camera || !payload.viewport) {
          throw new Error("Payload must include 'camera' and 'viewport' fields");
        }

        // Dynamically import Cesium to ensure it runs only on the client
        const Cesium = await import("cesium");

        // Set CESIUM_BASE_URL before creating the viewer
        window.CESIUM_BASE_URL = "/cesium/";

        // Configure Ion token if provided
        if (payload.cesiumIonToken) {
          Cesium.Ion.defaultAccessToken = payload.cesiumIonToken;
        } else {
          Cesium.Ion.defaultAccessToken = "";
        }

        if (cancelled || !containerRef.current) return;

        // Set up terrain provider
        let terrainProvider: InstanceType<typeof Cesium.EllipsoidTerrainProvider> | Awaited<ReturnType<typeof Cesium.createWorldTerrainAsync>>;
        if (payload.cesiumIonToken) {
          terrainProvider = await Cesium.createWorldTerrainAsync();
        } else {
          terrainProvider = new Cesium.EllipsoidTerrainProvider();
        }

        if (cancelled) return;

        // Set up imagery provider
        let imageryProvider: InstanceType<typeof Cesium.MapboxStyleImageryProvider> | InstanceType<typeof Cesium.OpenStreetMapImageryProvider>;
        if (payload.mapboxAccessToken) {
          imageryProvider = new Cesium.MapboxStyleImageryProvider({
            styleId: "satellite-v9",
            accessToken: payload.mapboxAccessToken,
          });
        } else {
          imageryProvider = new Cesium.OpenStreetMapImageryProvider({
            url: "https://tile.openstreetmap.org/",
          });
        }

        // Create a hidden credit container
        const creditContainer = document.createElement("div");
        creditContainer.style.display = "none";

        // Create the viewer
        const viewer = new Cesium.Viewer(containerRef.current, {
          terrainProvider,
          baseLayerPicker: false,
          animation: false,
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
        });

        // Remove default imagery and add our provider
        viewer.imageryLayers.removeAll();
        viewer.imageryLayers.addImageryProvider(imageryProvider);

        viewerRef.current = viewer;

        // Configure scene
        viewer.scene.globe.enableLighting = false;
        if (viewer.scene.skyBox) {
          viewer.scene.skyBox.show = false;
        }
        if (viewer.scene.skyAtmosphere) {
          viewer.scene.skyAtmosphere.show = false;
        }
        viewer.scene.backgroundColor = Cesium.Color.BLACK;

        // Set camera position
        viewer.camera.setView({
          destination: Cesium.Cartesian3.fromDegrees(
            payload.camera.lng,
            payload.camera.lat,
            payload.camera.altMeters
          ),
          orientation: {
            heading: Cesium.Math.toRadians(payload.camera.headingDeg),
            pitch: Cesium.Math.toRadians(payload.camera.pitchDeg),
            roll: Cesium.Math.toRadians(payload.camera.rollDeg),
          },
        });

        // Set field of view
        const frustum = viewer.camera.frustum;
        if (frustum instanceof Cesium.PerspectiveFrustum) {
          frustum.fov = Cesium.Math.toRadians(payload.camera.fovDeg);
        }

        // Wait for tiles to finish loading, then signal ready
        const checkReady = () => {
          if (cancelled) return;
          if (viewer.scene.globe.tilesLoaded) {
            // Render one more frame to be safe
            viewer.scene.requestRender();
            setTimeout(() => {
              if (cancelled) return;

              // Compute anchor projections
              if (payload.anchors && payload.anchors.length > 0) {
                const frameState = payload.anchors.map((anchor) => {
                  const cartesian = Cesium.Cartesian3.fromDegrees(
                    anchor.lng,
                    anchor.lat,
                    anchor.altMeters
                  );
                  const screenPos =
                    Cesium.SceneTransforms.worldToWindowCoordinates(
                      viewer.scene,
                      cartesian
                    );
                  return {
                    id: anchor.id,
                    projected: screenPos
                      ? { x: screenPos.x, y: screenPos.y }
                      : null,
                    desiredNormalizedX: anchor.desiredNormalizedX,
                    desiredNormalizedY: anchor.desiredNormalizedY,
                  };
                });
                window.__SMALLWORLD_FRAME_STATE__ = { anchors: frameState };
              } else {
                window.__SMALLWORLD_FRAME_STATE__ = { anchors: [] };
              }

              window.__SMALLWORLD_RENDER_READY__ = true;
            }, 500);
          } else {
            requestAnimationFrame(checkReady);
          }
        };
        requestAnimationFrame(checkReady);
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Unknown render error";
        setError(message);
        window.__SMALLWORLD_RENDER_ERROR__ = message;
        window.__SMALLWORLD_RENDER_READY__ = true;
      }
    }

    init();

    return () => {
      cancelled = true;
      if (viewerRef.current && !viewerRef.current.isDestroyed()) {
        viewerRef.current.destroy();
        viewerRef.current = null;
      }
    };
  }, [searchParams]);

  if (error) {
    return (
      <div
        id="cesium-render-container"
        style={{
          width: "100vw",
          height: "100vh",
          margin: 0,
          padding: 0,
          overflow: "hidden",
          backgroundColor: "black",
          color: "red",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        Render Error: {error}
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      id="cesium-render-container"
      style={{
        width: "100vw",
        height: "100vh",
        margin: 0,
        padding: 0,
        overflow: "hidden",
      }}
    />
  );
}

export default function RenderPreviewPage() {
  return (
    <Suspense
      fallback={
        <div
          style={{
            width: "100vw",
            height: "100vh",
            backgroundColor: "black",
          }}
        />
      }
    >
      <RenderPreviewInner />
    </Suspense>
  );
}
