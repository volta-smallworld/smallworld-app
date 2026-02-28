"use client";

import { useEffect, useRef } from "react";
import {
  Viewer,
  Cartesian2,
  Cartesian3,
  Color,
  EllipsoidTerrainProvider,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  Cartographic,
  Math as CesiumMath,
  ImageryLayer,
  Entity,
} from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import { initCesium, createOsmImageryProvider } from "@/lib/cesium";
import {
  LatLng,
  AnalysisOverlayKey,
  TerrainAnalysisResponse,
} from "@/types/terrain";

interface CesiumMapProps {
  center: LatLng | null;
  radiusMeters: number;
  onSelectCenter: (latlng: LatLng) => void;
  analysisResult: TerrainAnalysisResponse | null;
  overlays: Record<AnalysisOverlayKey, boolean>;
}

export default function CesiumMap({
  center,
  radiusMeters,
  onSelectCenter,
  analysisResult,
  overlays,
}: CesiumMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const markerRef = useRef<Entity | null>(null);
  const ellipseRef = useRef<Entity | null>(null);
  const overlayEntitiesRef = useRef<Entity[]>([]);

  const onSelectCenterRef = useRef(onSelectCenter);
  onSelectCenterRef.current = onSelectCenter;

  useEffect(() => {
    if (!containerRef.current) return;
    initCesium();

    const viewer = new Viewer(containerRef.current, {
      terrainProvider: new EllipsoidTerrainProvider(),
      baseLayer: new ImageryLayer(createOsmImageryProvider()),
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

    viewerRef.current = viewer;

    const handler = new ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction((event: { position: Cartesian2 }) => {
      const cartesian = viewer.camera.pickEllipsoid(
        event.position,
        viewer.scene.globe.ellipsoid
      );
      if (!cartesian) return;
      const carto = Cartographic.fromCartesian(cartesian);
      onSelectCenterRef.current({
        lat: CesiumMath.toDegrees(carto.latitude),
        lng: CesiumMath.toDegrees(carto.longitude),
      });
    }, ScreenSpaceEventType.LEFT_CLICK);

    return () => {
      handler.destroy();
      viewer.destroy();
      viewerRef.current = null;
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

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height: "100%", position: "relative" }}
    />
  );
}
