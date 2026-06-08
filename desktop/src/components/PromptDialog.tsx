import { useEffect, useRef, useState } from "react";
import gsap from "gsap";

interface PromptDialogProps {
  open: boolean;
  title: string;
  placeholder?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: (value: string) => void;
  onCancel: () => void;
}

export function PromptDialog({
  open,
  title,
  placeholder = "",
  confirmLabel = "确认",
  cancelLabel = "取消",
  onConfirm,
  onCancel,
}: PromptDialogProps) {
  const [value, setValue] = useState("");
  const [mounted, setMounted] = useState(false);
  const backdropRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const tlRef = useRef<gsap.core.Timeline | null>(null);

  useEffect(() => {
    if (open) {
      setMounted(true);
      setValue("");
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
          width: "min(380px, 90vw)",
          overflow: "hidden",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ padding: "24px 24px 16px" }}>
          <h3 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: 12 }}>{title}</h3>
          <input
            className="input-field"
            autoFocus
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={placeholder}
            onKeyDown={(e) => {
              if (e.key === "Enter" && value.trim()) {
                onConfirm(value.trim());
                setValue("");
              }
              if (e.key === "Escape") onCancel();
            }}
          />
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
          <button
            className="btn-secondary"
            onClick={() => {
              onCancel();
              setValue("");
            }}
          >
            {cancelLabel}
          </button>
          <button
            className="btn-primary"
            onClick={() => {
              if (value.trim()) {
                onConfirm(value.trim());
                setValue("");
              }
            }}
            disabled={!value.trim()}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
