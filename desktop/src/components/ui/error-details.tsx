import { ChevronRight } from "lucide-react";

import { ApiError } from "../../lib/api/client";
import "./error-details.css";

interface ErrorDetailsProps {
  error: unknown;
  label?: string;
}

interface ProblemDetailShape {
  request_id?: unknown;
  errors?: unknown;
}

function safeIdentifier(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  return normalized.length > 0
    && normalized.length <= 128
    && /^[a-zA-Z0-9._:-]+$/u.test(normalized)
    ? normalized
    : null;
}

function problemDetail(error: ApiError): ProblemDetailShape | null {
  return error.detail !== null && typeof error.detail === "object" && !Array.isArray(error.detail)
    ? error.detail as ProblemDetailShape
    : null;
}

/** Radix disclosure over the existing RFC 9457/ApiError boundary; raw payload values are never rendered. */
export function ErrorDetails({ error, label = "技术详情" }: ErrorDetailsProps) {
  if (!(error instanceof ApiError)) return null;

  const detail = problemDetail(error);
  const code = safeIdentifier(error.code);
  const requestId = safeIdentifier(detail?.request_id);
  const status = Number.isInteger(error.status) ? error.status : null;
  const checksCount = Array.isArray(error.checks) ? error.checks.length : 0;
  const errorsCount = Array.isArray(detail?.errors) ? detail.errors.length : 0;
  if (status === null && !code && !requestId && checksCount === 0 && errorsCount === 0) return null;

  return (
    <details className="error-details">
      <summary className="error-details__trigger">
        <ChevronRight className="error-details__chevron" size={14} aria-hidden="true" />
        {label}
      </summary>
      <div className="error-details__content">
        <dl>
          {status !== null ? <div><dt>HTTP 状态</dt><dd><code>{status}</code></dd></div> : null}
          {code ? <div><dt>错误代码</dt><dd><code>{code}</code></dd></div> : null}
          {requestId ? <div><dt>请求 ID</dt><dd><code>{requestId}</code></dd></div> : null}
          {checksCount > 0 ? <div><dt>检查项</dt><dd>{checksCount} 项</dd></div> : null}
          {errorsCount > 0 ? <div><dt>字段错误</dt><dd>{errorsCount} 项</dd></div> : null}
        </dl>
      </div>
    </details>
  );
}
