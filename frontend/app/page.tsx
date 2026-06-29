"use client";

import Hero from "@/components/layout/Hero";
import Onboarding from "@/components/onboarding/Onboarding";
import { useCredentials } from "@/context/CredentialsContext";

export default function Home() {
  const { isReady } = useCredentials();

  return (
    <>
      <Hero />
      {isReady ? null : <Onboarding />}
    </>
  );
}
