/**
 * Vendored from Vercel AI Elements Sources.
 * Upstream: https://elements.ai-sdk.dev/components/sources
 * Registry: https://elements.ai-sdk.dev/api/registry/sources.json
 * License: Apache-2.0
 *
 * Adaptation: semantic DBFox class names, localized default copy, and native
 * details/summary disclosure so the component remains compatible with the
 * Renderer's no-ad-hoc-inline-style application contract.
 */
import { cn } from "../../lib/utils";
import { BookOpen, ChevronDown } from "lucide-react";
import type { ComponentProps } from "react";
import "./sources.css";

export type SourcesProps = ComponentProps<"details">;

export const Sources = ({ className, ...props }: SourcesProps) => (
  <details className={cn("dbfox-sources", className)} {...props} />
);

export type SourcesTriggerProps = ComponentProps<"summary"> & {
  count: number;
};

export const SourcesTrigger = ({
  className,
  count,
  children,
  ...props
}: SourcesTriggerProps) => (
  <summary
    className={cn("dbfox-sources__trigger", className)}
    {...props}
  >
    {children ?? (
      <>
        <BookOpen size={14} aria-hidden="true" />
        <span>使用了 {count} 个来源</span>
        <ChevronDown className="dbfox-sources__chevron" size={14} aria-hidden="true" />
      </>
    )}
  </summary>
);

export type SourcesContentProps = ComponentProps<"div">;

export const SourcesContent = ({
  className,
  ...props
}: SourcesContentProps) => (
  <div
    className={cn("dbfox-sources__content", className)}
    {...props}
  />
);

export type SourceProps = ComponentProps<"a">;

export const Source = ({ href, title, children, className, ...props }: SourceProps) => (
  <a
    className={cn("dbfox-source", className)}
    href={href}
    rel="noreferrer"
    target="_blank"
    {...props}
  >
    {children ?? (
      <>
        <BookOpen size={14} aria-hidden="true" />
        <span>{title}</span>
      </>
    )}
  </a>
);
