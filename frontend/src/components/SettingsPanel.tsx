import { Shuffle } from "lucide-react";

interface Props {
  steps: number;
  cfg: number;
  seed: number;
  width: number;
  height: number;
  onStepsChange: (v: number) => void;
  onCfgChange: (v: number) => void;
  onSeedChange: (v: number) => void;
  onWidthChange: (v: number) => void;
  onHeightChange: (v: number) => void;
}

const DIMENSIONS = [512, 768, 1024, 1280];

function SliderRow({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <label className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
          {label}
        </label>
        <span className="text-xs font-mono text-zinc-300">{value}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-violet-500"
      />
    </div>
  );
}

function DimSelect({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="rounded-md px-3 py-2 text-sm text-zinc-100 bg-zinc-800 border border-zinc-700 focus:outline-none focus:ring-2 focus:ring-violet-500"
      >
        {DIMENSIONS.map((d) => (
          <option key={d} value={d}>
            {d}px
          </option>
        ))}
      </select>
    </div>
  );
}

export function SettingsPanel({
  steps,
  cfg,
  seed,
  width,
  height,
  onStepsChange,
  onCfgChange,
  onSeedChange,
  onWidthChange,
  onHeightChange,
}: Props) {
  const randomizeSeed = () => onSeedChange(Math.floor(Math.random() * 2 ** 32));

  return (
    <div className="flex flex-col gap-5">
      <SliderRow
        label="Steps"
        value={steps}
        min={1}
        max={150}
        step={1}
        onChange={onStepsChange}
      />
      <SliderRow
        label="CFG"
        value={cfg}
        min={1}
        max={20}
        step={0.5}
        onChange={onCfgChange}
      />

      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
          Seed
        </label>
        <div className="flex gap-2">
          <input
            type="number"
            value={seed}
            onChange={(e) => onSeedChange(Number(e.target.value))}
            className="flex-1 rounded-md px-3 py-2 text-sm text-zinc-100 bg-zinc-800 border border-zinc-700 focus:outline-none focus:ring-2 focus:ring-violet-500"
          />
          <button
            type="button"
            onClick={randomizeSeed}
            title="Randomize seed"
            className="p-2 rounded-md bg-zinc-800 border border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600 transition-colors"
          >
            <Shuffle size={16} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <DimSelect label="Width" value={width} onChange={onWidthChange} />
        <DimSelect label="Height" value={height} onChange={onHeightChange} />
      </div>
    </div>
  );
}
