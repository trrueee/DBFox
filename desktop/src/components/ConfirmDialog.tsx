import { useEffect, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";
import gsap from "gsap";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "danger" | "warning" | "info";
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "确认",
  cancelLabel = "取消",
  variant = "info",
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const [mounted, setMounted] = useState(false);
  const backdropRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const tlRef = useRef<gsap.core.Timeline | null>(null);

  useEffect(() => {
    if (open) {
      setMounted(true);
      tlRef.current?.kill();
      const tl = gsap.timeline();
      tl.fromTo(backdropRef.current, { opacity: 0 }, { opacity: 1, duration: 0.15, ease: "power1.out" })
        .fromTo(
          cardRef.current,
          { opacity: 0, scale: 0.92 },
          { opacity: 1, scale: 1, duration: 0.35, ease: "back.out(1.3)" },
          "-=0.05",
        );
      tlRef.current = tl;
    } else if (!open && mounted) {
      tlRef.current?.kill();
      const tl = gsap.timeline({
        onComplete: () => setMounted(false),
      });
      tl.to(cardRef.current, { opacity: 0, scale: 0.95, duration: 0.15, ease: "power2.in" })
        .to(backdropRef.current, { opacity: 0, duration: 0.12, ease: "power1.in" }, "-=0.06");
      tlRef.current = tl;
    }
  }, [open, mounted]);

  if (!mounted) return null;

  const confirmBg =
    variant === "danger"
      ? "var(--accent-red)"
      : variant === "warning"
        ? "var(--accent-amber)"
        : "var(--accent-indigo)";

  const iconColor =
    variant === "danger"
      ? "var(--accent-red)"
      : variant === "warning"
        ? "var(--accent-amber)"
        : "var(--accent-indigo)";

  return (
    <div
      ref={backdropRef}
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0, 0, 0, 0.5)",
        backdropFilter: "blur(4px)",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        zIndex: 9998,
      }}
      onClick={onCancel}
    >
      <div
        ref={cardRef}
        style={{
          background: "var(--bg-surface)",
          borderRadius: "var(--radius-lg)",
          boxShadow: "var(--shadow-xl)",
          width: "min(440px, 90vw)",
          overflow: "hidden",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ padding: "24px 24px 16px" }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: "var(--radius-md)",
                background:
                  variant === "danger"
                    ? "var(--accent-red-light)"
                    : variant === "warning"
                      ? "var(--accent-amber-light)"
                      : "var(--accent-indigo-light)",
                display: "grid",
                placeItems: "center",
                flexShrink: 0,
              }}
            >
              <AlertTriangle size={18} style={{ color: iconColor }} />
            </div>
            <div>
              <h3 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: 6 }}>{title}</h3>
              <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
                {message}
              </p>
            </div>
          </div>
        </div>
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
            padding: "12px 24px",
            borderTop: "1px solid var(--border-light)",
            background: "var(--bg-secondary)",
          }}
        >
          <button className="btn-secondary" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            style={{
              padding: "8px 16px",
              borderRadius: "var(--radius-sm)",
              border: "none",
              fontWeight: 600,
              fontSize: "0.85rem",
              color: "#fff",
              background: confirmBg,
              cursor: "pointer",
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
