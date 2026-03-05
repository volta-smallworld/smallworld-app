"use client";

import { useState } from "react";
import {
  LatLng,
  AnalysisWeights,
  AnalysisOverlayKey,
  TerrainFetchState,
  CompositionType,
  ViewpointFetchState,
  StyleFetchState,
  StyleReferenceCapability,
  StyleReferenceUploadResponse,
} from "@/types/terrain";

const WEIGHT_KEYS: { key: keyof AnalysisWeights; label: string }[] = [
  { key: "peaks", label: "Peaks" },
  { key: "ridges", label: "Ridges" },
  { key: "cliffs", label: "Cliffs" },
  { key: "water", label: "Water" },
  { key: "relief", label: "Relief" },
];

const OVERLAY_KEYS: { key: AnalysisOverlayKey; label: string; color: string }[] = [
  { key: "peaks", label: "Peaks", color: "#eab308" },
  { key: "ridges", label: "Ridges", color: "#d97706" },
  { key: "cliffs", label: "Cliffs", color: "#f97316" },
  { key: "waterChannels", label: "Water", color: "#3b82f6" },
  { key: "hotspots", label: "Hotspots", color: "#06b6d4" },
  { key: "viewpoints", label: "Viewpoints", color: "#d946ef" },
];

const COMPOSITION_OPTIONS: { key: CompositionType; label: string; color: string }[] = [
  { key: "ruleOfThirds", label: "Rule of 3rds", color: "#10b981" },
  { key: "goldenRatio", label: "Golden Ratio", color: "#f59e0b" },
  { key: "leadingLine", label: "Leading Line", color: "#8b5cf6" },
  { key: "symmetry", label: "Symmetry", color: "#ec4899" },
];

const sectionHeaderStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  textTransform: "uppercase",
  letterSpacing: "0.08em",
  color: "#555",
  marginBottom: 8,
};

const sectionStyle: React.CSSProperties = {
  padding: "14px 16px",
  borderTop: "1px solid rgba(255,255,255,0.06)",
};

interface ControlPanelProps {
  center: LatLng | null;
  radiusMeters: number;
  onRadiusChange: (radius: number) => void;
  weights: AnalysisWeights;
  onWeightsChange: (weights: AnalysisWeights) => void;
  overlays: Record<AnalysisOverlayKey, boolean>;
  onToggleOverlay: (key: AnalysisOverlayKey) => void;
  onAnalyze: () => void;
  fetchState: TerrainFetchState;
  selectedCompositions: CompositionType[];
  onCompositionsChange: (compositions: CompositionType[]) => void;
  onFindViewpoints: () => void;
  viewpointFetchState: ViewpointFetchState;
  // Style reference props
  styleCapability: StyleReferenceCapability | null;
  styleReference: StyleReferenceUploadResponse | null;
  styleUploadState: StyleFetchState;
  onUploadStyleReference: (file: File) => void;
  onFindStyledViewpoints: () => void;
  styleFetchState: StyleFetchState;
}

export default function ControlPanel({
  center,
  radiusMeters,
  onRadiusChange,
  weights,
  onWeightsChange,
  overlays,
  onToggleOverlay,
  onAnalyze,
  fetchState,
  selectedCompositions,
  onCompositionsChange,
  onFindViewpoints,
  viewpointFetchState,
  styleCapability,
  styleReference,
  styleUploadState,
  onUploadStyleReference,
  onFindStyledViewpoints,
  styleFetchState,
}: ControlPanelProps) {
  const [showWeights, setShowWeights] = useState<boolean>(false);
  const radiusKm = (radiusMeters / 1000).toFixed(1);

  // Derive workflow step
  // Step 1: center is null
  // Step 2: center set, fetchState idle/error
  // Step 3: fetchState success
  // Step 4: viewpointFetchState success
  const showConfigure = center !== null;
  const showExplore = fetchState === "success";
  const showStyleReference = fetchState === "success";

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>

      {/* ── LOCATION section (always visible) ── */}
      {!center ? (
        <div style={{ padding: "14px 16px", color: "#555", fontSize: 13 }}>
          Select a point on the globe
        </div>
      ) : (
        <div style={{ padding: "14px 16px" }}>
          <div style={sectionHeaderStyle}>LOCATION</div>
          <div style={{ fontFamily: "monospace", fontSize: 14, color: "#d0d0d0" }}>
            {center.lat.toFixed(4)}°, {center.lng.toFixed(4)}°
          </div>
        </div>
      )}

      {/* ── CONFIGURE section (visible when center is set) ── */}
      {showConfigure && (
        <div style={sectionStyle}>
          <div style={sectionHeaderStyle}>CONFIGURE</div>

          {/* Radius slider */}
          <div style={{ marginBottom: 12 }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 6,
              }}
            >
              <span style={sectionHeaderStyle}>RADIUS</span>
              <span style={{ fontFamily: "monospace", fontSize: 13, color: "#d0d0d0" }}>
                {radiusKm} km
              </span>
            </div>
            <input
              type="range"
              min={1000}
              max={50000}
              step={500}
              value={radiusMeters}
              onChange={(e) => onRadiusChange(Number(e.target.value))}
              style={{ width: "100%", accentColor: "#22d3ee" }}
            />
          </div>

          {/* Tune weights collapsible */}
          <div style={{ marginBottom: 12 }}>
            <div
              onClick={() => setShowWeights(!showWeights)}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "8px 0",
                cursor: "pointer",
                fontSize: 12,
                color: "#666",
                userSelect: "none",
              }}
            >
              <span>Tune weights</span>
              <span
                style={{
                  fontSize: 10,
                  transform: showWeights ? "rotate(180deg)" : "rotate(0)",
                  transition: "transform 200ms",
                }}
              >
                ▼
              </span>
            </div>
            {showWeights && (
              <div style={{ paddingBottom: 8 }}>
                {WEIGHT_KEYS.map(({ key, label }) => (
                  <div key={key} style={{ marginBottom: 4 }}>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        fontSize: 12,
                        color: "#aaa",
                      }}
                    >
                      <span>{label}</span>
                      <span style={{ fontFamily: "monospace" }}>{weights[key].toFixed(2)}</span>
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={2}
                      step={0.25}
                      value={weights[key]}
                      onChange={(e) =>
                        onWeightsChange({ ...weights, [key]: Number(e.target.value) })
                      }
                      style={{ width: "100%", accentColor: "#22d3ee" }}
                    />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Analyze button */}
          <button
            onClick={onAnalyze}
            disabled={!center || fetchState === "loading"}
            style={{
              width: "100%",
              padding: "10px 16px",
              fontSize: 13,
              fontWeight: 600,
              backgroundColor:
                !center || fetchState === "loading" ? "rgba(255,255,255,0.06)" : "#22d3ee",
              color: !center || fetchState === "loading" ? "#555" : "#000",
              border: "none",
              borderRadius: 8,
              cursor: !center || fetchState === "loading" ? "not-allowed" : "pointer",
              transition: "all 200ms",
            }}
          >
            {fetchState === "loading" ? "Analyzing..." : "Analyze Terrain"}
          </button>
        </div>
      )}

      {/* ── EXPLORE section (visible when fetchState === 'success') ── */}
      {showExplore && (
        <div style={sectionStyle}>
          <div style={sectionHeaderStyle}>EXPLORE</div>

          {/* Overlay toggles */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ ...sectionHeaderStyle, marginBottom: 6 }}>OVERLAYS</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {OVERLAY_KEYS.map(({ key, label, color }) => {
                const active = overlays[key];
                return (
                  <button
                    key={key}
                    onClick={() => onToggleOverlay(key)}
                    style={{
                      padding: "4px 10px",
                      fontSize: 11,
                      fontWeight: 500,
                      border: `1px solid ${active ? "transparent" : color + "40"}`,
                      borderRadius: 6,
                      cursor: "pointer",
                      backgroundColor: active ? color : "transparent",
                      color: active ? "#000" : color,
                      transition: "all 150ms",
                    }}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Composition picker */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ ...sectionHeaderStyle, marginBottom: 6 }}>COMPOSITION</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {COMPOSITION_OPTIONS.map(({ key, label, color }) => {
                const active = selectedCompositions.includes(key);
                return (
                  <button
                    key={key}
                    onClick={() => {
                      if (active) {
                        onCompositionsChange(selectedCompositions.filter((c) => c !== key));
                      } else {
                        onCompositionsChange([...selectedCompositions, key]);
                      }
                    }}
                    style={{
                      padding: "4px 10px",
                      fontSize: 11,
                      fontWeight: 500,
                      border: `1px solid ${active ? "transparent" : color + "40"}`,
                      borderRadius: 6,
                      cursor: "pointer",
                      backgroundColor: active ? color : "transparent",
                      color: active ? "#000" : color,
                      transition: "all 150ms",
                    }}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Find Viewpoints button */}
          {(() => {
            const disabled =
              viewpointFetchState === "loading" || selectedCompositions.length === 0;
            return (
              <button
                onClick={onFindViewpoints}
                disabled={disabled}
                style={{
                  width: "100%",
                  padding: "10px 16px",
                  fontSize: 13,
                  fontWeight: 600,
                  backgroundColor: disabled ? "rgba(255,255,255,0.06)" : "#10b981",
                  color: disabled ? "#555" : "#000",
                  border: "none",
                  borderRadius: 8,
                  cursor: disabled ? "not-allowed" : "pointer",
                  transition: "all 200ms",
                }}
              >
                {viewpointFetchState === "loading" ? "Finding Viewpoints..." : "Find Viewpoints"}
              </button>
            );
          })()}
        </div>
      )}

      {/* ── STYLE REFERENCE section (visible when fetchState === 'success') ── */}
      {showStyleReference && (
        <div style={sectionStyle}>
          <div style={sectionHeaderStyle}>STYLE REFERENCE</div>

          {styleCapability && !styleCapability.enabled && (
            <div style={{ fontSize: 12, color: "#666", marginBottom: 8 }}>
              Style search unavailable: {styleCapability.message}
            </div>
          )}

          <label
            style={{
              display: "block",
              padding: "8px 12px",
              fontSize: 13,
              fontWeight: 500,
              border: "1px dashed rgba(255,255,255,0.12)",
              borderRadius: 8,
              textAlign: "center",
              cursor: styleUploadState === "loading" ? "not-allowed" : "pointer",
              color: "#666",
              marginBottom: 8,
            }}
          >
            {styleUploadState === "loading"
              ? "Uploading..."
              : styleReference
                ? "Replace Reference Image"
                : "Upload Reference Image"}
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              style={{ display: "none" }}
              disabled={styleUploadState === "loading"}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) onUploadStyleReference(file);
                e.target.value = "";
              }}
            />
          </label>

          {styleReference && (
            <div
              style={{
                marginBottom: 8,
                borderRadius: 6,
                border: "1px solid #444",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: "100%",
                  paddingBottom: "56.25%",
                  position: "relative",
                  backgroundColor: "#1a1a2e",
                }}
              >
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: "#888",
                    fontSize: 12,
                  }}
                >
                  {styleReference.filename} ({styleReference.width}x{styleReference.height})
                </div>
              </div>
              <div style={{ padding: "6px 8px", fontSize: 11, color: "#777" }}>
                <div>Edge density: {styleReference.fingerprintSummary.edgeDensity.toFixed(3)}</div>
                <div>Parallelism: {styleReference.fingerprintSummary.parallelism.toFixed(3)}</div>
                <div>
                  Orientation:{" "}
                  {styleReference.fingerprintSummary.dominantOrientationDegrees.toFixed(1)}&deg;
                </div>
              </div>
            </div>
          )}

          {(() => {
            const disabled =
              !styleReference ||
              styleFetchState === "loading" ||
              selectedCompositions.length === 0;
            return (
              <button
                onClick={onFindStyledViewpoints}
                disabled={disabled}
                style={{
                  padding: "10px 16px",
                  fontSize: 13,
                  fontWeight: 600,
                  width: "100%",
                  backgroundColor: disabled ? "rgba(255,255,255,0.06)" : "#8b5cf6",
                  color: disabled ? "#555" : "#000",
                  border: "none",
                  borderRadius: 8,
                  cursor: disabled ? "not-allowed" : "pointer",
                  transition: "all 200ms",
                }}
              >
                {styleFetchState === "loading"
                  ? "Finding Styled Viewpoints..."
                  : "Find Styled Viewpoints"}
              </button>
            );
          })()}
        </div>
      )}
    </div>
  );
}
