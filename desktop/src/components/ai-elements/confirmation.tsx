/*
 * Vendored from Vercel AI Elements Confirmation (Apache-2.0):
 * https://elements.ai-sdk.dev/components/confirmation
 * https://elements.ai-sdk.dev/api/registry/confirmation.json
 *
 * The upstream compound-component anatomy is retained. DBFox supplies its
 * durable approval decision directly, so the AI SDK ToolUIPart dependency is
 * replaced by the four presentation states this primitive actually renders.
 */
import type { ComponentProps, ReactNode } from "react";
import { createContext, useContext, useMemo } from "react";

import { cn } from "../../lib/utils";
import { Alert, AlertDescription } from "../ui/alert";
import { Button } from "../ui/button";

type ConfirmationState =
  | "approval-requested"
  | "approval-responded"
  | "output-denied"
  | "output-available";

interface ConfirmationContextValue {
  approved?: boolean;
  state: ConfirmationState;
}

const ConfirmationContext = createContext<ConfirmationContextValue | null>(null);

function useConfirmation() {
  const context = useContext(ConfirmationContext);
  if (!context) throw new Error("Confirmation components must be used within Confirmation");
  return context;
}

type ConfirmationProps = ComponentProps<typeof Alert> & ConfirmationContextValue;

function Confirmation({ className, approved, state, ...props }: ConfirmationProps) {
  const contextValue = useMemo(() => ({ approved, state }), [approved, state]);
  return (
    <ConfirmationContext.Provider value={contextValue}>
      <Alert className={cn("flex flex-col gap-2", className)} {...props} />
    </ConfirmationContext.Provider>
  );
}

type ConfirmationTitleProps = ComponentProps<typeof AlertDescription>;

function ConfirmationTitle({ className, ...props }: ConfirmationTitleProps) {
  return <AlertDescription className={cn("inline", className)} {...props} />;
}

function ConfirmationRequest({ children }: { children?: ReactNode }) {
  return useConfirmation().state === "approval-requested" ? children : null;
}

function ConfirmationAccepted({ children }: { children?: ReactNode }) {
  const { approved, state } = useConfirmation();
  return approved === true && ["approval-responded", "output-available"].includes(state) ? children : null;
}

function ConfirmationRejected({ children }: { children?: ReactNode }) {
  const { approved, state } = useConfirmation();
  return approved === false && ["approval-responded", "output-denied", "output-available"].includes(state) ? children : null;
}

type ConfirmationActionsProps = ComponentProps<"div">;

function ConfirmationActions({ className, ...props }: ConfirmationActionsProps) {
  if (useConfirmation().state !== "approval-requested") return null;
  return <div className={cn("flex flex-wrap items-center justify-end gap-2 self-end", className)} {...props} />;
}

type ConfirmationActionProps = ComponentProps<typeof Button>;

function ConfirmationAction(props: ConfirmationActionProps) {
  return <Button size="sm" type="button" {...props} />;
}

export {
  Confirmation,
  ConfirmationAccepted,
  ConfirmationAction,
  ConfirmationActions,
  ConfirmationRejected,
  ConfirmationRequest,
  ConfirmationTitle,
};
