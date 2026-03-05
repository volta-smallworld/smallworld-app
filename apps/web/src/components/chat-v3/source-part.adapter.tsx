"use client";

import { memo } from "react";
import { Source } from "@/components/ui/source";

type SourcePartProps = {
  sourceType: string;
  id: string;
  url: string;
  title?: string;
};

export const SourcePartAdapter = memo(function SourcePartAdapter({
  url,
  title,
}: SourcePartProps) {
  if (!url) {
    return null;
  }

  return <Source href={url} title={title} />;
});
