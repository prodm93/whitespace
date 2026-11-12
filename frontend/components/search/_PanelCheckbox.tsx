interface PanelCheckboxProps {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}

export default function PanelCheckbox({ checked, onChange, label }: PanelCheckboxProps) {
  return (
    <label className="panel-checkbox">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="panel-checkbox__input"
      />
      <span className="panel-checkbox__mark" />
      <span className="panel-checkbox__text">{label}</span>

      <style jsx>{`
        .panel-checkbox {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-top: var(--gutter);
          cursor: pointer;
          width: fit-content;
        }
        .panel-checkbox__input {
          position: absolute;
          opacity: 0;
          width: 0;
          height: 0;
        }
        .panel-checkbox__mark {
          display: block;
          flex-shrink: 0;
          width: 16px;
          height: 16px;
          border: 1.5px solid var(--stroke-lavender);
          border-radius: var(--radius-sm);
          background: transparent;
          transition: border-color 0.2s var(--ease-out),
            background 0.2s var(--ease-out);
        }
        .panel-checkbox__input:checked + .panel-checkbox__mark {
          border-color: var(--accent);
          background: var(--accent);
        }
        .panel-checkbox__input:checked + .panel-checkbox__mark::after {
          content: "";
          display: block;
          width: 4px;
          height: 8px;
          margin: 1px auto 0;
          border: solid var(--text-primary);
          border-width: 0 1.5px 1.5px 0;
          transform: rotate(45deg);
        }
        .panel-checkbox__input:focus-visible + .panel-checkbox__mark {
          outline: 2px solid var(--accent);
          outline-offset: 2px;
        }
        .panel-checkbox__text {
          font-size: var(--text-caption);
          color: var(--text-secondary);
        }
      `}</style>
    </label>
  );
}
