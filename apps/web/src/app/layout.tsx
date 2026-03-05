import type { Metadata } from "next";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { Manrope } from "next/font/google";
import "./globals.css";

const manrope = Manrope({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-manrope",
});

export const metadata: Metadata = {
  title: "Smallworld",
  description: "Terrain analysis platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`dark ${manrope.variable}`}>
      <body><NuqsAdapter>{children}</NuqsAdapter></body>
    </html>
  );
}
