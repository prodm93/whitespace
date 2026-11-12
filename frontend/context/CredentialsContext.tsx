"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { ByokCredentials, Credentials, DeploymentMode } from "@/types";

interface CredentialsContextValue {
  credentials: Credentials | null;
  isReady: boolean;
  setMode: (mode: DeploymentMode) => void;
  setByokCredentials: (creds: ByokCredentials, waiting?: boolean) => void;
  keysWaiting: boolean;
  markSaasAuthenticated: () => void;
  reset: () => void;
}

const CredentialsContext = createContext<CredentialsContextValue | null>(null);

export function CredentialsProvider({ children }: { children: ReactNode }) {
  const [credentials, setCredentials] = useState<Credentials | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [keysWaiting, setKeysWaiting] = useState(false);

  const setMode = useCallback((mode: DeploymentMode) => {
    setCredentials({ mode, byok: null });
    setIsReady(false);
  }, []);

  const setByokCredentials = useCallback(
    (creds: ByokCredentials, waiting = false) => {
      setCredentials({ mode: "byok", byok: creds });
      setKeysWaiting(waiting);
      setIsReady(true);
    },
    [],
  );

  const markSaasAuthenticated = useCallback(() => {
    setCredentials((prev) => prev ? { ...prev } : { mode: "saas", byok: null });
    setIsReady(true);
  }, []);

  const reset = useCallback(() => {
    setCredentials(null);
    setIsReady(false);
  }, []);

  const value = useMemo(
    () => ({
      credentials,
      isReady,
      setMode,
      setByokCredentials,
      keysWaiting,
      markSaasAuthenticated,
      reset,
    }),
    [
      credentials,
      isReady,
      setMode,
      setByokCredentials,
      keysWaiting,
      markSaasAuthenticated,
      reset,
    ],
  );

  return (
    <CredentialsContext.Provider value={value}>
      {children}
    </CredentialsContext.Provider>
  );
}

export function useCredentials(): CredentialsContextValue {
  const ctx = useContext(CredentialsContext);
  if (!ctx) {
    throw new Error("useCredentials must be used within CredentialsProvider");
  }
  return ctx;
}
