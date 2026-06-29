"use client";

import { useCallback, useRef, useState } from "react";
import type { UploadedFile } from "@/types";

const ACCEPTED = ".pdf,.docx,.txt,.csv,.xlsx";

interface DropZoneProps {
  label: string;
  description: string;
  files: UploadedFile[];
  onAdd: (files: File[]) => void;
  onRemove: (id: string) => void;
}

let idCounter = 0;
function nextId(): string {
  return `file-${++idCounter}-${Date.now()}`;
}

export default function DropZone({
  label,
  description,
  files,
  onAdd,
  onRemove,
}: DropZoneProps) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const dropped = Array.from(e.dataTransfer.files);
      if (dropped.length > 0) onAdd(dropped);
    },
    [onAdd],
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selected = e.target.files ? Array.from(e.target.files) : [];
      if (selected.length > 0) onAdd(selected);
      e.target.value = "";
    },
    [onAdd],
  );

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="drop-zone-wrapper">
      <h3 className="drop-zone__label">{label}</h3>
      <p className="drop-zone__desc">{description}</p>

      <div
        className={`drop-zone ${dragOver ? "drop-zone--active" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED}
          onChange={handleChange}
          className="drop-zone__input"
        />
        <span className="drop-zone__prompt">
          Drop files here or click to browse
        </span>
        <span className="drop-zone__formats">
          PDF, DOCX, TXT, CSV, XLSX
        </span>
      </div>

      {files.length > 0 && (
        <ul className="drop-zone__list">
          {files.map((f) => (
            <li key={f.id} className="drop-zone__item">
              <span className="drop-zone__item-name">{f.name}</span>
              <span className="drop-zone__item-size">{formatSize(f.size)}</span>
              <button
                className="drop-zone__item-remove"
                onClick={() => onRemove(f.id)}
                type="button"
                aria-label={`Remove ${f.name}`}
              >
                &times;
              </button>
            </li>
          ))}
        </ul>
      )}

      <style jsx>{`
        .drop-zone-wrapper {
          flex: 1;
          min-width: 0;
        }
        .drop-zone__label {
          font-family: "Cormorant Garamond", Georgia, serif;
          font-size: var(--text-h2);
          font-weight: 400;
          color: var(--text-primary);
          margin-bottom: 8px;
        }
        .drop-zone__desc {
          font-size: var(--text-caption);
          color: var(--text-secondary);
          margin-bottom: 16px;
          line-height: 1.5;
        }
        .drop-zone {
          position: relative;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 8px;
          padding: 40px 24px;
          border: 1.5px dashed var(--accent-dim);
          border-radius: var(--radius-lg);
          background: rgba(18, 16, 42, 0.3);
          cursor: pointer;
          transition: border-color 0.25s var(--ease-out),
            background 0.25s var(--ease-out);
        }
        .drop-zone:hover,
        .drop-zone--active {
          border-color: var(--accent);
          background: rgba(138, 69, 112, 0.08);
        }
        .drop-zone__input {
          display: none;
        }
        .drop-zone__prompt {
          font-size: var(--text-body);
          font-weight: 300;
          color: var(--text-secondary);
        }
        .drop-zone__formats {
          font-size: var(--text-caption);
          color: var(--text-muted);
        }
        .drop-zone__list {
          list-style: none;
          margin-top: 12px;
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .drop-zone__item {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 8px 12px;
          border-radius: var(--radius-sm);
          background: rgba(18, 16, 42, 0.4);
          border: 1px solid var(--stroke-lavender);
        }
        .drop-zone__item-name {
          flex: 1;
          font-size: var(--text-caption);
          color: var(--text-primary);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .drop-zone__item-size {
          font-size: var(--text-caption);
          color: var(--text-muted);
          flex-shrink: 0;
        }
        .drop-zone__item-remove {
          font-size: 18px;
          line-height: 1;
          color: var(--text-secondary);
          flex-shrink: 0;
          transition: color 0.15s var(--ease-out);
        }
        .drop-zone__item-remove:hover {
          color: #c25a5a;
        }
      `}</style>
    </div>
  );
}

export { nextId };
