import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Chat | Smallworld",
  description: "Chat with Smallworld to explore terrain, viewpoints, and preview renders",
};

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return children;
}
