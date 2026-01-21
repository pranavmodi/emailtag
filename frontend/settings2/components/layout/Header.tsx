"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useRef, useEffect } from "react";
import { ChevronDown } from "lucide-react";

export interface MenuItem {
  href: string;
  label: string;
  description: string;
  icon: string;
  primary?: boolean;
}

export const MENU_ITEMS: MenuItem[] = [
  {
    href: "/",
    label: "System Settings",
    description: "Configure email processing behavior",
    icon: "⚙️",
    primary: true,
  },
  {
    href: "/template-config",
    label: "Templates",
    description: "Edit message templates",
    icon: "📝",
    primary: true,
  },
  {
    href: "/tag-statistics",
    label: "Tag Statistics",
    description: "Analyze tag retention and changes",
    icon: "📊",
    primary: true,
  },
  {
    href: "/archived-list",
    label: "Archived",
    description: "View archived conversations by day",
    icon: "📂",
    primary: false,
  },
  {
    href: "/ai-training",
    label: "AI Training",
    description: "View AI training conversations",
    icon: "🧠",
    primary: false,
  },
  {
    href: "/sandbox",
    label: "Sandbox",
    description: "Test autorespond outputs locally",
    icon: "🧪",
    primary: false,
  },
  {
    href: "/reprocess",
    label: "Reprocess",
    description: "Trigger conversation processing",
    icon: "🔄",
    primary: false,
  },
  {
    href: "/classification-traces",
    label: "Traces",
    description: "View classification traces",
    icon: "🔍",
    primary: false,
  },
  {
    href: "/conversation-replay",
    label: "Replay",
    description: "Replay conversations",
    icon: "▶️",
    primary: false,
  },
];

interface HeaderProps {
  user: string;
  currentPage?: {
    label: string;
    icon: string;
  };
}

export function Header({ user, currentPage }: HeaderProps) {
  const pathname = usePathname();
  const [moreMenuOpen, setMoreMenuOpen] = useState(false);
  const moreMenuRef = useRef<HTMLDivElement>(null);

  const primaryItems = MENU_ITEMS.filter((item) => item.primary);
  const secondaryItems = MENU_ITEMS.filter((item) => !item.primary);

  // Check if current page is in secondary items
  const isCurrentPageSecondary = secondaryItems.some(
    (item) => item.href === pathname
  );

  // Close menu when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        moreMenuRef.current &&
        !moreMenuRef.current.contains(event.target as Node)
      ) {
        setMoreMenuOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  const isActive = (href: string) => {
    if (href === "/") {
      return pathname === "/";
    }
    return pathname.startsWith(href);
  };

  return (
    <header className="sticky top-0 z-30 bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50 border-b border-slate-200/60 py-4">
      <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-6">
        {/* Primary menu items - card style */}
        {primaryItems.map((item) => {
          const active = isActive(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`rounded-2xl border p-4 transition hover:-translate-y-1 hover:shadow-lg ${
                active
                  ? "border-slate-900 bg-slate-900 text-white shadow-lg"
                  : "border-slate-200 bg-white text-slate-700"
              }`}
            >
              <div className="flex items-center gap-3 text-lg font-semibold">
                <span>{item.icon}</span>
                {item.label}
              </div>
              <p
                className={`mt-1 text-sm ${
                  active ? "text-white/80" : "text-slate-500"
                }`}
              >
                {item.description}
              </p>
            </Link>
          );
        })}

        {/* More dropdown - same card style */}
        <div className="relative" ref={moreMenuRef}>
          <button
            onClick={() => setMoreMenuOpen(!moreMenuOpen)}
            className={`rounded-2xl border p-4 transition hover:-translate-y-1 hover:shadow-lg ${
              isCurrentPageSecondary
                ? "border-slate-900 bg-slate-900 text-white shadow-lg"
                : "border-slate-200 bg-white text-slate-700"
            }`}
          >
            <div className="flex items-center gap-3 text-lg font-semibold">
              {isCurrentPageSecondary && currentPage ? (
                <>
                  <span>{currentPage.icon}</span>
                  {currentPage.label}
                </>
              ) : (
                <>
                  <span>📋</span>
                  More
                </>
              )}
              <ChevronDown
                className={`h-5 w-5 transition-transform ${
                  moreMenuOpen ? "rotate-180" : ""
                }`}
              />
            </div>
            <p
              className={`mt-1 text-sm ${
                isCurrentPageSecondary ? "text-white/80" : "text-slate-500"
              }`}
            >
              {isCurrentPageSecondary && currentPage
                ? secondaryItems.find((i) => i.href === pathname)?.description
                : "Additional tools"}
            </p>
          </button>

          {/* Dropdown menu */}
          {moreMenuOpen && (
            <div className="absolute left-0 top-full z-50 mt-2 w-64 rounded-xl border border-slate-200 bg-white py-2 shadow-xl">
              {secondaryItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMoreMenuOpen(false)}
                  className={`flex items-center gap-3 px-4 py-3 transition-colors ${
                    isActive(item.href)
                      ? "bg-slate-100 text-slate-900"
                      : "text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  <span className="text-lg">{item.icon}</span>
                  <div>
                    <div className="font-medium">{item.label}</div>
                    <div className="text-xs text-slate-500">
                      {item.description}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* User info - pushed to the right */}
        <div className="ml-auto flex items-center gap-3 text-sm text-slate-500">
          <span>
            Logged in as <strong className="text-slate-700">{user}</strong>
          </span>
        </div>
      </nav>
    </header>
  );
}

// Helper to get current page info from pathname
export function getCurrentPageInfo(pathname: string): MenuItem | undefined {
  return MENU_ITEMS.find((item) => {
    if (item.href === "/") {
      return pathname === "/";
    }
    return pathname.startsWith(item.href);
  });
}
