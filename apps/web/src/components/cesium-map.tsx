"use client";

import { useEffect, useRef, useCallback } from "react";
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
} from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import { initCesium, createOsmImageryProvider } from "@/lib/cesium";
import { LatLng } from "@/types/terrain";

interface CesiumMapProps {
  center: LatLng | null;
  radiusMeters: number;
  onSelectCenter: (latlng: LatLng) => void;
}

export default function CesiumMap({
  center,
  radiusMeters,
  onSelectCenter,
}: CesiumMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const markerRef = useRef<any>(null);
  const ellipseRef = useRef<any>(null);

  // Store latest props in refs for the click handler
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

    // Remove old entities
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

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height: "100%", position: "relative" }}
    />
  );
}
