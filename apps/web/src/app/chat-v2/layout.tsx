import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Chat — SmallWorld",
  description: "AI-powered terrain chat",
};

export default function ChatV2Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
