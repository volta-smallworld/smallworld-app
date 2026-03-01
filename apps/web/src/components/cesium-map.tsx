"use client";

import { useEffect, useRef } from "react";
import {
  Viewer,
  Cartesian2,
  Cartesian3,
  Color,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  Cartographic,
  Math as CesiumMath,
  Entity,
} from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import {
  initCesium,
  createPrimaryTerrainProvider,
  createPrimaryImageryProvider,
  hasGoogle3DTilesSupport,
  createGoogle3DTileset,
} from "@/lib/cesium";
import {
  LatLng,
  AnalysisOverlayKey,
  TerrainAnalysisResponse,
  ViewpointSearchResponse,
} from "@/types/terrain";

interface CesiumMapProps {
  center: LatLng | null;
  radiusMeters: number;
  onSelectCenter: (latlng: LatLng) => void;
  analysisResult: TerrainAnalysisResponse | null;
  overlays: Record<AnalysisOverlayKey, boolean>;
  viewpointResult: ViewpointSearchResponse | null;
  selectedViewpointId: string | null;
}

export default function CesiumMap({
  center,
  radiusMeters,
  onSelectCenter,
  analysisResult,
  overlays,
  viewpointResult,
  selectedViewpointId,
}: CesiumMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const markerRef = useRef<Entity | null>(null);
  const ellipseRef = useRef<Entity | null>(null);
  const overlayEntitiesRef = useRef<Entity[]>([]);
  const viewpointEntitiesRef = useRef<Entity[]>([]);

  const onSelectCenterRef = useRef(onSelectCenter);
  onSelectCenterRef.current = onSelectCenter;

  useEffect(() => {
    if (!containerRef.current) return;

    let destroyed = false;
    let handler: ScreenSpaceEventHandler | null = null;

    async function setupViewer() {
      initCesium();

      const terrainProvider = await createPrimaryTerrainProvider();
      const imageryProvider = await createPrimaryImageryProvider();

      if (destroyed || !containerRef.current) return;

      const viewer = new Viewer(containerRef.current, {
        terrainProvider: terrainProvider || undefined,
        baseLayerPicker: false,
        geocoder: false,
        homeButton: false,
        sceneModePicker: false,
        navigationHelpButton: false,
        animation: false,
        timeline: false,
        fullscreenButton: false,
        infoBox: false,
        selectionIndicator: false,
        creditContainer: document.createElement("div"),
      });

      // Replace default imagery with the capability-aware provider
      viewer.imageryLayers.removeAll();
      viewer.imageryLayers.addImageryProvider(imageryProvider);

      // Load Google Photorealistic 3D Tiles when available
      if (hasGoogle3DTilesSupport()) {
        try {
          const tileset = await createGoogle3DTileset();
          if (!destroyed) {
            viewer.scene.primitives.add(tileset);
          }
        } catch (e) {
          console.warn("Failed to load Google 3D Tiles:", e);
        }
      }

      viewerRef.current = viewer;

      handler = new ScreenSpaceEventHandler(viewer.scene.canvas);
      handler.setInputAction((event: { position: Cartesian2 }) => {
        const scene = viewer.scene;
        let cartesian =
          scene.pickPositionSupported ? scene.pickPosition(event.position) : undefined;

        if (!cartesian) {
          const ray = viewer.camera.getPickRay(event.position);
          if (ray) {
            cartesian = scene.globe.pick(ray, scene);
          }
        }

        if (!cartesian) {
          cartesian = viewer.camera.pickEllipsoid(
            event.position,
            scene.globe.ellipsoid
          );
        }

        if (!cartesian) return;
        const carto = Cartographic.fromCartesian(cartesian);
        onSelectCenterRef.current({
          lat: CesiumMath.toDegrees(carto.latitude),
          lng: CesiumMath.toDegrees(carto.longitude),
        });
      }, ScreenSpaceEventType.LEFT_CLICK);
    }

    setupViewer();

    return () => {
      destroyed = true;
      if (handler) handler.destroy();
      if (viewerRef.current) {
        viewerRef.current.destroy();
        viewerRef.current = null;
      }
    };
  }, []);

  // Update marker and ellipse when center/radius change
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    if (markerRef.current) {
      viewer.entities.remove(markerRef.current);
      markerRef.current = null;
    }
    if (ellipseRef.current) {
      viewer.entities.remove(ellipseRef.current);
      ellipseRef.current = null;
    }

    if (!center) return;

    const position = Cartesian3.fromDegrees(center.lng, center.lat);

    markerRef.current = viewer.entities.add({
      position,
      point: {
        pixelSize: 10,
        color: Color.RED,
        outlineColor: Color.WHITE,
        outlineWidth: 2,
      },
    });

    ellipseRef.current = viewer.entities.add({
      position,
      ellipse: {
        semiMajorAxis: radiusMeters as any,
        semiMinorAxis: radiusMeters as any,
        material: Color.RED.withAlpha(0.15) as any,
        outline: true as any,
        outlineColor: Color.RED.withAlpha(0.6) as any,
        outlineWidth: 2 as any,
      },
    });
  }, [center, radiusMeters]);

  // Render analysis overlays
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    // Remove old overlay entities
    for (const entity of overlayEntitiesRef.current) {
      viewer.entities.remove(entity);
    }
    overlayEntitiesRef.current = [];

    if (!analysisResult) return;

    const { features, hotspots } = analysisResult;
    const newEntities: Entity[] = [];

    // Peaks — yellow points
    if (overlays.peaks) {
      for (const peak of features.peaks) {
        const e = viewer.entities.add({
          position: Cartesian3.fromDegrees(peak.center.lng, peak.center.lat),
          point: {
            pixelSize: 8,
            color: Color.YELLOW,
            outlineColor: Color.BLACK,
            outlineWidth: 1,
          },
        });
        newEntities.push(e);
      }
    }

    // Ridges — gold polylines
    if (overlays.ridges) {
      for (const ridge of features.ridges) {
        if (ridge.path.length < 2) continue;
        const positions = ridge.path.map((p) =>
          Cartesian3.fromDegrees(p.lng, p.lat)
        );
        const e = viewer.entities.add({
          polyline: {
            positions,
            width: 2 as any,
            material: Color.fromCssColorString("#d97706") as any,
            clampToGround: true as any,
          },
        });
        newEntities.push(e);
      }
    }

    // Cliffs — orange points
    if (overlays.cliffs) {
      for (const cliff of features.cliffs) {
        const e = viewer.entities.add({
          position: Cartesian3.fromDegrees(cliff.center.lng, cliff.center.lat),
          point: {
            pixelSize: 7,
            color: Color.ORANGE,
            outlineColor: Color.BLACK,
            outlineWidth: 1,
          },
        });
        newEntities.push(e);
      }
    }

    // Water channels — blue polylines
    if (overlays.waterChannels) {
      for (const ch of features.waterChannels) {
        if (ch.path.length < 2) continue;
        const positions = ch.path.map((p) =>
          Cartesian3.fromDegrees(p.lng, p.lat)
        );
        const e = viewer.entities.add({
          polyline: {
            positions,
            width: 2 as any,
            material: Color.fromCssColorString("#3b82f6") as any,
            clampToGround: true as any,
          },
        });
        newEntities.push(e);
      }
    }

    // Hotspots — cyan points
    if (overlays.hotspots) {
      for (const hs of hotspots) {
        const e = viewer.entities.add({
          position: Cartesian3.fromDegrees(hs.center.lng, hs.center.lat),
          point: {
            pixelSize: 12,
            color: Color.CYAN.withAlpha(0.8),
            outlineColor: Color.WHITE,
            outlineWidth: 2,
          },
        });
        newEntities.push(e);
      }
    }

    overlayEntitiesRef.current = newEntities;
  }, [analysisResult, overlays]);

  // Render viewpoint overlays
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    // Remove old viewpoint entities
    for (const entity of viewpointEntitiesRef.current) {
      viewer.entities.remove(entity);
    }
    viewpointEntitiesRef.current = [];

    if (!viewpointResult || !overlays.viewpoints) return;

    const newEntities: Entity[] = [];

    for (const vp of viewpointResult.viewpoints) {
      const isSelected = vp.id === selectedViewpointId;
      const position = Cartesian3.fromDegrees(vp.camera.lng, vp.camera.lat);

      // Viewpoint marker — magenta point
      const marker = viewer.entities.add({
        position,
        point: {
          pixelSize: isSelected ? 14 : 10,
          color: Color.MAGENTA,
          outlineColor: isSelected ? Color.WHITE : Color.BLACK,
          outlineWidth: isSelected ? 3 : 1,
        },
      });
      newEntities.push(marker);

      // Heading ray — 300m projected line in heading direction
      const headingRad = (vp.camera.headingDegrees * Math.PI) / 180;
      const rayLength = 300; // meters
      const earthRadius = 6378137;
      const latRad = (vp.camera.lat * Math.PI) / 180;
      const endLat = vp.camera.lat + ((rayLength * Math.cos(headingRad)) / earthRadius) * (180 / Math.PI);
      const endLng = vp.camera.lng + ((rayLength * Math.sin(headingRad)) / (earthRadius * Math.cos(latRad))) * (180 / Math.PI);

      const ray = viewer.entities.add({
        polyline: {
          positions: [position, Cartesian3.fromDegrees(endLng, endLat)],
          width: (isSelected ? 3 : 2) as any,
          material: (isSelected ? Color.WHITE : Color.MAGENTA.withAlpha(0.7)) as any,
          clampToGround: true as any,
        },
      });
      newEntities.push(ray);
    }

    viewpointEntitiesRef.current = newEntities;
  }, [viewpointResult, selectedViewpointId, overlays]);

  // Fly camera to the selected viewpoint
  useEffect(() => {
    if (!viewerRef.current || !selectedViewpointId || !viewpointResult) return;

    const vp = viewpointResult.viewpoints.find(
      (v) => v.id === selectedViewpointId
    );
    if (!vp) return;

    const viewer = viewerRef.current;
    const { camera: cam } = vp;

    viewer.camera.flyTo({
      destination: Cartesian3.fromDegrees(
        cam.lng,
        cam.lat,
        cam.altitudeMeters
      ),
      orientation: {
        heading: CesiumMath.toRadians(cam.headingDegrees),
        pitch: CesiumMath.toRadians(cam.pitchDegrees),
        roll: CesiumMath.toRadians(cam.rollDegrees),
      },
      duration: 1.5,
    });
  }, [selectedViewpointId, viewpointResult]);

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height: "100%", position: "relative" }}
    />
  );
}
