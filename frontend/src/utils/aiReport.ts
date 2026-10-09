import type { AIReport, AIReportContent } from '../types/ai'

/**
 * Normalizes an AIReport returned from the backend or cache.
 * Ensures that both nested `report.content` and top-level fields
 * (`executive_summary`, `risk_assessment`, `transformation_specs`, etc.)
 * are fully populated and consistent.
 */
export function normalizeAIReport(raw: any): AIReport {
  if (!raw) return raw

  const rawContent = raw.content ?? {}
  const content: AIReportContent = {
    executive_summary: rawContent.executive_summary ?? raw.executive_summary ?? '',
    risk_assessment: (rawContent.risk_assessment ?? raw.risk_assessment ?? []).map((r: any) => ({
      risk_type: r.risk_type ?? r.category ?? 'General Risk',
      category: r.category ?? r.risk_type ?? 'General Risk',
      severity: r.severity ?? 'INFO',
      summary: r.summary ?? '',
      ml_impact: r.ml_impact ?? '',
    })),
    prioritized_remediation_steps:
      rawContent.prioritized_remediation_steps ??
      rawContent.remediation_plan ??
      raw.prioritized_remediation_steps ??
      raw.remediation_plan ??
      [],
    remediation_plan:
      rawContent.remediation_plan ??
      rawContent.prioritized_remediation_steps ??
      raw.remediation_plan ??
      raw.prioritized_remediation_steps ??
      [],
    ml_preparation_plan: rawContent.ml_preparation_plan ?? raw.ml_preparation_plan ?? [],
    transformation_specs: rawContent.transformation_specs ?? raw.transformation_specs ?? [],
    generated_python_code: rawContent.generated_python_code ?? raw.generated_python_code ?? null,
  }

  return {
    ...raw,
    content,
    executive_summary: raw.executive_summary ?? content.executive_summary,
    risk_assessment: raw.risk_assessment ?? content.risk_assessment,
    remediation_plan: raw.remediation_plan ?? content.remediation_plan,
    transformation_specs: raw.transformation_specs ?? content.transformation_specs,
    ml_preparation_plan: raw.ml_preparation_plan ?? content.ml_preparation_plan,
    generated_python_code: raw.generated_python_code ?? content.generated_python_code,
  }
}
