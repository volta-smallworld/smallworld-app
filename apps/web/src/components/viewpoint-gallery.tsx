"use client";

import {
  RankedViewpoint,
  ViewpointPreviewState,
  ViewpointPreviewStatus,
} from "@/types/terrain";

interface ViewpointGalleryProps {
  viewpoints: RankedViewpoint[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  previewStates: Record<string, ViewpointPreviewState>;
  onRetryPreview: (id: string) => void;
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
            background:
              "linear-gradient(135deg, rgba(30,30,60,0.9) 0%, rgba(40,40,80,0.9) 100%)",
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
            background: "rgba(127,29,29,0.5)",
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
              backgroundColor: "rgba(239,68,68,0.7)",
              color: "#fff",
              border: "1px solid rgba(239,68,68,0.9)",
              borderRadius: 4,
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

  // idle: gray placeholder with composition + score overlay
  return (
    <div style={containerStyle}>
      <div
        style={{
          ...overlayStyle,
          background:
            "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
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
            fontSize: 20,
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

export default function ViewpointGallery({
  viewpoints,
  selectedId,
  onSelect,
  previewStates,
  onRetryPreview,
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
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>
          Viewpoints ({viewpoints.length})
        </h3>

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
                borderRadius: 6,
                border: `2px solid ${isSelected ? "#22d3ee" : "rgba(255,255,255,0.08)"}`,
                backgroundColor: isSelected
                  ? "rgba(34,211,238,0.06)"
                  : "rgba(255,255,255,0.03)",
                cursor: "pointer",
                overflow: "hidden",
                transition: "border-color 0.15s, background-color 0.15s",
              }}
            >
              {/* Preview region */}
              <PreviewRegion
                viewpoint={vp}
                state={previewState}
                onRetry={() => onRetryPreview(vp.id)}
              />

              {/* Metadata below preview */}
              <div style={{ padding: "10px 12px 12px" }}>
                {/* Row 1: composition type + score */}
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: 6,
                  }}
                >
                  <span style={{ fontWeight: 600, fontSize: 13, color }}>
                    {vp.composition}
                  </span>
                  <span
                    style={{
                      fontFamily: "monospace",
                      fontSize: 13,
                      color: "#ccc",
                      fontWeight: 600,
                    }}
                  >
                    {vp.score.toFixed(3)}
                  </span>
                </div>

                {/* Row 2: scene type */}
                <div style={{ fontSize: 12, color: "#999", marginBottom: 4 }}>
                  {vp.sceneType}
                </div>

                {/* Row 3: lat/lng */}
                <div style={{ fontSize: 11, color: "#777", marginBottom: 3 }}>
                  {vp.camera.lat.toFixed(4)}, {vp.camera.lng.toFixed(4)}
                </div>

                {/* Row 4: altitude + heading */}
                <div style={{ fontSize: 11, color: "#777", marginBottom: 3 }}>
                  {vp.camera.altitudeMeters.toFixed(0)}m alt &middot;{" "}
                  {vp.camera.headingDegrees.toFixed(0)}&deg; heading
                </div>

                {/* Row 5: pitch */}
                <div style={{ fontSize: 11, color: "#777", marginBottom: 6 }}>
                  pitch {vp.camera.pitchDegrees.toFixed(1)}&deg;
                </div>

                {/* Top 3 score components */}
                <div
                  style={{
                    fontSize: 11,
                    color: "#555",
                    borderTop: "1px solid rgba(255,255,255,0.06)",
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
                      <span style={{ color: "#666" }}>{key}</span>
                      <span style={{ fontFamily: "monospace", color: "#888" }}>
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
