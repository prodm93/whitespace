"use client";

import { ClerkProvider } from "@clerk/react";
import { useCredentials } from "@/context/CredentialsContext";
import AuthTokenBridge from "@/components/auth/AuthTokenBridge";

export default function ClerkRoot({ children }: { children: React.ReactNode }) {
  const { credentials } = useCredentials();
  const publishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

  if (credentials?.mode !== "saas" || !publishableKey) {
    return <>{children}</>;
  }

  return (
    <ClerkProvider publishableKey={publishableKey}>
      <AuthTokenBridge />
      {children}
    </ClerkProvider>
  );
}
