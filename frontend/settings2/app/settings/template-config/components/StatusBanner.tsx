/**
 * StatusBanner component - displays success, error, or info messages
 */

export type StatusMessage = { type: "success" | "error" | "info"; message: string };

interface StatusBannerProps {
  status: StatusMessage;
}

export function StatusBanner({ status }: StatusBannerProps) {
  const styles: Record<StatusMessage["type"], string> = {
    success: "border-emerald-200 bg-emerald-50 text-emerald-700",
    error: "border-rose-200 bg-rose-50 text-rose-600",
    info: "border-slate-200 bg-slate-50 text-slate-700",
  };

  return (
    <div className={`rounded-2xl border px-4 py-3 text-sm ${styles[status.type]}`}>
      {status.message}
    </div>
  );
}
