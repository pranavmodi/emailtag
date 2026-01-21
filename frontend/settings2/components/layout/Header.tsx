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
    <header className="sticky top-0 z-30 backdrop-blur-md bg-white/70 border-b border-slate-200/60">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
        <nav className="flex items-center gap-1 text-sm font-medium">
          {/* Primary menu items */}
          {primaryItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`rounded-lg px-3 py-1.5 transition-colors ${
                isActive(item.href)
                  ? "bg-indigo-50 text-indigo-700 font-semibold"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }`}
            >
              <span className="mr-1">{item.icon}</span>
              {item.label}
            </Link>
          ))}

          {/* More dropdown */}
          <div className="relative" ref={moreMenuRef}>
            <button
              onClick={() => setMoreMenuOpen(!moreMenuOpen)}
              className={`flex items-center gap-1 rounded-lg px-3 py-1.5 transition-colors ${
                isCurrentPageSecondary
                  ? "bg-indigo-50 text-indigo-700 font-semibold"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }`}
            >
              {isCurrentPageSecondary && currentPage ? (
                <>
                  <span className="mr-1">{currentPage.icon}</span>
                  {currentPage.label}
                </>
              ) : (
                "More"
              )}
              <ChevronDown
                className={`h-4 w-4 transition-transform ${
                  moreMenuOpen ? "rotate-180" : ""
                }`}
              />
            </button>

            {/* Dropdown menu */}
            {moreMenuOpen && (
              <div className="absolute left-0 top-full mt-1 w-56 rounded-lg border border-slate-200 bg-white py-1 shadow-lg">
                {secondaryItems.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setMoreMenuOpen(false)}
                    className={`flex items-center gap-2 px-4 py-2 text-sm transition-colors ${
                      isActive(item.href)
                        ? "bg-indigo-50 text-indigo-700 font-medium"
                        : "text-slate-700 hover:bg-slate-50"
                    }`}
                  >
                    <span>{item.icon}</span>
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
        </nav>

        <div className="flex items-center gap-3 text-sm text-slate-500">
          <span>
            Logged in as <strong className="text-slate-700">{user}</strong>
          </span>
        </div>
      </div>
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
