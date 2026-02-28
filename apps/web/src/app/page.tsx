"use client";

import dynamic from "next/dynamic";
import { useState, useCallback } from "react";
import ControlPanel from "@/components/control-panel";
import TerrainResultPanel from "@/components/terrain-result-panel";
import SceneList from "@/components/scene-list";
import { analyzeTerrain } from "@/lib/api";
import {
  LatLng,
  AnalysisWeights,
  AnalysisOverlayKey,
  TerrainAnalysisResponse,
  TerrainFetchState,
  DEFAULT_WEIGHTS,
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

const DEFAULT_OVERLAYS: Record<AnalysisOverlayKey, boolean> = {
  peaks: true,
  ridges: true,
  cliffs: false,
  waterChannels: true,
  hotspots: true,
};

export default function Home() {
  const [center, setCenter] = useState<LatLng | null>(null);
  const [radiusMeters, setRadiusMeters] = useState(5000);
  const [weights, setWeights] = useState<AnalysisWeights>({ ...DEFAULT_WEIGHTS });
  const [overlays, setOverlays] = useState<Record<AnalysisOverlayKey, boolean>>({
    ...DEFAULT_OVERLAYS,
  });
  const [fetchState, setFetchState] = useState<TerrainFetchState>("idle");
  const [result, setResult] = useState<TerrainAnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSelectCenter = useCallback((latlng: LatLng) => {
    setCenter(latlng);
  }, []);

  const handleAnalyze = useCallback(async () => {
    if (!center) return;
    setFetchState("loading");
    setError(null);
    try {
      const data = await analyzeTerrain({
        center,
        radiusMeters,
        weights,
      });
      setResult(data);
      setFetchState("success");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setFetchState("error");
    }
  }, [center, radiusMeters, weights]);

  const handleToggleOverlay = useCallback((key: AnalysisOverlayKey) => {
    setOverlays((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  return (
    <div style={{ display: "flex", height: "100vh", width: "100vw" }}>
      {/* Left sidebar */}
      <div
        style={{
          width: 320,
          minWidth: 320,
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
          weights={weights}
          onWeightsChange={setWeights}
          overlays={overlays}
          onToggleOverlay={handleToggleOverlay}
          onAnalyze={handleAnalyze}
          fetchState={fetchState}
        />
        <div style={{ borderTop: "1px solid #333" }}>
          <TerrainResultPanel
            fetchState={fetchState}
            result={result}
            error={error}
          />
        </div>
        {result && fetchState === "success" && (
          <div style={{ borderTop: "1px solid #333" }}>
            <SceneList scenes={result.scenes} />
          </div>
        )}
      </div>

      {/* Map */}
      <div style={{ flex: 1, position: "relative" }}>
        <CesiumMap
          center={center}
          radiusMeters={radiusMeters}
          onSelectCenter={handleSelectCenter}
          analysisResult={result}
          overlays={overlays}
        />
      </div>
    </div>
  );
}
