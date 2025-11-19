import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost";
};

const variantClasses: Record<NonNullable<ButtonProps["variant"]>, string> = {
  primary:
    "bg-slate-900 text-white hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand.indigo focus-visible:ring-offset-2",
  ghost:
    "bg-transparent text-slate-600 hover:text-slate-900 border border-transparent hover:border-slate-200",
};

export function Button({ className, variant = "primary", ...props }: ButtonProps) {
  const resolvedVariant = variantClasses[variant];

  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition",
        resolvedVariant,
        className
      )}
      {...props}
    />
  );
}
