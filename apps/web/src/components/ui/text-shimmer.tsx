"use client"

import { cn } from "@/lib/utils"
import { createElement } from "react"

export type TextShimmerProps = {
  as?: React.ElementType
  duration?: number
  spread?: number
  children: React.ReactNode
  className?: string
  style?: React.CSSProperties
}

export function TextShimmer({
  as = "span",
  className,
  duration = 4,
  spread = 20,
  children,
}: TextShimmerProps) {
  const dynamicSpread = Math.min(Math.max(spread, 5), 45)

  return createElement(
    as,
    {
      className: cn(
        "bg-size-[200%_auto] bg-clip-text font-medium text-transparent",
        "animate-[shimmer_4s_infinite_linear]",
        className
      ),
      style: {
        backgroundImage: `linear-gradient(to right, var(--muted-foreground) ${50 - dynamicSpread}%, var(--foreground) 50%, var(--muted-foreground) ${50 + dynamicSpread}%)`,
        animationDuration: `${duration}s`,
      },
    },
    children
  )
}
