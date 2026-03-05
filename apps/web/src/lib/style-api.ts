import type {
  StyleReferenceCapability,
  StyleReferenceUploadResponse,
  StyleViewpointSearchRequest,
  StyleViewpointSearchResponse,
  StyleVerificationResult,
} from "@/types/terrain";
import { API_BASE_URL } from "@/lib/server/urls";

export async function fetchStyleCapabilities(): Promise<StyleReferenceCapability> {
  const resp = await fetch(
    `${API_BASE_URL}/api/v1/style-references/capabilities`,
  );
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    const detail = body?.detail || resp.statusText;
    throw new Error(`API error ${resp.status}: ${detail}`);
  }
  return resp.json();
}

export async function uploadStyleReference(
  file: File,
  label?: string,
): Promise<StyleReferenceUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (label) {
    formData.append("label", label);
  }

  const resp = await fetch(`${API_BASE_URL}/api/v1/style-references`, {
    method: "POST",
    body: formData,
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    const detail = body?.detail || resp.statusText;
    throw new Error(`API error ${resp.status}: ${detail}`);
  }
  return resp.json();
}

export async function findStyleViewpoints(
  req: StyleViewpointSearchRequest,
): Promise<StyleViewpointSearchResponse> {
  const resp = await fetch(
    `${API_BASE_URL}/api/v1/terrain/style-viewpoints`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    },
  );
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    const detail = body?.detail || resp.statusText;
    throw new Error(`API error ${resp.status}: ${detail}`);
  }
  return resp.json();
}

export async function verifyStyleRender(
  referenceId: string,
  viewpointId: string,
  previewBlob: Blob,
  composition: string,
  preRenderScore: number,
): Promise<StyleVerificationResult> {
  const formData = new FormData();
  formData.append("viewpointId", viewpointId);
  formData.append("preview", previewBlob, "preview.jpg");
  formData.append("composition", composition);
  formData.append("preRenderScore", preRenderScore.toString());

  const resp = await fetch(
    `${API_BASE_URL}/api/v1/style-references/${referenceId}/verify-render`,
    {
      method: "POST",
      body: formData,
    },
  );
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    const detail = body?.detail || resp.statusText;
    throw new Error(`API error ${resp.status}: ${detail}`);
  }
  return resp.json();
}
