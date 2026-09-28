import type { ReactNode } from 'react';

export function Field({
  label,
  htmlFor,
  hint,
  error,
  children,
  testId,
}: {
  label: string;
  htmlFor?: string;
  hint?: ReactNode;
  error?: string | null;
  children: ReactNode;
  testId?: string;
}) {
  return (
    <div className="bb-field" data-testid={testId}>
      <label className="bb-field__label" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
      {error ? (
        <p className="bb-field__error" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="bb-field__hint">{hint}</p>
      ) : null}
    </div>
  );
}
