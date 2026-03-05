"use client"

import { cn } from "@/lib/utils"
import { ExternalLinkIcon } from "lucide-react"

export type SourceProps = {
  href: string
  title?: string
  className?: string
  children?: React.ReactNode
}

function Source({ href, title, className, children }: SourceProps) {
  const domain = (() => {
    try {
      return new URL(href).hostname.replace("www.", "")
    } catch {
      return href
    }
  })()

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs transition-colors",
        "border-border/50 bg-muted/30 text-muted-foreground hover:bg-muted/50 hover:text-foreground",
        className,
      )}
    >
      <ExternalLinkIcon className="size-3 shrink-0" />
      <span className="truncate">{children ?? title ?? domain}</span>
    </a>
  )
}

export { Source }
