import { cn } from "@/lib/utils";

export type SegmentOption<T extends string> = {
  value: T;
  label: string;
  description?: string;
  activeClass?: string;
};

type SegmentedControlProps<T extends string> = {
  options: SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
  disabled?: boolean;
  className?: string;
};

// Color classes for each segment value
const SEGMENT_COLORS: Record<string, { active: string; text: string }> = {
  off: {
    active: "bg-slate-700 text-white shadow-md",
    text: "text-slate-500"
  },
  sandbox: {
    active: "bg-amber-500 text-white shadow-md shadow-amber-200",
    text: "text-slate-500"
  },
  production: {
    active: "bg-emerald-500 text-white shadow-md shadow-emerald-200",
    text: "text-slate-500"
  },
};

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  disabled = false,
  className,
}: SegmentedControlProps<T>) {
  return (
    <div
      className={cn(
        "inline-flex rounded-full bg-slate-100 p-1 gap-0.5",
        disabled && "opacity-50 pointer-events-none",
        className
      )}
    >
      {options.map((option) => {
        const isActive = option.value === value;
        const colors = SEGMENT_COLORS[option.value] || { active: "bg-white text-slate-900 shadow-sm", text: "text-slate-500" };

        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            disabled={disabled}
            className={cn(
              "px-4 py-1.5 text-sm font-medium rounded-full transition-all duration-200",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1",
              isActive
                ? colors.active
                : cn(colors.text, "hover:text-slate-700 hover:bg-white/50")
            )}
            title={option.description}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
