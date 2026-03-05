"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { useQueryStates, parseAsFloat, parseAsInteger } from "nuqs";
import ControlPanel from "@/components/control-panel";
import TerrainResultPanel from "@/components/terrain-result-panel";
import SceneList from "@/components/scene-list";
import ViewpointGallery from "@/components/viewpoint-gallery";
import { analyzeTerrain, findViewpoints } from "@/lib/api";
import { fetchStyleCapabilities, uploadStyleReference, findStyleViewpoints } from "@/lib/style-api";
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
  StyleFetchState,
  StyleReferenceCapability,
  StyleReferenceUploadResponse,
  StyleViewpointSearchResponse,
  StyleVerificationResult,
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
  const [locationParams, setLocationParams] = useQueryStates(
    {
      lat: parseAsFloat,
      lng: parseAsFloat,
      r: parseAsInteger.withDefault(5000),
    },
    { history: "push" },
  );
  const [cameraParams, setCameraParams] = useQueryStates(
    {
      clat: parseAsFloat,
      clng: parseAsFloat,
      alt: parseAsFloat,
      h: parseAsFloat,
      p: parseAsFloat,
    },
    { history: "push" },
  );

  const center: LatLng | null = useMemo(
    () =>
      locationParams.lat != null && locationParams.lng != null
        ? { lat: locationParams.lat, lng: locationParams.lng }
        : null,
    [locationParams.lat, locationParams.lng],
  );
  const radiusMeters = locationParams.r;

  const initialCamera = useMemo(() => {
    if (
      cameraParams.clat != null &&
      cameraParams.clng != null &&
      cameraParams.alt != null
    ) {
      return {
        lat: cameraParams.clat,
        lng: cameraParams.clng,
        altitudeMeters: cameraParams.alt,
        headingDegrees: cameraParams.h ?? 0,
        pitchDegrees: cameraParams.p ?? -90,
      };
    }
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // only compute once on mount

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
  // Style reference state
  const [styleCapability, setStyleCapability] = useState<StyleReferenceCapability | null>(null);
  const [styleReference, setStyleReference] = useState<StyleReferenceUploadResponse | null>(null);
  const [styleUploadState, setStyleUploadState] = useState<StyleFetchState>("idle");
  const [styleFetchState, setStyleFetchState] = useState<StyleFetchState>("idle");
  const [styleViewpointResult, setStyleViewpointResult] = useState<StyleViewpointSearchResponse | null>(null);
  const [styleError, setStyleError] = useState<string | null>(null);
  const [styleVerifications, setStyleVerifications] = useState<Record<string, StyleVerificationResult>>({});
  const previewControllersRef = useRef<Record<string, AbortController>>({});

  const handleSelectCenter = useCallback(
    (latlng: LatLng) => {
      setLocationParams({ lat: latlng.lat, lng: latlng.lng });
      // Clear camera params when selecting a new center
      setCameraParams({ clat: null, clng: null, alt: null, h: null, p: null });
    },
    [setLocationParams, setCameraParams],
  );

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
      const isDeselecting = selectedViewpointId === id;
      setSelectedViewpointId((prev) => (prev === id ? null : id));

      // Update camera URL params
      if (isDeselecting) {
        setCameraParams({ clat: null, clng: null, alt: null, h: null, p: null });
      } else {
        const vpForUrl = id.startsWith("style-")
          ? styleViewpointResult?.viewpoints.find((v) => `style-${v.id}` === id)
          : viewpointResult?.viewpoints.find((v) => v.id === id);
        if (vpForUrl) {
          setCameraParams({
            clat: vpForUrl.camera.lat,
            clng: vpForUrl.camera.lng,
            alt: vpForUrl.camera.altitudeMeters,
            h: vpForUrl.camera.headingDegrees,
            p: vpForUrl.camera.pitchDegrees,
          });
        }
      }

      // Trigger on-demand preview if needed
      if (previewCapability?.enabled) {
        const vp = id.startsWith("style-")
          ? styleViewpointResult?.viewpoints.find((v) => `style-${v.id}` === id)
          : viewpointResult?.viewpoints.find((v) => v.id === id);
        const currentState = previewStates[id];
        if (vp && (!currentState || currentState.status === "idle")) {
          const previewVp: RankedViewpoint = id.startsWith("style-")
            ? {
                id,
                sceneId: vp.sceneId,
                sceneType: vp.sceneType,
                composition: vp.composition,
                camera: vp.camera,
                targets: vp.targets,
                distanceMetersApprox: vp.distanceMetersApprox,
                score: vp.score,
                scoreBreakdown: vp.scoreBreakdown,
                validation: vp.validation,
              }
            : vp;
          renderPreview(previewVp, previewGenerationRef.current);
        }
      }
    },
    [previewCapability, viewpointResult, styleViewpointResult, previewStates, renderPreview, selectedViewpointId, setCameraParams],
  );

  const handleRetryPreview = useCallback(
    (id: string) => {
      const vp = id.startsWith("style-")
        ? styleViewpointResult?.viewpoints.find((v) => `style-${v.id}` === id)
        : viewpointResult?.viewpoints.find((v) => v.id === id);
      if (!vp) return;

      const previewVp: RankedViewpoint = id.startsWith("style-")
        ? {
            id,
            sceneId: vp.sceneId,
            sceneType: vp.sceneType,
            composition: vp.composition,
            camera: vp.camera,
            targets: vp.targets,
            distanceMetersApprox: vp.distanceMetersApprox,
            score: vp.score,
            scoreBreakdown: vp.scoreBreakdown,
            validation: vp.validation,
          }
        : vp;

      renderPreview(previewVp, previewGenerationRef.current);
    },
    [viewpointResult, styleViewpointResult, renderPreview],
  );

  const handleUploadStyleReference = useCallback(async (file: File) => {
    setStyleUploadState("loading");
    try {
      const ref = await uploadStyleReference(file);
      setStyleReference(ref);
      setStyleUploadState("success");
    } catch {
      setStyleUploadState("error");
    }
  }, []);

  const handleFindStyledViewpoints = useCallback(async () => {
    if (!center || fetchState !== "success" || !styleReference) return;

    setStyleFetchState("loading");
    setStyleError(null);
    setStyleViewpointResult(null);
    setStyleVerifications({});

    try {
      const data = await findStyleViewpoints({
        center,
        radiusMeters,
        weights,
        compositions: selectedCompositions,
        referenceId: styleReference.referenceId,
      });

      setStyleViewpointResult(data);
      setStyleFetchState("success");

      // Eager preview + verification for top N
      const eagerCount = parseInt(process.env.NEXT_PUBLIC_STYLE_VERIFY_EAGER_COUNT || "3", 10);
      const eagerVps = data.viewpoints.slice(0, eagerCount);

      for (const vp of eagerVps) {
        renderPreview(
          {
            id: `style-${vp.id}`,
            sceneId: vp.sceneId,
            sceneType: vp.sceneType,
            composition: vp.composition,
            camera: vp.camera,
            targets: vp.targets,
            distanceMetersApprox: vp.distanceMetersApprox,
            score: vp.score,
            scoreBreakdown: vp.scoreBreakdown,
            validation: vp.validation,
          } as RankedViewpoint,
          previewGenerationRef.current,
        );
      }
    } catch (err) {
      setStyleError(err instanceof Error ? err.message : "Unknown error");
      setStyleFetchState("error");
    }
  }, [center, radiusMeters, weights, selectedCompositions, fetchState, styleReference, renderPreview]);

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

  // Fetch style capabilities on mount
  useEffect(() => {
    fetchStyleCapabilities()
      .then(setStyleCapability)
      .catch(() =>
        setStyleCapability({
          enabled: false,
          hedLoaded: false,
          clipLoaded: false,
          lpipsLoaded: false,
          maxUploadBytes: 0,
          message: "Failed to check style capabilities",
        }),
      );
  }, []);

  return (
    <div style={{ position: "relative", width: "100vw", height: "100vh", overflow: "hidden" }}>
      <style>{`
        .sw-panel::-webkit-scrollbar { width: 4px; }
        .sw-panel::-webkit-scrollbar-track { background: transparent; }
        .sw-panel::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }
      `}</style>

      {/* Full-screen globe — behind everything */}
      <CesiumMap
        center={center}
        radiusMeters={radiusMeters}
        onSelectCenter={handleSelectCenter}
        analysisResult={result}
        overlays={overlays}
        viewpointResult={viewpointResult}
        selectedViewpointId={selectedViewpointId}
        initialCamera={initialCamera}
      />

      {/* Map overlay: empty state when no point selected */}
      {!center && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            zIndex: 5,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            pointerEvents: "none",
          }}
        >
          <div
            style={{
              textAlign: "center",
              padding: "32px 40px",
              borderRadius: 16,
              background: "rgba(8, 10, 16, 0.7)",
              backdropFilter: "blur(12px)",
              WebkitBackdropFilter: "blur(12px)",
              border: "1px solid rgba(255, 255, 255, 0.08)",
            }}
          >
            <svg
              width="48"
              height="48"
              viewBox="0 0 48 48"
              fill="none"
              style={{ margin: "0 auto 16px", display: "block", opacity: 0.6 }}
            >
              <circle cx="24" cy="24" r="16" stroke="#22d3ee" strokeWidth="1.5" strokeDasharray="4 4" />
              <line x1="24" y1="4" x2="24" y2="16" stroke="#22d3ee" strokeWidth="1.5" />
              <line x1="24" y1="32" x2="24" y2="44" stroke="#22d3ee" strokeWidth="1.5" />
              <line x1="4" y1="24" x2="16" y2="24" stroke="#22d3ee" strokeWidth="1.5" />
              <line x1="32" y1="24" x2="44" y2="24" stroke="#22d3ee" strokeWidth="1.5" />
              <circle cx="24" cy="24" r="3" fill="#22d3ee" fillOpacity="0.4" />
            </svg>
            <div style={{ fontSize: 16, fontWeight: 600, color: "#f0f0f0", marginBottom: 6 }}>
              Click anywhere to explore
            </div>
            <div style={{ fontSize: 13, color: "#666" }}>
              Select a point on the globe to begin terrain analysis
            </div>
          </div>
        </div>
      )}

      {/* Floating panel — top left */}
      <div
        className="sw-panel"
        style={{
          position: "absolute",
          top: 16,
          left: 16,
          width: 360,
          maxHeight: "calc(100vh - 32px)",
          overflowY: "auto",
          overflowX: "hidden",
          zIndex: 10,
          background: "rgba(8, 10, 16, 0.88)",
          backdropFilter: "blur(20px)",
          WebkitBackdropFilter: "blur(20px)",
          border: "1px solid rgba(255, 255, 255, 0.06)",
          borderRadius: 12,
          boxShadow: "0 8px 32px rgba(0, 0, 0, 0.5)",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Panel header */}
        <div
          style={{
            padding: "14px 16px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            borderBottom: "1px solid rgba(255, 255, 255, 0.06)",
          }}
        >
          <span
            style={{
              fontSize: 15,
              fontWeight: 700,
              color: "#f0f0f0",
              letterSpacing: "-0.01em",
            }}
          >
            Smallworld
          </span>
          <Link
            href="/chat"
            style={{
              padding: "4px 12px",
              borderRadius: 6,
              background: "rgba(255,255,255,0.06)",
              color: "#a0a0a0",
              fontSize: 12,
              fontWeight: 500,
              textDecoration: "none",
            }}
          >
            Chat
          </Link>
        </div>

        <ControlPanel
          center={center}
          radiusMeters={radiusMeters}
          onRadiusChange={(r: number) => setLocationParams({ r })}
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
          styleCapability={styleCapability}
          styleReference={styleReference}
          styleUploadState={styleUploadState}
          onUploadStyleReference={handleUploadStyleReference}
          onFindStyledViewpoints={handleFindStyledViewpoints}
          styleFetchState={styleFetchState}
        />

        <div style={{ borderTop: "1px solid rgba(255, 255, 255, 0.06)" }}>
          <TerrainResultPanel
            fetchState={fetchState}
            result={result}
            error={error}
          />
        </div>

        {result && fetchState === "success" && (
          <div style={{ borderTop: "1px solid rgba(255, 255, 255, 0.06)" }}>
            <SceneList scenes={result.scenes} />
          </div>
        )}
      </div>

      {/* Floating panel — top right (viewpoints) */}
      {(viewpointFetchState === "success" && viewpointResult && viewpointResult.viewpoints.length > 0) ||
       (styleFetchState === "success" && styleViewpointResult && styleViewpointResult.viewpoints.length > 0) ? (
        <div
          className="sw-panel"
          style={{
            position: "absolute",
            top: 16,
            right: 16,
            width: 340,
            maxHeight: "calc(100vh - 32px)",
            overflowY: "auto",
            overflowX: "hidden",
            zIndex: 10,
            background: "rgba(8, 10, 16, 0.88)",
            backdropFilter: "blur(20px)",
            WebkitBackdropFilter: "blur(20px)",
            border: "1px solid rgba(255, 255, 255, 0.06)",
            borderRadius: 12,
            boxShadow: "0 8px 32px rgba(0, 0, 0, 0.5)",
            display: "flex",
            flexDirection: "column",
          }}
        >
          {viewpointFetchState === "success" &&
            viewpointResult &&
            viewpointResult.viewpoints.length > 0 && (
            <ViewpointGallery
              viewpoints={viewpointResult.viewpoints}
              selectedId={selectedViewpointId}
              onSelect={handleSelectViewpoint}
              previewStates={previewStates}
              onRetryPreview={handleRetryPreview}
            />
          )}

          {viewpointFetchState === "error" && viewpointError && (
            <div style={{ padding: 16, color: "#ef4444", fontSize: 13 }}>
              Viewpoint error: {viewpointError}
            </div>
          )}

          {styleFetchState === "success" &&
            styleViewpointResult &&
            styleViewpointResult.viewpoints.length > 0 && (
            <div style={{ borderTop: "1px solid rgba(255, 255, 255, 0.06)" }}>
              <ViewpointGallery
                viewpoints={styleViewpointResult.viewpoints.map((vp) => ({
                  id: `style-${vp.id}`,
                  sceneId: vp.sceneId,
                  sceneType: vp.sceneType,
                  composition: vp.composition,
                  camera: vp.camera,
                  targets: vp.targets,
                  distanceMetersApprox: vp.distanceMetersApprox,
                  score: vp.score,
                  scoreBreakdown: vp.scoreBreakdown,
                  validation: vp.validation,
                }))}
                selectedId={selectedViewpointId}
                onSelect={handleSelectViewpoint}
                previewStates={previewStates}
                onRetryPreview={handleRetryPreview}
                isStyleMode={true}
                styleViewpoints={styleViewpointResult.viewpoints}
                styleVerifications={styleVerifications}
              />
            </div>
          )}

          {styleFetchState === "error" && styleError && (
            <div style={{ padding: 16, color: "#ef4444", fontSize: 13 }}>
              Style search error: {styleError}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
