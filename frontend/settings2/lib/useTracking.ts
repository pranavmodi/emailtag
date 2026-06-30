"use client";

import { useEffect, useRef, useCallback } from "react";
import { UsageApi, UsageEventCreate } from "./api";

// Generate a unique session ID
function generateSessionId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

// Get or create session ID from localStorage
function getSessionId(): string {
  if (typeof window === "undefined") return "";

  const STORAGE_KEY = "usage_session_id";
  const SESSION_EXPIRY_KEY = "usage_session_expiry";
  const SESSION_DURATION_MS = 30 * 60 * 1000; // 30 minutes

  const existingSession = localStorage.getItem(STORAGE_KEY);
  const expiryTime = localStorage.getItem(SESSION_EXPIRY_KEY);

  // Check if session exists and hasn't expired
  if (existingSession && expiryTime && Date.now() < parseInt(expiryTime, 10)) {
    // Extend session
    localStorage.setItem(SESSION_EXPIRY_KEY, String(Date.now() + SESSION_DURATION_MS));
    return existingSession;
  }

  // Create new session
  const newSession = generateSessionId();
  localStorage.setItem(STORAGE_KEY, newSession);
  localStorage.setItem(SESSION_EXPIRY_KEY, String(Date.now() + SESSION_DURATION_MS));
  return newSession;
}

// Track an event (fire and forget)
async function trackEvent(event: UsageEventCreate): Promise<void> {
  try {
    await UsageApi.track({
      ...event,
      session_id: event.session_id || getSessionId(),
    });
  } catch (error) {
    // Silently fail - don't interrupt user experience
    console.debug("Failed to track event:", error);
  }
}

/**
 * Hook for tracking user interactions on a page.
 *
 * @param pagePath - The current page path (e.g., "/", "/template-config")
 * @param pageName - Human-readable page name (e.g., "System Settings", "Templates")
 */
export function useTracking(pagePath: string, pageName: string) {
  const pageLoadTime = useRef<number>(Date.now());
  const hasTrackedPageView = useRef<boolean>(false);

  // Track page view on mount
  useEffect(() => {
    if (hasTrackedPageView.current) return;
    hasTrackedPageView.current = true;

    pageLoadTime.current = Date.now();

    trackEvent({
      event_type: "page_view",
      event_name: `view_${pageName.toLowerCase().replace(/\s+/g, "_")}`,
      page_path: pagePath,
      details: {
        page_name: pageName,
        timestamp: new Date().toISOString(),
      },
    });

    // Track page leave with duration
    return () => {
      const duration = Date.now() - pageLoadTime.current;
      trackEvent({
        event_type: "page_leave",
        event_name: `leave_${pageName.toLowerCase().replace(/\s+/g, "_")}`,
        page_path: pagePath,
        duration_ms: duration,
        details: {
          page_name: pageName,
          duration_seconds: Math.round(duration / 1000),
        },
      });
    };
  }, [pagePath, pageName]);

  // Track click/action
  const trackAction = useCallback(
    (actionName: string, component?: string, details?: Record<string, unknown>) => {
      trackEvent({
        event_type: "action",
        event_name: actionName,
        page_path: pagePath,
        component,
        details: {
          page_name: pageName,
          ...details,
        },
      });
    },
    [pagePath, pageName]
  );

  // Track button click
  const trackClick = useCallback(
    (buttonName: string, details?: Record<string, unknown>) => {
      trackEvent({
        event_type: "click",
        event_name: `click_${buttonName.toLowerCase().replace(/\s+/g, "_")}`,
        page_path: pagePath,
        component: buttonName,
        details: {
          page_name: pageName,
          ...details,
        },
      });
    },
    [pagePath, pageName]
  );

  // Track form submission
  const trackFormSubmit = useCallback(
    (formName: string, details?: Record<string, unknown>) => {
      trackEvent({
        event_type: "action",
        event_name: `submit_${formName.toLowerCase().replace(/\s+/g, "_")}`,
        page_path: pagePath,
        component: formName,
        details: {
          page_name: pageName,
          ...details,
        },
      });
    },
    [pagePath, pageName]
  );

  // Track toggle change
  const trackToggle = useCallback(
    (toggleName: string, newValue: boolean, details?: Record<string, unknown>) => {
      trackEvent({
        event_type: "action",
        event_name: `toggle_${toggleName.toLowerCase().replace(/\s+/g, "_")}`,
        page_path: pagePath,
        component: toggleName,
        details: {
          page_name: pageName,
          new_value: newValue,
          ...details,
        },
      });
    },
    [pagePath, pageName]
  );

  // Track search
  const trackSearch = useCallback(
    (searchTerm: string, resultsCount?: number) => {
      trackEvent({
        event_type: "action",
        event_name: "search",
        page_path: pagePath,
        details: {
          page_name: pageName,
          search_term: searchTerm,
          results_count: resultsCount,
        },
      });
    },
    [pagePath, pageName]
  );

  // Track error
  const trackError = useCallback(
    (errorMessage: string, errorContext?: string) => {
      trackEvent({
        event_type: "error",
        event_name: "error_occurred",
        page_path: pagePath,
        details: {
          page_name: pageName,
          error_message: errorMessage,
          error_context: errorContext,
        },
      });
    },
    [pagePath, pageName]
  );

  return {
    trackAction,
    trackClick,
    trackFormSubmit,
    trackToggle,
    trackSearch,
    trackError,
  };
}

export default useTracking;
