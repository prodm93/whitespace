import type { Metadata } from "next";
import { Cormorant_Garamond, Inter } from "next/font/google";
import "./globals.css";
import AppShell from "@/components/layout/AppShell";
import { CredentialsProvider } from "@/context/CredentialsContext";

const cormorant = Cormorant_Garamond({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  style: ["normal", "italic"],
  display: "swap",
  variable: "--font-cormorant",
});

const inter = Inter({
  subsets: ["latin"],
  weight: ["300", "400", "500"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "WhiteSpace",
  description: "Find your whitespace. Adversarial multi-model patent analysis and ideation.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${cormorant.variable} ${inter.variable}`} style={{ visibility: "hidden" }}>
      <body>
        <CredentialsProvider>
          <AppShell>{children}</AppShell>
        </CredentialsProvider>
      </body>
    </html>
  );
}
