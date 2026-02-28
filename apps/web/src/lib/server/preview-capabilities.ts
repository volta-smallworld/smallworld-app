export interface PreviewCapabilityInfo {
  enabled: boolean;
  provider: "ionTerrain" | "none";
  eagerCount: number;
  message: string | null;
}

const EAGER_COUNT = parseInt(process.env.PREVIEW_EAGER_COUNT || "3", 10);

export function getPreviewCapabilities(): PreviewCapabilityInfo {
  const ionToken = process.env.NEXT_PUBLIC_CESIUM_ION_TOKEN;

  if (ionToken && ionToken.trim().length > 0) {
    return {
      enabled: true,
      provider: "ionTerrain",
      eagerCount: EAGER_COUNT,
      message: null,
    };
  }

  return {
    enabled: false,
    provider: "none",
    eagerCount: 0,
    message: "Configure NEXT_PUBLIC_CESIUM_ION_TOKEN to enable raw terrain previews.",
  };
}
