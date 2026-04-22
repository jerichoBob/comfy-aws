import { useState } from "react";
import { Clock, Download, Hash, Box } from "lucide-react";
import type { Job } from "../hooks/useJob";
import { Lightbox, type LightboxMeta } from "./Lightbox";

interface Props {
  job: Job;
  onCopyToSession?: (meta: LightboxMeta) => void;
}

export function ResultPanel({ job, onCopyToSession }: Props) {
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const imageUrl = job.output_urls[0];
  const checkpoint = String(job.params.checkpoint ?? "—");
  const seed = String(job.params.seed ?? "—");

  const meta: LightboxMeta = {
    ...(job.params as LightboxMeta),
    duration_seconds: job.duration_seconds ?? undefined,
  };

  return (
    <div className="flex flex-col gap-4">
      {imageUrl && (
        <button
          type="button"
          className="rounded-lg overflow-hidden border border-zinc-700 bg-zinc-800 cursor-pointer p-0 block w-full"
          onClick={() => setLightboxOpen(true)}
        >
          <img
            src={imageUrl}
            alt="Generated output"
            className="w-full object-contain max-h-[60vh]"
          />
        </button>
      )}

      <div className="flex flex-wrap gap-4 text-sm text-zinc-400">
        {job.duration_seconds != null && (
          <span className="flex items-center gap-1">
            <Clock size={14} className="text-zinc-500" />
            {job.duration_seconds}s
          </span>
        )}
        <span className="flex items-center gap-1">
          <Hash size={14} className="text-zinc-500" />
          {seed}
        </span>
        <span className="flex items-center gap-1 truncate max-w-xs">
          <Box size={14} className="text-zinc-500" />
          <span className="truncate">{checkpoint}</span>
        </span>
      </div>

      {imageUrl && (
        <a
          href={imageUrl}
          download
          className="inline-flex items-center gap-2 text-sm text-violet-400 hover:text-violet-300 transition-colors"
        >
          <Download size={14} />
          Download image
        </a>
      )}

      {lightboxOpen && imageUrl && (
        <Lightbox
          url={imageUrl}
          meta={meta}
          onClose={() => setLightboxOpen(false)}
          onCopyToSession={onCopyToSession}
        />
      )}
    </div>
  );
}
