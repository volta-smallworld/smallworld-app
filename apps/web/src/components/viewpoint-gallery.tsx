"use client";

import { useState, useCallback } from "react";
import {
  RankedViewpoint,
  ViewpointPreviewState,
  ViewpointPreviewStatus,
  StyleRankedViewpoint,
  StyleVerificationResult,
} from "@/types/terrain";

interface ViewpointGalleryProps {
  viewpoints: RankedViewpoint[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  previewStates: Record<string, ViewpointPreviewState>;
  onRetryPreview: (id: string) => void;
  isStyleMode?: boolean;
  styleViewpoints?: StyleRankedViewpoint[];
  styleVerifications?: Record<string, StyleVerificationResult>;
}

const COMP_COLORS: Record<string, string> = {
  ruleOfThirds: "#f59e0b",
  goldenRatio: "#8b5cf6",
  leadingLine: "#10b981",
  symmetry: "#ec4899",
};

function PreviewRegion({
  viewpoint,
  state,
  onRetry,
}: {
  viewpoint: RankedViewpoint;
  state: ViewpointPreviewState | undefined;
  onRetry: () => void;
}) {
  const status: ViewpointPreviewStatus = state?.status ?? "idle";
  const color = COMP_COLORS[viewpoint.composition] || "#aaa";

  const containerStyle: React.CSSProperties = {
    position: "relative",
    width: "100%",
    paddingBottom: "56.25%", // 16:9 aspect ratio
    backgroundColor: "#1a1a2e",
    borderRadius: "6px 6px 0 0",
    overflow: "hidden",
  };

  const overlayStyle: React.CSSProperties = {
    position: "absolute",
    inset: 0,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
  };

  if (status === "ready" && state?.objectUrl) {
    return (
      <div style={containerStyle}>
        <img
          src={state.objectUrl}
          alt={`Preview for ${viewpoint.composition} viewpoint`}
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
          }}
        />
      </div>
    );
  }

  if (status === "loading") {
    return (
      <div style={containerStyle}>
        <div
          style={{
            ...overlayStyle,
            background: "rgba(8, 10, 16, 0.9)",
          }}
        >
          <div
            style={{
              width: 32,
              height: 32,
              border: "3px solid rgba(255,255,255,0.15)",
              borderTopColor: color,
              borderRadius: "50%",
              animation: "vpGallerySpin 0.8s linear infinite",
            }}
          />
          <span
            style={{
              marginTop: 8,
              fontSize: 11,
              color: "#888",
              letterSpacing: 0.5,
            }}
          >
            Rendering...
          </span>
        </div>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div style={containerStyle}>
        <div
          style={{
            ...overlayStyle,
            background: "rgba(127, 29, 29, 0.4)",
          }}
        >
          <span style={{ fontSize: 12, color: "#fca5a5", marginBottom: 8 }}>
            Preview failed
          </span>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onRetry();
            }}
            style={{
              padding: "4px 14px",
              fontSize: 12,
              fontWeight: 600,
              backgroundColor: "rgba(239, 68, 68, 0.6)",
              color: "#fff",
              border: "none",
              borderRadius: 6,
              cursor: "pointer",
            }}
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (status === "unsupported") {
    return (
      <div style={containerStyle}>
        <div
          style={{
            ...overlayStyle,
            background: "rgba(30,30,50,0.85)",
          }}
        >
          <span style={{ fontSize: 12, color: "#666" }}>
            Preview unavailable
          </span>
        </div>
      </div>
    );
  }

  // idle: placeholder with composition + score overlay
  return (
    <div style={containerStyle}>
      <div
        style={{
          ...overlayStyle,
          background:
            "linear-gradient(135deg, rgba(8, 10, 16, 0.95) 0%, rgba(16, 20, 30, 0.95) 100%)",
        }}
      >
        <span
          style={{
            fontSize: 14,
            fontWeight: 600,
            color,
          }}
        >
          {viewpoint.composition}
        </span>
        <span
          style={{
            marginTop: 4,
            fontSize: 18,
            fontWeight: 700,
            fontFamily: "monospace",
            color: "#ccc",
          }}
        >
          {viewpoint.score.toFixed(3)}
        </span>
      </div>
    </div>
  );
}

function CopyLinkButton() {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      // Build URL from current page with the viewpoint selected
      const url = new URL(window.location.href);
      navigator.clipboard.writeText(url.toString()).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      });
    },
    [],
  );

  return (
    <button
      onClick={handleCopy}
      title="Copy link to this viewpoint"
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: 24,
        height: 24,
        padding: 0,
        border: "none",
        borderRadius: 4,
        backgroundColor: copied ? "rgba(34, 197, 94, 0.2)" : "rgba(255, 255, 255, 0.06)",
        color: copied ? "#22c55e" : "#888",
        cursor: "pointer",
        transition: "all 150ms",
        flexShrink: 0,
      }}
    >
      {copied ? (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      ) : (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
        </svg>
      )}
    </button>
  );
}

export default function ViewpointGallery({
  viewpoints,
  selectedId,
  onSelect,
  previewStates,
  onRetryPreview,
  isStyleMode = false,
  styleViewpoints = [],
  styleVerifications = {},
}: ViewpointGalleryProps) {
  if (viewpoints.length === 0) return null;

  return (
    <>
      <style>{`
        @keyframes vpGallerySpin {
          to { transform: rotate(360deg); }
        }
      `}</style>
      <div
        style={{
          padding: "14px 16px",
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        <div
          style={{
            fontSize: 11,
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            color: "#555",
            marginBottom: 10,
          }}
        >
          {isStyleMode ? "STYLED " : ""}VIEWPOINTS ({viewpoints.length})
        </div>

        {viewpoints.map((vp) => {
          const isSelected = vp.id === selectedId;
          const color = COMP_COLORS[vp.composition] || "#aaa";
          const previewState = previewStates[vp.id];

          // Get top 3 score components
          const breakdown = vp.scoreBreakdown;
          const entries = Object.entries(breakdown) as [string, number][];
          const top3 = [...entries].sort((a, b) => b[1] - a[1]).slice(0, 3);

          return (
            <div
              key={vp.id}
              onClick={() => onSelect(vp.id)}
              style={{
                borderRadius: 8,
                border: isSelected
                  ? "2px solid rgba(34, 211, 238, 0.4)"
                  : "1px solid rgba(255, 255, 255, 0.06)",
                backgroundColor: isSelected
                  ? "rgba(34, 211, 238, 0.04)"
                  : "rgba(255, 255, 255, 0.02)",
                cursor: "pointer",
                overflow: "hidden",
                transition: "all 200ms",
              }}
            >
              {/* Preview region */}
              <PreviewRegion
                viewpoint={vp}
                state={previewState}
                onRetry={() => onRetryPreview(vp.id)}
              />

              {/* Metadata below preview */}
              <div style={{ padding: "10px 12px" }}>
                {/* Row 1: composition type + score + copy link */}
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: 6,
                    gap: 6,
                  }}
                >
                  <span style={{ fontWeight: 600, fontSize: 12, color }}>
                    {vp.composition}
                  </span>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span
                      style={{
                        fontFamily: "monospace",
                        fontSize: 13,
                        color: "#d0d0d0",
                        fontWeight: 600,
                      }}
                    >
                      {vp.score.toFixed(3)}
                    </span>
                    {isSelected && <CopyLinkButton />}
                  </div>
                </div>

                {/* Row 2: scene type */}
                <div style={{ fontSize: 11, color: "#666", marginBottom: 4 }}>
                  {vp.sceneType}
                </div>

                {/* Row 3: lat/lng */}
                <div
                  style={{
                    fontSize: 11,
                    fontFamily: "monospace",
                    color: "#555",
                    marginBottom: 3,
                  }}
                >
                  {vp.camera.lat.toFixed(4)}, {vp.camera.lng.toFixed(4)}
                </div>

                {/* Row 4: altitude + heading */}
                <div style={{ fontSize: 11, color: "#555", marginBottom: 3 }}>
                  {vp.camera.altitudeMeters.toFixed(0)}m alt &middot;{" "}
                  {vp.camera.headingDegrees.toFixed(0)}&deg; heading
                </div>

                {/* Row 5: pitch */}
                <div style={{ fontSize: 11, color: "#555", marginBottom: 6 }}>
                  pitch {vp.camera.pitchDegrees.toFixed(1)}&deg;
                </div>

                {/* Style metadata */}
                {isStyleMode && (() => {
                  const styleVp = styleViewpoints.find((s) => `style-${s.id}` === vp.id);
                  const verification = styleVerifications[vp.id];
                  if (!styleVp) return null;
                  return (
                    <div
                      style={{
                        marginBottom: 6,
                        padding: "4px 0",
                        borderTop: "1px solid rgba(124,58,237,0.2)",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          fontSize: 11,
                        }}
                      >
                        <span style={{ color: "#8b5cf6" }}>Styled</span>
                        <span
                          style={{
                            fontSize: 10,
                            padding: "1px 6px",
                            borderRadius: 4,
                            backgroundColor:
                              styleVp.style.verificationStatus === "verified"
                                ? "rgba(34,197,94,0.2)"
                                : styleVp.style.verificationStatus === "partial"
                                  ? "rgba(234,179,8,0.2)"
                                  : styleVp.style.verificationStatus === "failed"
                                    ? "rgba(239,68,68,0.2)"
                                    : "rgba(255,255,255,0.06)",
                            color:
                              styleVp.style.verificationStatus === "verified"
                                ? "#22c55e"
                                : styleVp.style.verificationStatus === "partial"
                                  ? "#eab308"
                                  : styleVp.style.verificationStatus === "failed"
                                    ? "#ef4444"
                                    : "#888",
                          }}
                        >
                          {verification?.verificationStatus || styleVp.style.verificationStatus}
                        </span>
                      </div>
                      <div
                        style={{
                          fontSize: 11,
                          fontFamily: "monospace",
                          color: "#666",
                          marginTop: 2,
                        }}
                      >
                        patch: {styleVp.style.patchSimilarity.toFixed(3)} &middot;
                        contour: {styleVp.style.contourRefinement.toFixed(3)}
                      </div>
                      <div
                        style={{
                          fontSize: 11,
                          fontFamily: "monospace",
                          color: "#666",
                        }}
                      >
                        base: {styleVp.baseScore.toFixed(3)} &middot;
                        style: {styleVp.style.preRenderScore.toFixed(3)}
                      </div>
                      {styleVp.style.matchedFeatureIds.length > 0 && (
                        <div style={{ fontSize: 10, color: "#555", marginTop: 2 }}>
                          features: {styleVp.style.matchedFeatureIds.length} matched
                        </div>
                      )}
                      {verification && verification.finalStyleScore != null && (
                        <div
                          style={{
                            fontSize: 11,
                            fontFamily: "monospace",
                            color: "#8b5cf6",
                            marginTop: 2,
                            fontWeight: 600,
                          }}
                        >
                          final: {verification.finalStyleScore.toFixed(3)}
                        </div>
                      )}
                    </div>
                  );
                })()}

                {/* Top 3 score components */}
                <div
                  style={{
                    borderTop: "1px solid rgba(255, 255, 255, 0.04)",
                    paddingTop: 6,
                  }}
                >
                  {top3.map(([key, val]) => (
                    <div
                      key={key}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        marginBottom: 2,
                      }}
                    >
                      <span style={{ fontSize: 10, color: "#555" }}>{key}</span>
                      <span
                        style={{
                          fontFamily: "monospace",
                          fontSize: 10,
                          color: "#666",
                        }}
                      >
                        {val.toFixed(3)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
