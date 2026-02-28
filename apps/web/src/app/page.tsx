"use client";

import dynamic from "next/dynamic";
import { useState, useCallback } from "react";
import ControlPanel from "@/components/control-panel";
import TerrainResultPanel from "@/components/terrain-result-panel";
import { fetchElevationGrid } from "@/lib/api";
import {
  LatLng,
  ElevationGridResponse,
  TerrainFetchState,
} from "@/types/terrain";

const CesiumMap = dynamic(() => import("@/components/cesium-map"), {
  ssr: false,
  loading: () => (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "#888",
      }}
    >
      Loading globe...
    </div>
  ),
});

export default function Home() {
  const [center, setCenter] = useState<LatLng | null>(null);
  const [radiusMeters, setRadiusMeters] = useState(5000);
  const [fetchState, setFetchState] = useState<TerrainFetchState>("idle");
  const [result, setResult] = useState<ElevationGridResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSelectCenter = useCallback((latlng: LatLng) => {
    setCenter(latlng);
  }, []);

  const handleFetchTerrain = useCallback(async () => {
    if (!center) return;
    setFetchState("loading");
    setError(null);
    try {
      const data = await fetchElevationGrid({
        center,
        radiusMeters,
      });
      setResult(data);
      setFetchState("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setFetchState("error");
    }
  }, [center, radiusMeters]);

  return (
    <div style={{ display: "flex", height: "100vh", width: "100vw" }}>
      {/* Left sidebar */}
      <div
        style={{
          width: 300,
          minWidth: 300,
          borderRight: "1px solid #333",
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <ControlPanel
          center={center}
          radiusMeters={radiusMeters}
          onRadiusChange={setRadiusMeters}
          onFetchTerrain={handleFetchTerrain}
          fetchState={fetchState}
        />
        <div style={{ borderTop: "1px solid #333" }}>
          <TerrainResultPanel
            fetchState={fetchState}
            result={result}
            error={error}
          />
        </div>
      </div>

      {/* Map */}
      <div style={{ flex: 1, position: "relative" }}>
        <CesiumMap
          center={center}
          radiusMeters={radiusMeters}
          onSelectCenter={handleSelectCenter}
        />
      </div>
    </div>
  );
}
