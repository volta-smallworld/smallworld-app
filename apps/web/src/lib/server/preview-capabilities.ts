export type MapProvider = "google3d" | "ionTerrain" | "osm";

export interface PreviewCapabilityInfo {
  enabled: boolean;
  provider: "ionTerrain" | "google3d" | "none";
  eagerCount: number;
  message: string | null;
  /** All providers that can be activated given current env vars. */
  availableProviders: MapProvider[];
  /** Priority order used during resolution (highest first). */
  providerOrder: MapProvider[];
  /** The provider that was selected after resolution. */
  activeProvider: MapProvider;
}

const EAGER_COUNT = parseInt(process.env.PREVIEW_EAGER_COUNT || "3", 10);

/** Priority-ordered list used for resolution — highest fidelity first. */
const PROVIDER_ORDER: MapProvider[] = ["google3d", "ionTerrain", "osm"];

/**
 * Resolve which map providers are available from server-side env vars.
 */
function resolveProviders(): {
  activeProvider: MapProvider;
  availableProviders: MapProvider[];
} {
  const available: MapProvider[] = [];

  const googleKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
  if (googleKey && googleKey.trim().length > 0) available.push("google3d");

  const ionToken = process.env.NEXT_PUBLIC_CESIUM_ION_TOKEN;
  if (ionToken && ionToken.trim().length > 0) available.push("ionTerrain");

  available.push("osm"); // always available

  return {
    activeProvider: available[0],
    availableProviders: available,
  };
}

export function getPreviewCapabilities(): PreviewCapabilityInfo {
  const { activeProvider, availableProviders } = resolveProviders();

  if (activeProvider === "google3d") {
    return {
      enabled: true,
      provider: "google3d",
      eagerCount: EAGER_COUNT,
      message: null,
      availableProviders,
      providerOrder: PROVIDER_ORDER,
      activeProvider,
    };
  }

  if (activeProvider === "ionTerrain") {
    return {
      enabled: true,
      provider: "ionTerrain",
      eagerCount: EAGER_COUNT,
      message: null,
      availableProviders,
      providerOrder: PROVIDER_ORDER,
      activeProvider,
    };
  }

  return {
    enabled: false,
    provider: "none",
    eagerCount: 0,
    message:
      "Configure NEXT_PUBLIC_GOOGLE_MAPS_API_KEY (or NEXT_PUBLIC_CESIUM_ION_TOKEN) to enable previews.",
    availableProviders,
    providerOrder: PROVIDER_ORDER,
    activeProvider: "osm",
  };
}
