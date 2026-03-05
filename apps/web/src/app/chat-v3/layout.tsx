import { RuntimeProvider } from "@/components/chat-v3/runtime-provider";

export default function ChatV3Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <RuntimeProvider>{children}</RuntimeProvider>;
}
