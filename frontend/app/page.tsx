"use client";

import Hero from "@/components/layout/Hero";
import Onboarding from "@/components/onboarding/Onboarding";
import Workspace from "@/components/upload/Workspace";
import { useCredentials } from "@/context/CredentialsContext";

export default function Home() {
  const { isReady } = useCredentials();

  return (
    <>
      <Hero />
      {isReady ? <Workspace /> : <Onboarding />}
    </>
  );
}
