"use client";

import dynamic from "next/dynamic";
import { useState, useCallback, useEffect, useRef } from "react";
import ControlPanel from "@/components/control-panel";
import TerrainResultPanel from "@/components/terrain-result-panel";
import SceneList from "@/components/scene-list";
import ViewpointGallery from "@/components/viewpoint-gallery";
import { analyzeTerrain, findViewpoints } from "@/lib/api";
import { fetchPreviewCapabilities, fetchViewpointPreview } from "@/lib/previews";
import {
  LatLng,
  AnalysisWeights,
  AnalysisOverlayKey,
  TerrainAnalysisResponse,
  TerrainFetchState,
  ViewpointSearchResponse,
  ViewpointFetchState,
  CompositionType,
  DEFAULT_WEIGHTS,
  PreviewCapability,
  ViewpointPreviewState,
  RankedViewpoint,
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
  viewpoints: true,
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
  const [selectedCompositions, setSelectedCompositions] = useState<CompositionType[]>(["ruleOfThirds", "goldenRatio", "leadingLine", "symmetry"]);
  const [viewpointFetchState, setViewpointFetchState] = useState<ViewpointFetchState>("idle");
  const [viewpointResult, setViewpointResult] = useState<ViewpointSearchResponse | null>(null);
  const [viewpointError, setViewpointError] = useState<string | null>(null);
  const [selectedViewpointId, setSelectedViewpointId] = useState<string | null>(null);
  const [previewCapability, setPreviewCapability] = useState<PreviewCapability | null>(null);
  const [previewStates, setPreviewStates] = useState<Record<string, ViewpointPreviewState>>({});
  const previewGenerationRef = useRef(0);
  const previewControllersRef = useRef<Record<string, AbortController>>({});

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

  const cleanupPreviews = useCallback(() => {
    Object.values(previewControllersRef.current).forEach((controller) => controller.abort());
    previewControllersRef.current = {};

    setPreviewStates((prev) => {
      Object.values(prev).forEach((state) => {
        if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
      });
      return {};
    });
  }, []);

  const renderPreview = useCallback(async (viewpoint: RankedViewpoint, generation: number) => {
    if (previewGenerationRef.current !== generation) return;

    previewControllersRef.current[viewpoint.id]?.abort();
    const controller = new AbortController();
    previewControllersRef.current[viewpoint.id] = controller;

    setPreviewStates((prev) => {
      const previousObjectUrl = prev[viewpoint.id]?.objectUrl;
      if (previousObjectUrl) {
        URL.revokeObjectURL(previousObjectUrl);
      }

      return {
        ...prev,
        [viewpoint.id]: { status: "loading", objectUrl: null, error: null },
      };
    });

    try {
      const blob = await fetchViewpointPreview(viewpoint, controller.signal);
      const objectUrl = URL.createObjectURL(blob);

      if (
        controller.signal.aborted ||
        previewGenerationRef.current !== generation
      ) {
        URL.revokeObjectURL(objectUrl);
        return;
      }

      setPreviewStates((prev) => {
        if (!(viewpoint.id in prev)) {
          return prev;
        }

        const previousObjectUrl = prev[viewpoint.id]?.objectUrl;
        if (previousObjectUrl) {
          URL.revokeObjectURL(previousObjectUrl);
        }

        return {
          ...prev,
          [viewpoint.id]: { status: "ready", objectUrl, error: null },
        };
      });
    } catch (err) {
      if (controller.signal.aborted || previewGenerationRef.current !== generation) {
        return;
      }

      setPreviewStates((prev) => ({
        ...prev,
        [viewpoint.id]: {
          status: "error",
          objectUrl: null,
          error: err instanceof Error ? err.message : String(err),
        },
      }));
    } finally {
      if (previewControllersRef.current[viewpoint.id] === controller) {
        delete previewControllersRef.current[viewpoint.id];
      }
    }
  }, []);

  const handleFindViewpoints = useCallback(async () => {
    if (!center || fetchState !== "success") return;

    previewGenerationRef.current += 1;
    const generation = previewGenerationRef.current;

    setViewpointFetchState("loading");
    setViewpointError(null);
    setSelectedViewpointId(null);
    setViewpointResult(null);
    setPreviewCapability(null);
    cleanupPreviews();

    try {
      const data = await findViewpoints({
        center,
        radiusMeters,
        weights,
        compositions: selectedCompositions,
      });

      if (previewGenerationRef.current !== generation) return;

      setViewpointResult(data);
      setViewpointFetchState("success");

      fetchPreviewCapabilities()
        .then((cap) => {
          if (previewGenerationRef.current !== generation) return;
          setPreviewCapability(cap);
          if (cap.enabled && data.viewpoints.length > 0) {
            const eagerViewpoints = data.viewpoints.slice(0, cap.eagerCount);
            eagerViewpoints.forEach((vp) => renderPreview(vp, generation));
          }
        })
        .catch(() => {
          if (previewGenerationRef.current !== generation) return;
          setPreviewCapability({
            enabled: false,
            provider: "none",
            eagerCount: 0,
            message: "Failed to check preview capabilities",
          });
        });
    } catch (err) {
      if (previewGenerationRef.current !== generation) return;
      setViewpointError(err instanceof Error ? err.message : "Unknown error");
      setViewpointFetchState("error");
    }
  }, [center, radiusMeters, weights, selectedCompositions, fetchState, cleanupPreviews, renderPreview]);

  const handleSelectViewpoint = useCallback(
    (id: string) => {
      setSelectedViewpointId((prev) => (prev === id ? null : id));

      // Trigger on-demand preview if needed
      if (previewCapability?.enabled && viewpointResult) {
        const vp = viewpointResult.viewpoints.find((v) => v.id === id);
        const currentState = previewStates[id];
        if (vp && (!currentState || currentState.status === "idle")) {
          renderPreview(vp, previewGenerationRef.current);
        }
      }
    },
    [previewCapability, viewpointResult, previewStates, renderPreview],
  );

  const handleRetryPreview = useCallback(
    (id: string) => {
      if (!viewpointResult) return;
      const vp = viewpointResult.viewpoints.find((v) => v.id === id);
      if (vp) renderPreview(vp, previewGenerationRef.current);
    },
    [viewpointResult, renderPreview],
  );

  // Initialize unsupported states when capability is disabled
  useEffect(() => {
    if (previewCapability && !previewCapability.enabled && viewpointResult) {
      setPreviewStates((prev) => {
        const next = { ...prev };
        viewpointResult.viewpoints.forEach((vp) => {
          if (!next[vp.id]) {
            next[vp.id] = { status: "unsupported", objectUrl: null, error: null };
          }
        });
        return next;
      });
    }
  }, [previewCapability, viewpointResult]);

  // Cleanup object URLs on unmount
  useEffect(() => {
    return () => cleanupPreviews();
  }, [cleanupPreviews]);

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
          selectedCompositions={selectedCompositions}
          onCompositionsChange={setSelectedCompositions}
          onFindViewpoints={handleFindViewpoints}
          viewpointFetchState={viewpointFetchState}
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
        {viewpointFetchState === "success" &&
          viewpointResult &&
          viewpointResult.viewpoints.length > 0 && (
          <div style={{ borderTop: "1px solid #333" }}>
            <ViewpointGallery
              viewpoints={viewpointResult.viewpoints}
              selectedId={selectedViewpointId}
              onSelect={handleSelectViewpoint}
              previewStates={previewStates}
              onRetryPreview={handleRetryPreview}
            />
          </div>
        )}
        {viewpointFetchState === "error" && viewpointError && (
          <div style={{ padding: 16, color: "#ef4444", fontSize: 13 }}>
            Viewpoint error: {viewpointError}
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
          viewpointResult={viewpointResult}
          selectedViewpointId={selectedViewpointId}
        />
      </div>
    </div>
  );
}
