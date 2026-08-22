"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ExternalLink, FileSearch, Loader2, Maximize2, Minimize2 } from "lucide-react";

import { Header } from "@/components/layout/Header";
import { Badge } from "@/components/ui/badge";
import { ApiError, ModelEvaluationApi, SettingsApi } from "@/lib/api";
import { EvaluationRunner } from "../EvaluationRunner";

type Props = {
  caseType?: string;
  caseId?: string;
  conversationId?: string;
  emailId?: string;
  resultIndex?: string;
  objective?: string;
  filename?: string;
  contentType?: string;
  frontUrl?: string;
};

export function CaseDetailClient(props: Props) {
  const [user, setUser] = useState("Admin");
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [documentReviewMode, setDocumentReviewMode] = useState(false);

  useEffect(() => {
    SettingsApi.getAuthStatus()
      .then((auth) => {
        if (!auth.authenticated) {
          window.location.href = "/login";
          return;
        }
        setUser(auth.username || "Admin");
      })
      .catch((error) => {
        if (error instanceof ApiError && error.status === 401) window.location.href = "/login";
      })
      .finally(() => setCheckingAuth(false));
  }, []);

  useEffect(() => {
    if (!documentReviewMode) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDocumentReviewMode(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [documentReviewMode]);

  const caseType = props.caseType === "vision" ? "vision" : props.caseType === "classification" ? "classification" : null;
  const objective = props.objective === "rx" || props.objective === "lien" ? props.objective : null;
  const parsedIndex = props.resultIndex === undefined ? null : Number(props.resultIndex);
  const validVision = caseType === "vision" && props.emailId && objective && Number.isInteger(parsedIndex) && parsedIndex !== null && parsedIndex >= 0;
  const validClassification = caseType === "classification" && Boolean(props.conversationId || props.caseId);

  if (checkingAuth) {
    return <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500"><Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading test case…</div>;
  }

  if (!props.caseId || (!validVision && !validClassification)) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
        <div className="rounded-2xl border border-red-200 bg-white p-8 text-center">
          <p className="font-semibold text-red-700">This evaluation case link is incomplete.</p>
          <Link href="/settings/model-evaluation" className="mt-4 inline-flex items-center gap-2 text-sm font-medium text-indigo-700"><ArrowLeft className="h-4 w-4" /> Back to model evaluation</Link>
        </div>
      </main>
    );
  }

  const previewUrl = validVision
    ? ModelEvaluationApi.getVisionPreviewUrl(`/api/v1/model-evaluation/vision/${props.emailId}/${parsedIndex}/content`)
    : null;
  const title = props.filename || (caseType === "classification" ? `Email ${props.conversationId || props.caseId}` : "Document evaluation");

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50">
      <Header user={user} currentPage={{ label: "Evaluation Case", icon: "🔎" }} />
      <main className="mx-auto max-w-[1600px] px-6 py-7">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <Link href="/settings/model-evaluation" className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
            <ArrowLeft className="h-4 w-4" /> Back to model evaluation
          </Link>
          {props.frontUrl && (
            <a href={props.frontUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 text-sm font-medium text-indigo-700">Open in Front <ExternalLink className="h-4 w-4" /></a>
          )}
        </div>

        <section className="mb-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="flex items-center gap-2 text-xl font-bold text-slate-900"><FileSearch className="h-5 w-5 text-indigo-600" /> {title}</h1>
              <p className="mt-1 text-xs text-slate-500">Case {props.caseId}{props.conversationId ? ` · Front ${props.conversationId}` : ""}</p>
            </div>
            <Badge className="border-indigo-200 bg-indigo-50 text-indigo-700">{caseType === "vision" ? `${objective?.toUpperCase()} document` : "Email classification"}</Badge>
          </div>
        </section>

        <div className={validVision ? documentReviewMode
          ? "fixed inset-0 z-[70] grid grid-cols-1 grid-rows-[auto_minmax(0,1fr)_minmax(0,1fr)] gap-3 overflow-hidden bg-slate-100 p-3 lg:grid-cols-[minmax(560px,1.15fr)_minmax(520px,0.85fr)] lg:grid-rows-[auto_minmax(0,1fr)]"
          : "grid gap-5 xl:grid-cols-[minmax(560px,1fr)_minmax(560px,1fr)]"
          : ""}>
          {validVision && documentReviewMode && (
            <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-2 shadow-sm lg:col-span-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-slate-900">Ground-truth review · {title}</p>
                <p className="text-[10px] text-slate-500">Use the PDF controls to zoom, search, and move between pages. Press Esc to exit.</p>
              </div>
              <button type="button" onClick={() => setDocumentReviewMode(false)} className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50">
                <Minimize2 className="h-4 w-4" /> Exit full-screen review
              </button>
            </div>
          )}
          {validVision && previewUrl && (
            <aside className={`min-h-0 rounded-2xl border border-slate-200 bg-slate-100 p-3 shadow-sm ${documentReviewMode ? "overflow-hidden" : ""}`}>
              <div className={documentReviewMode ? "flex h-full min-h-0 flex-col" : "xl:sticky xl:top-3"}>
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Source document</p>
                  <div className="flex flex-wrap items-center gap-2">
                    {!documentReviewMode && (
                      <button type="button" onClick={() => setDocumentReviewMode(true)} className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-[10px] font-medium text-indigo-700 hover:bg-indigo-50">
                        <Maximize2 className="h-3.5 w-3.5" /> Full-screen review
                      </button>
                    )}
                    <a href={previewUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-[10px] font-medium text-indigo-700 hover:bg-indigo-50">
                      <ExternalLink className="h-3.5 w-3.5" /> Open full size
                    </a>
                    <button type="button" onClick={() => document.getElementById("ground-truth-editor")?.scrollIntoView({ behavior: "smooth", block: "start" })} className="rounded-md border border-indigo-200 bg-indigo-50 px-2.5 py-1.5 text-[10px] font-medium text-indigo-700 hover:bg-indigo-100">
                      Review fields
                    </button>
                  </div>
                </div>
                <iframe title={title} src={previewUrl} className={documentReviewMode ? "min-h-0 flex-1 w-full rounded bg-white" : "h-[calc(100vh-190px)] min-h-[720px] w-full rounded bg-white"} />
              </div>
            </aside>
          )}
          <section className={`min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm ${documentReviewMode ? "min-h-0 overflow-y-auto" : ""}`}>
            {validVision ? (
              <EvaluationRunner
                caseType="vision"
                caseId={props.caseId}
                target={{ email_id: props.emailId, result_index: parsedIndex as number, objective: objective as "rx" | "lien" }}
              />
            ) : (
              <EvaluationRunner
                caseType="classification"
                caseId={props.caseId}
                target={{ conversation_id: props.conversationId || props.caseId }}
              />
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
