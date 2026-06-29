import type { Metadata } from "next";
import "./globals.css";
import AppShell from "@/components/layout/AppShell";
import { CredentialsProvider } from "@/context/CredentialsContext";

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
    <html lang="en">
      <body>
        <CredentialsProvider>
          <AppShell>{children}</AppShell>
        </CredentialsProvider>
      </body>
    </html>
  );
}
