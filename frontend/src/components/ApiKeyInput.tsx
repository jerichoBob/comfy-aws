import { Settings } from "lucide-react";
import { useRef, useState } from "react";
import { getApiKey, setApiKey } from "../hooks/useApi";

export function ApiKeyInput() {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(getApiKey);
  const ref = useRef<HTMLDivElement>(null);

  const handleBlur = () => {
    setApiKey(value);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        title="API Key settings"
        className="p-1.5 rounded text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
      >
        <Settings size={16} />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-72 rounded-lg border border-zinc-700 bg-zinc-800 p-4 shadow-xl z-50">
          <label className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
            API Key
          </label>
          <input
            type="password"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onBlur={handleBlur}
            placeholder="Leave empty to disable auth"
            className="mt-2 w-full rounded-md px-3 py-2 text-sm text-zinc-100 bg-zinc-900 border border-zinc-700 focus:outline-none focus:ring-2 focus:ring-violet-500"
          />
          <p className="mt-2 text-xs text-zinc-600">
            Stored in localStorage. Sent as X-API-Key header.
          </p>
        </div>
      )}
    </div>
  );
}
