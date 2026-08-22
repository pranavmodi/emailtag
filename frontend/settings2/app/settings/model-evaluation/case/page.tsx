import { CaseDetailClient } from "./CaseDetailClient";

type Query = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function ModelEvaluationCasePage({
  searchParams,
}: {
  searchParams: Promise<Query>;
}) {
  const query = await searchParams;
  return (
    <CaseDetailClient
      caseType={first(query.case_type)}
      caseId={first(query.case_id)}
      conversationId={first(query.conversation_id)}
      emailId={first(query.email_id)}
      resultIndex={first(query.result_index)}
      objective={first(query.objective)}
      filename={first(query.filename)}
      contentType={first(query.content_type)}
      frontUrl={first(query.front_url)}
    />
  );
}
