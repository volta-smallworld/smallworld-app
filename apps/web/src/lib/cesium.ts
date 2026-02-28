import { Ion, OpenStreetMapImageryProvider } from "cesium";

let initialized = false;

export function initCesium() {
  if (initialized) return;
  (window as any).CESIUM_BASE_URL = "/cesium/";
  Ion.defaultAccessToken = "";
  initialized = true;
}

export function createOsmImageryProvider() {
  return new OpenStreetMapImageryProvider({
    url: "https://tile.openstreetmap.org/",
  });
}
