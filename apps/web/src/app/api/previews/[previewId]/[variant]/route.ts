import { NextResponse } from "next/server";

export const runtime = "nodejs";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8080";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ previewId: string; variant: string }> }
): Promise<NextResponse> {
  const { previewId, variant } = await params;

  if (!["raw", "enhanced"].includes(variant)) {
    return NextResponse.json({ error: "Unknown variant" }, { status: 404 });
  }

  try {
    const upstream = await fetch(
      `${API_BASE}/api/v1/previews/${previewId}/artifacts/${variant}`
    );

    if (!upstream.ok) {
      return NextResponse.json(
        { error: "Artifact not found" },
        { status: upstream.status }
      );
    }

    const buffer = await upstream.arrayBuffer();
    return new NextResponse(buffer, {
      status: 200,
      headers: {
        "Content-Type": "image/png",
        "Cache-Control": "public, max-age=3600",
      },
    });
  } catch {
    return NextResponse.json(
      { error: "Failed to fetch preview" },
      { status: 502 }
    );
  }
}
