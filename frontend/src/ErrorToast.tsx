import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { ApiError } from "./api";

interface Toast {
  message: string;
  type: string;
  detail: string | null;
  correlationId: string | null;
}

interface ErrorContextValue {
  /** Surface any thrown error as a global toast (never fails silently). */
  report: (err: unknown) => void;
}

const ErrorContext = createContext<ErrorContextValue | null>(null);

export function useErrorReporter(): ErrorContextValue {
  const ctx = useContext(ErrorContext);
  if (!ctx) throw new Error("useErrorReporter must be used within <ErrorProvider>");
  return ctx;
}

export function ErrorProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<Toast | null>(null);

  const report = useCallback((err: unknown) => {
    if (err instanceof ApiError) {
      setToast({
        message: err.message,
        type: err.type,
        detail: err.detail,
        correlationId: err.correlationId,
      });
    } else {
      setToast({
        message: err instanceof Error ? err.message : String(err),
        type: "unexpected",
        detail: null,
        correlationId: null,
      });
    }
  }, []);

  const value = useMemo(() => ({ report }), [report]);

  return (
    <ErrorContext.Provider value={value}>
      {children}
      {toast && (
        <div className="toast" role="alert">
          <div className="toast-head">
            <strong>{toast.type}</strong>
            <button className="toast-close" onClick={() => setToast(null)} aria-label="Dismiss">
              ×
            </button>
          </div>
          <div className="toast-msg">{toast.message}</div>
          {toast.detail && <pre className="toast-detail">{toast.detail}</pre>}
          {toast.correlationId && (
            <div className="toast-cid">correlation id: {toast.correlationId}</div>
          )}
        </div>
      )}
    </ErrorContext.Provider>
  );
}
