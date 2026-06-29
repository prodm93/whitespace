"use client";

import { useCallback, useRef, useState } from "react";
import type { AuraCreds, ByokCredentials } from "@/types";
import { parseAuraFile } from "./AuraFileParser";
import { validateCredentials } from "@/lib/api";

interface ByokFormProps {
  onConnect: (creds: ByokCredentials) => void;
  onBack: () => void;
}

export default function ByokForm({ onConnect, onBack }: ByokFormProps) {
  const [openrouterKey, setOpenrouterKey] = useState("");
  const [aura, setAura] = useState<AuraCreds | null>(null);
  const [auraFilename, setAuraFilename] = useState("");
  const [auraError, setAuraError] = useState("");
  const [exaKey, setExaKey] = useState("");
  const [firecrawlKey, setFirecrawlKey] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleAuraFile = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setAuraError("");
    try {
      const text = await file.text();
      const parsed = parseAuraFile(text);
      setAura(parsed);
      setAuraFilename(file.name);
    } catch (err) {
      setAuraError(err instanceof Error ? err.message : "Failed to parse file");
      setAura(null);
      setAuraFilename("");
    }
  }, []);

  const handleConnect = useCallback(async () => {
    setError("");
    const creds: ByokCredentials = {
      openrouterApiKey: openrouterKey,
      aura,
      exaApiKey: exaKey,
      firecrawlApiKey: firecrawlKey,
    };

    if (!creds.openrouterApiKey) {
      setError("OpenRouter API key is required.");
      return;
    }
    if (!creds.aura) {
      setError("Neo4j Aura credentials file is required.");
      return;
    }

    setValidating(true);
    try {
      const result = await validateCredentials(creds);
      if (result.valid) {
        onConnect(creds);
      } else {
        setError(result.error ?? "Credentials validation failed.");
      }
    } catch {
      setError("Could not reach the backend. Is it running?");
    } finally {
      setValidating(false);
    }
  }, [openrouterKey, aura, exaKey, firecrawlKey, onConnect]);

  return (
    <section className="byok-form">
      <button className="byok-form__back" onClick={onBack} type="button">
        &larr; Back
      </button>
      <h2 className="byok-form__heading">Connect your services</h2>

      <div className="byok-form__field">
        <label className="byok-form__label" htmlFor="openrouter-key">
          OpenRouter API Key
        </label>
        <input
          id="openrouter-key"
          className="byok-form__input"
          type="password"
          placeholder="sk-or-v1-..."
          value={openrouterKey}
          onChange={(e) => setOpenrouterKey(e.target.value)}
          autoComplete="off"
        />
      </div>

      <div className="byok-form__field">
        <label className="byok-form__label">
          Neo4j Aura Credentials
        </label>
        <div className="byok-form__file-zone">
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.env"
            onChange={handleAuraFile}
            className="byok-form__file-input"
          />
          <button
            className="byok-form__file-btn"
            type="button"
            onClick={() => fileInputRef.current?.click()}
          >
            {auraFilename || "Upload .txt file"}
          </button>
          {aura && (
            <span className="byok-form__file-ok">
              &#10003; {aura.neo4jUri}
            </span>
          )}
          {auraError && (
            <span className="byok-form__file-err">{auraError}</span>
          )}
        </div>
      </div>

      <button
        className="byok-form__advanced-toggle"
        onClick={() => setShowAdvanced(!showAdvanced)}
        type="button"
      >
        {showAdvanced ? "Hide" : "Show"} advanced search keys
        <span className={`byok-form__chevron ${showAdvanced ? "byok-form__chevron--open" : ""}`}>
          &#8250;
        </span>
      </button>

      {showAdvanced && (
        <div className="byok-form__advanced">
          <div className="byok-form__field">
            <label className="byok-form__label" htmlFor="exa-key">
              Exa API Key <span className="byok-form__optional">(optional)</span>
            </label>
            <input
              id="exa-key"
              className="byok-form__input"
              type="password"
              placeholder="exa-..."
              value={exaKey}
              onChange={(e) => setExaKey(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div className="byok-form__field">
            <label className="byok-form__label" htmlFor="firecrawl-key">
              Firecrawl API Key <span className="byok-form__optional">(optional)</span>
            </label>
            <input
              id="firecrawl-key"
              className="byok-form__input"
              type="password"
              placeholder="fc-..."
              value={firecrawlKey}
              onChange={(e) => setFirecrawlKey(e.target.value)}
              autoComplete="off"
            />
          </div>
          <p className="byok-form__hint">
            Without these, search falls back to DuckDuckGo (no API key needed).
          </p>
        </div>
      )}

      {error && <p className="byok-form__error">{error}</p>}

      <button
        className="byok-form__connect"
        onClick={handleConnect}
        disabled={validating}
        type="button"
      >
        {validating ? "Validating…" : "Connect"}
      </button>

      <style jsx>{`
        .byok-form {
          padding: 0 var(--margin) 96px;
          max-width: 520px;
          margin: 0 auto;
        }
        .byok-form__back {
          font-size: var(--text-caption);
          color: var(--text-secondary);
          margin-bottom: 24px;
          transition: color 0.2s var(--ease-out);
        }
        .byok-form__back:hover {
          color: var(--text-primary);
        }
        .byok-form__heading {
          font-family: "Cormorant Garamond", Georgia, serif;
          font-size: var(--text-h2);
          font-weight: 400;
          color: var(--text-primary);
          margin-bottom: 36px;
        }
        .byok-form__field {
          margin-bottom: 24px;
        }
        .byok-form__label {
          display: block;
          font-size: var(--text-caption);
          font-weight: 400;
          color: var(--text-secondary);
          margin-bottom: 8px;
          letter-spacing: 0.03em;
          text-transform: uppercase;
        }
        .byok-form__optional {
          text-transform: none;
          color: var(--text-muted);
        }
        .byok-form__input {
          width: 100%;
          padding: 12px 16px;
          font-family: "Inter", sans-serif;
          font-size: var(--text-body);
          font-weight: 300;
          color: var(--text-primary);
          background: rgba(18, 16, 42, 0.5);
          border: 1px solid var(--stroke-lavender);
          border-radius: var(--radius-md);
          outline: none;
          transition: border-color 0.2s var(--ease-out);
        }
        .byok-form__input::placeholder {
          color: var(--text-muted);
        }
        .byok-form__input:focus {
          border-color: var(--accent);
        }
        .byok-form__file-zone {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .byok-form__file-input {
          display: none;
        }
        .byok-form__file-btn {
          padding: 12px 16px;
          font-size: var(--text-body);
          font-weight: 300;
          color: var(--text-secondary);
          background: rgba(18, 16, 42, 0.5);
          border: 1px dashed var(--stroke-lavender);
          border-radius: var(--radius-md);
          text-align: left;
          transition: border-color 0.2s var(--ease-out), color 0.2s var(--ease-out);
        }
        .byok-form__file-btn:hover {
          border-color: var(--accent);
          color: var(--text-primary);
        }
        .byok-form__file-ok {
          font-size: var(--text-caption);
          color: #5a9a6a;
        }
        .byok-form__file-err {
          font-size: var(--text-caption);
          color: #c25a5a;
        }
        .byok-form__advanced-toggle {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: var(--text-caption);
          color: var(--text-secondary);
          margin-bottom: 16px;
          transition: color 0.2s var(--ease-out);
        }
        .byok-form__advanced-toggle:hover {
          color: var(--text-primary);
        }
        .byok-form__chevron {
          display: inline-block;
          transition: transform 0.2s var(--ease-out);
        }
        .byok-form__chevron--open {
          transform: rotate(90deg);
        }
        .byok-form__advanced {
          margin-bottom: 24px;
          padding: 20px;
          border: 1px solid var(--stroke-lavender);
          border-radius: var(--radius-md);
          background: rgba(18, 16, 42, 0.3);
        }
        .byok-form__advanced .byok-form__field:last-of-type {
          margin-bottom: 0;
        }
        .byok-form__hint {
          font-size: var(--text-caption);
          color: var(--text-muted);
          margin-top: 12px;
        }
        .byok-form__error {
          font-size: var(--text-caption);
          color: #c25a5a;
          margin-bottom: 16px;
        }
        .byok-form__connect {
          width: 100%;
          padding: 14px 0;
          font-family: "Inter", sans-serif;
          font-size: var(--text-body);
          font-weight: 400;
          color: var(--text-primary);
          background: var(--accent);
          border-radius: var(--radius-md);
          transition: opacity 0.2s var(--ease-out), box-shadow 0.2s var(--ease-out);
        }
        .byok-form__connect:hover:not(:disabled) {
          box-shadow: 0 0 24px var(--accent-glow);
        }
        .byok-form__connect:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
      `}</style>
    </section>
  );
}
