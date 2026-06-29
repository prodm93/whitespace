"use client";

import { useEffect } from "react";
import {
  ClerkProvider,
  SignInButton,
  useAuth,
} from "@clerk/nextjs";
import { useCredentials } from "@/context/CredentialsContext";

function SaasInner({ onBack }: { onBack: () => void }) {
  const { isSignedIn, isLoaded } = useAuth();
  const { markSaasAuthenticated } = useCredentials();

  useEffect(() => {
    if (isSignedIn) {
      markSaasAuthenticated();
    }
  }, [isSignedIn, markSaasAuthenticated]);

  return (
    <section className="saas-gate">
      <button className="saas-gate__back" onClick={onBack} type="button">
        &larr; Back
      </button>

      {!isLoaded && (
        <p className="saas-gate__status">Loading&hellip;</p>
      )}

      {isLoaded && !isSignedIn && (
        <>
          <h2 className="saas-gate__heading">Sign in to continue</h2>
          <p className="saas-gate__desc">
            Create an account or sign in to use hosted infrastructure.
          </p>
          <SignInButton mode="modal">
            <button className="saas-gate__btn" type="button">
              Sign in
            </button>
          </SignInButton>
        </>
      )}

      {isLoaded && isSignedIn && (
        <p className="saas-gate__status">Authenticated. Redirecting&hellip;</p>
      )}

      <style jsx>{`
        .saas-gate {
          padding: 0 var(--margin) 96px;
          max-width: 520px;
          margin: 0 auto;
          text-align: center;
        }
        .saas-gate__back {
          display: block;
          font-size: var(--text-caption);
          color: var(--text-secondary);
          margin-bottom: 24px;
          text-align: left;
          transition: color 0.2s var(--ease-out);
        }
        .saas-gate__back:hover {
          color: var(--text-primary);
        }
        .saas-gate__heading {
          font-family: "Cormorant Garamond", Georgia, serif;
          font-size: var(--text-h2);
          font-weight: 400;
          color: var(--text-primary);
          margin-bottom: 12px;
        }
        .saas-gate__desc {
          font-size: var(--text-body);
          color: var(--text-secondary);
          margin-bottom: 32px;
        }
        .saas-gate__btn {
          padding: 14px 48px;
          font-family: "Inter", sans-serif;
          font-size: var(--text-body);
          font-weight: 400;
          color: var(--text-primary);
          background: var(--accent);
          border-radius: var(--radius-md);
          transition: opacity 0.2s var(--ease-out), box-shadow 0.2s var(--ease-out);
        }
        .saas-gate__btn:hover {
          box-shadow: 0 0 24px var(--accent-glow);
        }
        .saas-gate__status {
          font-size: var(--text-body);
          color: var(--text-secondary);
        }
      `}</style>
    </section>
  );
}

interface SaasGateProps {
  onBack: () => void;
}

export default function SaasGate({ onBack }: SaasGateProps) {
  const publishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;

  if (!publishableKey) {
    return (
      <section className="saas-gate-unavailable">
        <button className="saas-gate-unavailable__back" onClick={onBack} type="button">
          &larr; Back
        </button>
        <p className="saas-gate-unavailable__msg">
          Hosted mode is not available in this environment. Clerk keys are not configured.
        </p>

        <style jsx>{`
          .saas-gate-unavailable {
            padding: 0 var(--margin) 96px;
            max-width: 520px;
            margin: 0 auto;
          }
          .saas-gate-unavailable__back {
            display: block;
            font-size: var(--text-caption);
            color: var(--text-secondary);
            margin-bottom: 24px;
            transition: color 0.2s var(--ease-out);
          }
          .saas-gate-unavailable__back:hover {
            color: var(--text-primary);
          }
          .saas-gate-unavailable__msg {
            font-size: var(--text-body);
            color: var(--text-secondary);
          }
        `}</style>
      </section>
    );
  }

  return (
    <ClerkProvider publishableKey={publishableKey}>
      <SaasInner onBack={onBack} />
    </ClerkProvider>
  );
}
