import { NextResponse } from "next/server";
import { getPreviewCapabilities } from "@/lib/server/preview-capabilities";

export const runtime = "nodejs";

export async function GET() {
  const capabilities = getPreviewCapabilities();
  return NextResponse.json(capabilities);
}
