"use client";

import { useEffect, useRef, useState } from "react";
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
  googleMapsApiKey?: string;
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

export default function RenderPreviewInner() {
  const searchParams = useSearchParams();
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const viewerRef = useRef<any>(null);
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

        const useGoogle3D = !!payload.googleMapsApiKey;

        // Set up terrain provider — when using Google 3D Tiles, use ellipsoid
        // since the tileset includes its own geometry
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        let terrainProvider: any;
        if (!useGoogle3D && payload.cesiumIonToken) {
          terrainProvider = await Cesium.createWorldTerrainAsync();
        } else {
          terrainProvider = new Cesium.EllipsoidTerrainProvider();
        }

        if (cancelled) return;

        // Set up imagery provider — skip when using Google 3D Tiles
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        let imageryProvider: any = null;
        if (!useGoogle3D) {
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

        // Set up imagery layers
        viewer.imageryLayers.removeAll();
        if (imageryProvider) {
          viewer.imageryLayers.addImageryProvider(imageryProvider);
        }

        // Load Google Photorealistic 3D Tiles when key is present
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        let tileset: any = null;
        if (useGoogle3D) {
          const tilesetUrl = `https://tile.googleapis.com/v1/3dtiles/root.json?key=${payload.googleMapsApiKey}`;
          tileset = await Cesium.Cesium3DTileset.fromUrl(tilesetUrl);
          viewer.scene.primitives.add(tileset);
        }

        viewerRef.current = viewer;

        // Force the Cesium canvas to match the requested viewport.
        // In headless browsers the canvas can default to 300x150 if
        // CSS viewport units haven't resolved when the viewer is created.
        const canvas = viewer.canvas;
        canvas.width = payload.viewport.width;
        canvas.height = payload.viewport.height;
        canvas.style.width = payload.viewport.width + "px";
        canvas.style.height = payload.viewport.height + "px";
        viewer.resize();

        // Configure scene
        if (useGoogle3D) {
          // Hide the globe — the 3D tileset provides its own terrain surface
          // and the ellipsoid would occlude it
          viewer.scene.globe.show = false;
        }
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

        // Wait for tiles to finish loading, then signal ready.
        //
        // For Google 3D Tiles: tilesLoaded is initially true before the first
        // frame triggers tile requests.  We use a two-phase approach:
        //   Phase 1 – wait for tilesLoaded to go *false* (loading started)
        //   Phase 2 – wait for tilesLoaded to go *true*  (loading finished)
        // A timeout on phase 1 handles edge cases where no tiles are needed.
        let tilesetLoadingStarted = !tileset; // skip phase 1 if no tileset
        const phase1Deadline = Date.now() + 5000; // 5s max to see loading start
        const checkReady = () => {
          if (cancelled) return;

          // Kick a render each frame so Cesium continues requesting tiles
          viewer.scene.requestRender();

          // Phase 1: wait for the tileset to begin loading
          if (tileset && !tilesetLoadingStarted) {
            if (!tileset.tilesLoaded) {
              tilesetLoadingStarted = true;
            } else if (Date.now() > phase1Deadline) {
              // Tileset never started loading — move on
              tilesetLoadingStarted = true;
            } else {
              requestAnimationFrame(checkReady);
              return;
            }
          }

          // Phase 2: wait for everything to finish
          const globeReady = viewer.scene.globe.tilesLoaded;
          const tilesetReady = tileset ? tileset.tilesLoaded : true;
          if (globeReady && tilesetReady) {
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
