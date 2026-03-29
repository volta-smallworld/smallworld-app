import type { PreviewCapability, RankedViewpoint } from "@/types/terrain";

export async function fetchPreviewCapabilities(): Promise<PreviewCapability> {
  const res = await fetch("/api/viewpoint-previews/capabilities");
  if (!res.ok) {
    throw new Error(`Capabilities request failed: ${res.status}`);
  }
  return res.json();
}

export async function fetchViewpointPreview(
  viewpoint: RankedViewpoint,
  signal?: AbortSignal,
): Promise<Blob> {
  const res = await fetch("/api/viewpoint-previews", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    signal,
    body: JSON.stringify({
      viewpointId: viewpoint.id,
      camera: viewpoint.camera,
    }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ error: "Unknown error" }));
    throw new Error(errorData.detail || errorData.message || errorData.error || `Preview failed: ${res.status}`);
  }

  return res.blob();
}
