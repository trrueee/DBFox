import * as React from "react";

interface TooltipProps {
  content: string;
  children: React.ReactElement;
  side?: "top" | "bottom" | "left" | "right";
}

function Tooltip({ content, children }: TooltipProps) {
  const [visible, setVisible] = React.useState(false);
  const triggerRef = React.useRef<HTMLDivElement>(null);

  return (
    <div
      className="relative inline-flex"
      ref={triggerRef}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
    >
      {children}
      {visible && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 z-50 animate-slide-up">
          <div className="bg-[var(--text-primary)] text-[var(--text-inverse)] text-[0.65rem] px-2 py-1 rounded-sm whitespace-nowrap shadow-md">
            {content}
          </div>
        </div>
      )}
    </div>
  );
}

export { Tooltip };
