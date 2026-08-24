"use client";

import { useId, useState } from "react";
import { Icon } from "@/components/ui/Icon";

type BaseProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  hint?: string;
  required?: boolean;
  autoComplete?: string;
  placeholder?: string;
};

function describedBy(error?: string, hint?: string, errorId?: string, hintId?: string) {
  return [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(" ") || undefined;
}

export function TextField({
  type = "text",
  label,
  value,
  onChange,
  error,
  hint,
  required,
  autoComplete,
  placeholder
}: BaseProps & { type?: "text" | "email" }) {
  const id = useId();
  return (
    <div className="hc-field">
      <label htmlFor={id}>
        {label}
        {required ? null : <span className="hc-field-hint"> (optional)</span>}
      </label>
      <input
        id={id}
        className="hc-input"
        type={type}
        value={value}
        required={required}
        autoComplete={autoComplete}
        placeholder={placeholder}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(error, hint, `${id}-error`, `${id}-hint`)}
        onChange={(event) => onChange(event.target.value)}
      />
      {hint && !error ? (
        <p className="hc-field-hint" id={`${id}-hint`}>
          {hint}
        </p>
      ) : null}
      {error ? (
        <p className="hc-field-error" id={`${id}-error`}>
          <Icon name="alert" size={14} />
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function PasswordField({ label, value, onChange, error, hint, required, autoComplete }: BaseProps) {
  const id = useId();
  const [visible, setVisible] = useState(false);

  return (
    <div className="hc-field">
      <label htmlFor={id}>{label}</label>
      <div className="hc-input-wrap">
        <input
          id={id}
          className="hc-input"
          type={visible ? "text" : "password"}
          value={value}
          required={required}
          autoComplete={autoComplete}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(error, hint, `${id}-error`, `${id}-hint`)}
          onChange={(event) => onChange(event.target.value)}
        />
        <button
          type="button"
          className="hc-input-btn"
          onClick={() => setVisible((current) => !current)}
          aria-label={visible ? "Hide password" : "Show password"}
        >
          <Icon name={visible ? "eyeOff" : "eye"} size={18} />
        </button>
      </div>
      {hint && !error ? (
        <p className="hc-field-hint" id={`${id}-hint`}>
          {hint}
        </p>
      ) : null}
      {error ? (
        <p className="hc-field-error" id={`${id}-error`}>
          <Icon name="alert" size={14} />
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function FormAlert({ tone = "error", children }: { tone?: "error" | "info"; children: React.ReactNode }) {
  return (
    <div className={`hc-alert hc-alert-${tone}`} role={tone === "error" ? "alert" : "status"}>
      <Icon name={tone === "error" ? "alert" : "info"} size={17} />
      <span>{children}</span>
    </div>
  );
}
