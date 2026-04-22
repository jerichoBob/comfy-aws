import clsx from "clsx";
import { Image, Trash2, X, RotateCcw } from "lucide-react";
import type { HistoryEntry } from "../hooks/useJobHistory";
import type { LightboxMeta } from "./Lightbox";

interface Props {
  history: HistoryEntry[];
  onClear: () => void;
  onRemove?: (id: string) => void;
  onRetry?: (params: Record<string, unknown>) => void;
  onImageClick?: (url: string, meta: LightboxMeta) => void;
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

const STATUS_STYLES: Record<string, string> = {
  COMPLETED: "bg-emerald-900/50 text-emerald-400",
  RUNNING: "bg-amber-900/50 text-amber-400",
  FAILED: "bg-red-900/50 text-red-400",
  PENDING: "bg-zinc-800 text-zinc-400",
  CANCELLED: "bg-zinc-800 text-zinc-500",
};

export function JobHistory({
  history,
  onClear,
  onRemove,
  onRetry,
  onImageClick,
}: Props) {
  if (history.length === 0) {
    return (
      <div className="p-4 text-xs text-zinc-600 text-center">No jobs yet</div>
    );
  }

  return (
    <div className="flex flex-col">
      <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800">
        <span className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
          History
        </span>
        <button
          type="button"
          onClick={onClear}
          title="Clear all history"
          className="p-1 text-zinc-600 hover:text-zinc-400 transition-colors"
        >
          <Trash2 size={12} />
        </button>
      </div>

      {history.map((entry) => (
        <div
          key={entry.id}
          className="flex items-center gap-3 px-4 py-3 border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors group"
        >
          <div className="w-12 h-12 rounded shrink-0 overflow-hidden bg-zinc-800 border border-zinc-700 flex items-center justify-center">
            {entry.thumbnail_url ? (
              <button
                type="button"
                className="w-full h-full p-0 cursor-pointer"
                onClick={() =>
                  onImageClick?.(entry.thumbnail_url!, {
                    ...(entry.params as LightboxMeta),
                    duration_seconds: entry.duration_seconds,
                  })
                }
                title="View full size"
              >
                <img
                  src={entry.thumbnail_url}
                  alt=""
                  className="w-full h-full object-cover"
                />
              </button>
            ) : (
              <Image size={16} className="text-zinc-600" />
            )}
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span
                className={clsx(
                  "text-xs px-1.5 py-0.5 rounded font-medium",
                  STATUS_STYLES[entry.status] ?? "bg-zinc-800 text-zinc-400",
                )}
              >
                {entry.status}
              </span>
              {entry.duration_seconds != null && (
                <span className="text-xs text-zinc-600">
                  {entry.duration_seconds}s
                </span>
              )}
            </div>
            <p className="text-xs text-zinc-600 mt-0.5 truncate">
              {String(entry.params.positive_prompt ?? entry.id)}
            </p>

            {entry.status === "FAILED" && onRetry && (
              <button
                type="button"
                onClick={() => onRetry(entry.params)}
                className="mt-1 flex items-center gap-1 text-xs text-violet-400 hover:text-violet-300 transition-colors"
              >
                <RotateCcw size={10} />
                Retry
              </button>
            )}
          </div>

          <div className="flex flex-col items-end gap-1 shrink-0">
            <span className="text-xs text-zinc-700">
              {relativeTime(entry.created_at)}
            </span>
            {onRemove && (
              <button
                type="button"
                onClick={() => onRemove(entry.id)}
                title="Remove from history"
                className="opacity-0 group-hover:opacity-100 p-0.5 text-zinc-600 hover:text-zinc-400 transition-all"
              >
                <X size={11} />
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
