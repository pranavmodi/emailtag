"use client";

import { useEffect } from "react";
import {
  X,
  Building2,
  Mail,
  Phone,
  Linkedin,
  Award,
  Briefcase,
  MapPin,
  Calendar,
  Users,
  ExternalLink,
  GraduationCap,
  Scale,
  FileText,
  Download,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { PifInfoResponse } from "@/lib/types";

interface ResearchModalProps {
  firm: PifInfoResponse;
  isOpen: boolean;
  onClose: () => void;
}

// Helper to check if a string is a valid LinkedIn URL
const isValidLinkedInUrl = (url: string | null | undefined): boolean => {
  if (!url) return false;
  const lower = url.toLowerCase();
  return lower.startsWith("https://linkedin.com") ||
         lower.startsWith("https://www.linkedin.com") ||
         lower.startsWith("http://linkedin.com") ||
         lower.startsWith("http://www.linkedin.com") ||
         lower.startsWith("linkedin.com") ||
         lower.startsWith("www.linkedin.com");
};

// Helper to escape CSV values
const escapeCSV = (value: string | null | undefined): string => {
  if (!value) return "";
  const str = String(value);
  if (str.includes(",") || str.includes('"') || str.includes("\n")) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
};

// Generate CSV content from firm research data
const generateResearchCSV = (firm: PifInfoResponse): string => {
  const lines: string[] = [];
  const research = firm.research_data;
  const leadership = firm.leadership || [];

  // Firm Overview Section
  lines.push("=== FIRM OVERVIEW ===");
  lines.push("Field,Value");
  lines.push(`Firm Name,${escapeCSV(firm.firm_name)}`);
  lines.push(`Website,${escapeCSV(firm.website)}`);
  lines.push(`Founded,${escapeCSV(research?.founded_year)}`);
  lines.push(`Firm Size,${escapeCSV(research?.firm_size)}`);
  lines.push(`Office Locations,${escapeCSV(research?.office_locations?.join("; "))}`);
  lines.push(`Practice Areas,${escapeCSV(research?.practice_areas?.join("; "))}`);
  lines.push("");

  // Leadership Section
  if (leadership.length > 0) {
    lines.push("=== LEADERSHIP TEAM ===");
    lines.push("Name,Title,Email,Phone,LinkedIn,Bio,Education,Bar Admissions,Skills");
    for (const leader of leadership) {
      lines.push([
        escapeCSV(leader.name),
        escapeCSV(leader.title),
        escapeCSV(leader.email),
        escapeCSV(leader.phone),
        escapeCSV(isValidLinkedInUrl(leader.linkedin) ? leader.linkedin : ""),
        escapeCSV(leader.bio),
        escapeCSV(leader.education?.join("; ")),
        escapeCSV(leader.bar_admissions?.join("; ")),
        escapeCSV(leader.skills?.join("; ")),
      ].join(","));
    }
    lines.push("");
  }

  // Awards & Recognition
  if (research?.awards_recognition && research.awards_recognition.length > 0) {
    lines.push("=== AWARDS & RECOGNITION ===");
    lines.push("Award");
    for (const award of research.awards_recognition) {
      lines.push(escapeCSV(award));
    }
    lines.push("");
  }

  // Notable Cases
  if (research?.notable_cases && research.notable_cases.length > 0) {
    lines.push("=== NOTABLE CASES ===");
    lines.push("Case");
    for (const caseItem of research.notable_cases) {
      lines.push(escapeCSV(caseItem));
    }
    lines.push("");
  }

  // Social Media
  if (research?.social_media && Object.keys(research.social_media).length > 0) {
    lines.push("=== SOCIAL MEDIA ===");
    lines.push("Platform,URL");
    for (const [platform, url] of Object.entries(research.social_media)) {
      lines.push(`${escapeCSV(platform)},${escapeCSV(url)}`);
    }
    lines.push("");
  }

  // Sources
  if (research?.sources && research.sources.length > 0) {
    lines.push("=== RESEARCH SOURCES ===");
    lines.push("URL");
    for (const source of research.sources) {
      lines.push(escapeCSV(source));
    }
  }

  return lines.join("\n");
};

// Download CSV file
const downloadCSV = (filename: string, content: string) => {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.setAttribute("href", url);
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

// Generate flat contacts CSV for Google Sheets (one row per contact)
const generateContactsCSV = (firm: PifInfoResponse): string => {
  const lines: string[] = [];
  const research = firm.research_data;
  const leadership = firm.leadership || [];
  const contacts = firm.contacts || [];

  // Header row
  lines.push([
    "Firm Name",
    "Website",
    "Firm Description",
    "Practice Areas",
    "Source",
    "Contact Name",
    "Position/Title",
    "Email",
    "Phone",
    "Extension",
    "LinkedIn",
    "Bio",
    "Education",
    "Bar Admissions",
  ].join(","));

  // Firm description from additional_info or constructed
  const firmDescription = [
    research?.founded_year ? `Founded: ${research.founded_year}` : "",
    research?.firm_size ? `Size: ${research.firm_size}` : "",
    research?.office_locations?.length ? `Locations: ${research.office_locations.join(", ")}` : "",
  ].filter(Boolean).join(". ");

  const practiceAreas = research?.practice_areas?.join(", ") || "";

  // Add leadership members (from research)
  for (const leader of leadership) {
    lines.push([
      escapeCSV(firm.firm_name),
      escapeCSV(firm.website),
      escapeCSV(firmDescription),
      escapeCSV(practiceAreas),
      "Research",
      escapeCSV(leader.name),
      escapeCSV(leader.title),
      escapeCSV(leader.email),
      escapeCSV(leader.phone),
      "",
      escapeCSV(isValidLinkedInUrl(leader.linkedin) ? leader.linkedin : ""),
      escapeCSV(leader.bio),
      escapeCSV(leader.education?.join("; ")),
      escapeCSV(leader.bar_admissions?.join("; ")),
    ].join(","));
  }

  // Add contacts (from email extraction)
  for (const contact of contacts) {
    lines.push([
      escapeCSV(firm.firm_name),
      escapeCSV(firm.website),
      escapeCSV(firmDescription),
      escapeCSV(practiceAreas),
      "Email",
      escapeCSV(contact.name),
      escapeCSV(contact.title),
      escapeCSV(contact.email),
      escapeCSV(contact.phone),
      escapeCSV(contact.extension),
      "",
      "",
      "",
      "",
    ].join(","));
  }

  // If no contacts at all, still output one row with firm info
  if (leadership.length === 0 && contacts.length === 0) {
    lines.push([
      escapeCSV(firm.firm_name),
      escapeCSV(firm.website),
      escapeCSV(firmDescription),
      escapeCSV(practiceAreas),
      "", "", "", "", "", "", "", "", "", "",
    ].join(","));
  }

  return lines.join("\n");
};

export function ResearchModal({ firm, isOpen, onClose }: ResearchModalProps) {
  // Close on escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    if (isOpen) {
      document.addEventListener("keydown", handleEscape);
      document.body.style.overflow = "hidden";
    }
    return () => {
      document.removeEventListener("keydown", handleEscape);
      document.body.style.overflow = "unset";
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const research = firm.research_data;
  const leadership = firm.leadership || [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative z-10 w-full max-w-5xl max-h-[90vh] overflow-hidden rounded-2xl bg-white shadow-2xl mx-4">
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-100">
              <Building2 className="h-5 w-5 text-indigo-600" />
            </div>
            <div>
              <h2 className="text-xl font-semibold text-slate-800">
                {firm.firm_name}
              </h2>
              <p className="text-sm text-slate-500">Research Results</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {(firm.research_data || (firm.leadership && firm.leadership.length > 0)) && (
              <>
                <Button
                  variant="ghost"
                  onClick={() => downloadCSV(
                    `${firm.firm_name.replace(/[^a-zA-Z0-9]/g, "_")}_contacts.csv`,
                    generateContactsCSV(firm)
                  )}
                  className="h-8 px-3 text-sm text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50"
                >
                  <Download className="h-4 w-4 mr-1.5" />
                  Contacts
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => downloadCSV(
                    `${firm.firm_name.replace(/[^a-zA-Z0-9]/g, "_")}_full_research.csv`,
                    generateResearchCSV(firm)
                  )}
                  className="h-8 px-3 text-sm text-slate-600 hover:text-slate-800"
                >
                  <Download className="h-4 w-4 mr-1.5" />
                  Full Report
                </Button>
              </>
            )}
            <Button
              variant="ghost"
              onClick={onClose}
              className="h-8 w-8 p-0 rounded-full"
            >
              <X className="h-5 w-5" />
            </Button>
          </div>
        </div>

        {/* Content */}
        <div className="overflow-y-auto max-h-[calc(90vh-80px)] p-6 space-y-8">
          {/* Firm Overview */}
          {research && (
            <section>
              <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-800 mb-4">
                <Building2 className="h-5 w-5 text-indigo-500" />
                Firm Overview
              </h3>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {research.founded_year && (
                  <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                    <div className="flex items-center gap-2 text-xs font-medium text-slate-500 mb-1">
                      <Calendar className="h-3.5 w-3.5" />
                      Founded
                    </div>
                    <div className="text-lg font-semibold text-slate-800">
                      {research.founded_year}
                    </div>
                  </div>
                )}
                {research.firm_size && (
                  <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                    <div className="flex items-center gap-2 text-xs font-medium text-slate-500 mb-1">
                      <Users className="h-3.5 w-3.5" />
                      Firm Size
                    </div>
                    <div className="text-lg font-semibold text-slate-800">
                      {research.firm_size}
                    </div>
                  </div>
                )}
                {firm.website && (
                  <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                    <div className="flex items-center gap-2 text-xs font-medium text-slate-500 mb-1">
                      <ExternalLink className="h-3.5 w-3.5" />
                      Website
                    </div>
                    <a
                      href={firm.website.startsWith("http") ? firm.website : `https://${firm.website}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm font-medium text-indigo-600 hover:underline truncate block"
                    >
                      {firm.website}
                    </a>
                  </div>
                )}
                {research.office_locations && research.office_locations.length > 0 && (
                  <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                    <div className="flex items-center gap-2 text-xs font-medium text-slate-500 mb-1">
                      <MapPin className="h-3.5 w-3.5" />
                      Locations
                    </div>
                    <div className="text-sm text-slate-700">
                      {research.office_locations.length} office{research.office_locations.length > 1 ? "s" : ""}
                    </div>
                  </div>
                )}
              </div>

              {/* Office Locations Detail */}
              {research.office_locations && research.office_locations.length > 0 && (
                <div className="mt-4">
                  <div className="text-sm font-medium text-slate-600 mb-2">Office Locations</div>
                  <div className="flex flex-wrap gap-2">
                    {research.office_locations.map((loc, i) => (
                      <Badge key={i} className="bg-slate-100 text-slate-700">
                        <MapPin className="h-3 w-3 mr-1" />
                        {loc}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </section>
          )}

          {/* Practice Areas */}
          {research?.practice_areas && research.practice_areas.length > 0 && (
            <section>
              <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-800 mb-4">
                <Briefcase className="h-5 w-5 text-indigo-500" />
                Practice Areas
              </h3>
              <div className="flex flex-wrap gap-2">
                {research.practice_areas.map((area, i) => (
                  <Badge key={i} className="bg-indigo-50 text-indigo-700 px-3 py-1">
                    {area}
                  </Badge>
                ))}
              </div>
            </section>
          )}

          {/* Leadership Team */}
          {leadership.length > 0 && (
            <section>
              <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-800 mb-4">
                <Users className="h-5 w-5 text-amber-500" />
                Leadership Team ({leadership.length})
              </h3>
              <div className="grid gap-4 sm:grid-cols-2">
                {leadership.map((leader, i) => (
                  <div
                    key={i}
                    className="rounded-xl border border-slate-200 bg-white p-4 hover:shadow-md transition-shadow"
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div>
                        <div className="font-semibold text-slate-800">{leader.name}</div>
                        {leader.title && (
                          <div className="text-sm text-slate-500">{leader.title}</div>
                        )}
                      </div>
                      {isValidLinkedInUrl(leader.linkedin) ? (
                        <a
                          href={leader.linkedin?.startsWith("http") ? leader.linkedin : `https://${leader.linkedin}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-50 text-blue-600 hover:bg-blue-100"
                          title="View LinkedIn Profile"
                        >
                          <Linkedin className="h-4 w-4" />
                        </a>
                      ) : (
                        <div
                          className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 text-slate-400"
                          title="LinkedIn not found"
                        >
                          <Linkedin className="h-4 w-4" />
                        </div>
                      )}
                    </div>

                    {/* Contact Info */}
                    <div className="space-y-1.5 mb-3">
                      {leader.email && (
                        <div className="flex items-center gap-2 text-sm text-slate-600">
                          <Mail className="h-3.5 w-3.5 text-slate-400" />
                          <a href={`mailto:${leader.email}`} className="hover:text-indigo-600">
                            {leader.email}
                          </a>
                        </div>
                      )}
                      {leader.phone && (
                        <div className="flex items-center gap-2 text-sm text-slate-600">
                          <Phone className="h-3.5 w-3.5 text-slate-400" />
                          {leader.phone}
                        </div>
                      )}
                    </div>

                    {/* Bio */}
                    {leader.bio && (
                      <p className="text-sm text-slate-600 mb-3 line-clamp-3">{leader.bio}</p>
                    )}

                    {/* Education */}
                    {leader.education && leader.education.length > 0 && (
                      <div className="mb-3">
                        <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500 mb-1">
                          <GraduationCap className="h-3.5 w-3.5" />
                          Education
                        </div>
                        <div className="text-sm text-slate-600">
                          {leader.education.slice(0, 2).map((edu, j) => (
                            <div key={j} className="truncate">{edu}</div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Bar Admissions */}
                    {leader.bar_admissions && leader.bar_admissions.length > 0 && (
                      <div className="mb-3">
                        <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500 mb-1">
                          <Scale className="h-3.5 w-3.5" />
                          Bar Admissions
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {leader.bar_admissions.map((bar, j) => (
                            <Badge key={j} className="bg-emerald-50 text-emerald-700 text-xs">
                              {bar}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Skills */}
                    {leader.skills && leader.skills.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {leader.skills.slice(0, 4).map((skill, j) => (
                          <Badge key={j} className="bg-slate-100 text-slate-600 text-xs">
                            {skill}
                          </Badge>
                        ))}
                        {leader.skills.length > 4 && (
                          <span className="text-xs text-slate-400">+{leader.skills.length - 4}</span>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Awards & Recognition */}
          {research?.awards_recognition && research.awards_recognition.length > 0 && (
            <section>
              <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-800 mb-4">
                <Award className="h-5 w-5 text-amber-500" />
                Awards & Recognition
              </h3>
              <div className="space-y-2">
                {research.awards_recognition.map((award, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm text-slate-600">
                    <Award className="h-4 w-4 text-amber-400 mt-0.5 flex-shrink-0" />
                    {award}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Notable Cases */}
          {research?.notable_cases && research.notable_cases.length > 0 && (
            <section>
              <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-800 mb-4">
                <FileText className="h-5 w-5 text-indigo-500" />
                Notable Cases
              </h3>
              <div className="space-y-2">
                {research.notable_cases.map((caseItem, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm text-slate-600">
                    <span className="text-indigo-400">•</span>
                    {caseItem}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Social Media */}
          {research?.social_media && Object.keys(research.social_media).length > 0 && (
            <section>
              <h3 className="flex items-center gap-2 text-lg font-semibold text-slate-800 mb-4">
                <ExternalLink className="h-5 w-5 text-indigo-500" />
                Social Media
              </h3>
              <div className="flex flex-wrap gap-2">
                {Object.entries(research.social_media).map(([platform, url]) => (
                  <a
                    key={platform}
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-2 rounded-lg bg-slate-100 px-4 py-2 text-sm text-slate-700 hover:bg-indigo-100 hover:text-indigo-700 transition-colors"
                  >
                    {platform}
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                ))}
              </div>
            </section>
          )}

          {/* Sources */}
          {research?.sources && research.sources.length > 0 && (
            <section>
              <h3 className="text-sm font-medium text-slate-500 mb-3">Research Sources</h3>
              <div className="flex flex-wrap gap-2">
                {research.sources.map((source, i) => (
                  <a
                    key={i}
                    href={source}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded bg-slate-50 px-2 py-1 text-xs text-slate-500 hover:bg-slate-100 hover:text-slate-700"
                  >
                    Source {i + 1}
                    <ExternalLink className="h-2.5 w-2.5" />
                  </a>
                ))}
              </div>
            </section>
          )}

          {/* No Research Data */}
          {!research && leadership.length === 0 && (
            <div className="text-center py-12 text-slate-500">
              No research data available. Click &quot;Research Firm&quot; to gather information.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
