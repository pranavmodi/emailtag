"use client";

import type { ComponentPropsWithoutRef } from "react";
import * as SwitchPrimitives from "@radix-ui/react-switch";
import { cn } from "@/lib/utils";

const sizeVariants = {
  base: {
    track: "h-6 w-11",
    thumb: "h-5 w-5",
    translate: "data-[state=checked]:translate-x-[calc(100%-1.25rem)]",
  },
  lg: {
    track: "h-12 w-24",
    thumb: "h-10 w-10",
    translate: "data-[state=checked]:translate-x-[3.5rem]",
  },
} as const;

export interface SwitchProps
  extends ComponentPropsWithoutRef<typeof SwitchPrimitives.Root> {
  label?: string;
  size?: keyof typeof sizeVariants;
}

export function Switch({ className, label, size = "base", ...rest }: SwitchProps) {
  const variant = sizeVariants[size];

  return (
    <SwitchPrimitives.Root
      className={cn(
        "peer inline-flex shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand.indigo focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-brand.indigo data-[state=unchecked]:bg-slate-300",
        variant.track,
        className
      )}
      {...rest}
    >
      <SwitchPrimitives.Thumb
        className={cn(
          "pointer-events-none rounded-full bg-white shadow-lg ring-0 transition-transform data-[state=unchecked]:translate-x-0",
          variant.translate,
          variant.thumb
        )}
      />
    </SwitchPrimitives.Root>
  );
}
