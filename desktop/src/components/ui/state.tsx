import * as React from "react";
import { AlertTriangle, Inbox } from "lucide-react";

import { cn } from "../../lib/utils";
import { Alert, AlertDescription, AlertTitle } from "./alert";
import { Button } from "./button";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "./empty";
import { ErrorDetails } from "./error-details";
import { ShadcnSkeleton } from "./skeleton";
import { Spinner } from "./spinner";

interface StateBlockProps extends React.HTMLAttributes<HTMLDivElement> {
  title: string;
  description?: string;
  icon?: React.ReactNode;
}

interface EmptyStateProps extends StateBlockProps {
  action?: React.ReactNode;
}

/** Product composition of the vendored shadcn Empty primitives. */
function EmptyState({ title, description, action, icon, className, ...props }: EmptyStateProps) {
  return (
    <Empty className={cn("min-h-48", className)} {...props}>
      <EmptyHeader>
        <EmptyMedia variant="icon">{icon ?? <Inbox aria-hidden="true" />}</EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        {description ? <EmptyDescription>{description}</EmptyDescription> : null}
      </EmptyHeader>
      {action ? <EmptyContent>{action}</EmptyContent> : null}
    </Empty>
  );
}

interface ErrorStateProps extends StateBlockProps {
  error?: unknown;
  onRetry?: () => void;
  retryLabel?: string;
}

/** Product composition of the vendored shadcn Alert primitives. */
function ErrorState({ title, description, error, icon, onRetry, retryLabel = "重试", className, ...props }: ErrorStateProps) {
  return (
    <Alert variant="destructive" className={className} {...props}>
      {icon ?? <AlertTriangle aria-hidden="true" />}
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>
        {description ? <p>{description}</p> : null}
        {onRetry ? <Button size="sm" variant="outline" onClick={onRetry}>{retryLabel}</Button> : null}
        {error ? <ErrorDetails error={error} /> : null}
      </AlertDescription>
    </Alert>
  );
}

interface LoadingStateProps extends React.HTMLAttributes<HTMLDivElement> {
  label?: string;
}

/** shadcn Spinner in the documented Empty loading composition. */
function LoadingState({ label = "加载中", className, ...props }: LoadingStateProps) {
  return (
    <Empty role="status" className={cn("min-h-32 gap-3 p-6 md:p-8", className)} {...props}>
      <EmptyHeader>
        <EmptyMedia><Spinner role="presentation" aria-label={undefined} /></EmptyMedia>
        <EmptyTitle className="text-sm">{label}</EmptyTitle>
      </EmptyHeader>
    </Empty>
  );
}

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "text" | "row" | "control";
}

const SKELETON_VARIANTS = {
  text: "h-3 w-full",
  row: "h-8 w-full",
  control: "h-8 w-24",
} as const;

function Skeleton({ variant = "text", className, ...props }: SkeletonProps) {
  return <ShadcnSkeleton aria-hidden="true" className={cn(SKELETON_VARIANTS[variant], className)} {...props} />;
}

export { EmptyState, ErrorState, LoadingState, Skeleton };
