"use client";

import { useState } from "react";
import type { DeploymentMode, ByokCredentials } from "@/types";
import { useCredentials } from "@/context/CredentialsContext";
import ModeToggle from "./ModeToggle";
import ByokForm from "@/components/credentials/ByokForm";
import SaasGate from "@/components/auth/SaasGate";

export default function Onboarding() {
  const [selectedMode, setSelectedMode] = useState<DeploymentMode | null>(null);
  const { setMode, setByokCredentials } = useCredentials();

  const handleModeSelect = (mode: DeploymentMode) => {
    setSelectedMode(mode);
    setMode(mode);
  };

  const handleByokConnect = (creds: ByokCredentials) => {
    setByokCredentials(creds);
  };

  const handleBack = () => {
    setSelectedMode(null);
  };

  if (!selectedMode) {
    return <ModeToggle onSelect={handleModeSelect} />;
  }

  if (selectedMode === "byok") {
    return <ByokForm onConnect={handleByokConnect} onBack={handleBack} />;
  }

  return <SaasGate onBack={handleBack} />;
}
