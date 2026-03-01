"use client";

import dynamic from "next/dynamic";
import { Suspense } from "react";

const RenderPreviewInner = dynamic(() => import("./render-preview-inner"), {
  ssr: false,
  loading: () => (
    <div
      style={{
        width: "100vw",
        height: "100vh",
        backgroundColor: "black",
      }}
    />
  ),
});

export default function RenderPreviewPage() {
  return (
    <Suspense
      fallback={
        <div
          style={{
            width: "100vw",
            height: "100vh",
            backgroundColor: "black",
          }}
        />
      }
    >
      <RenderPreviewInner />
    </Suspense>
  );
}
