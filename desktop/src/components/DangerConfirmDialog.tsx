import React, { useEffect, useRef, useState } from "react";
import { ShieldAlert, X, Loader2 } from "lucide-react";
import gsap from "gsap";

export interface ConfirmationDetails {
  confirm_token: string;
  impact_summary: string;
  expected_confirm_text: string;
  onConfirm: (confirmText: string) => Promise<void>;
  onCancel: () => void;
}

interface DangerConfirmDialogProps {
  details: ConfirmationDetails | null;
}

export const DangerConfirmDialog: React.FC<DangerConfirmDialogProps> = ({ details }) => {
  const [inputText, setInputText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [mounted, setMounted] = useState(false);
  const backdropRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const tlRef = useRef<gsap.core.Timeline | null>(null);

  useEffect(() => {
    if (details) {
      setMounted(true);
      setInputText("");
      setError("");
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
    } else if (!details && mounted) {
      tlRef.current?.kill();
      const tl = gsap.timeline({
        onComplete: () => setMounted(false),
      });
      tl.to(cardRef.current, { opacity: 0, scale: 0.95, duration: 0.15, ease: "power2.in" })
        .to(backdropRef.current, { opacity: 0, duration: 0.12, ease: "power1.in" }, "-=0.06");
      tlRef.current = tl;
    }
  }, [details, mounted]);

  if (!mounted) return null;

  const handleConfirm = async () => {
    if (inputText.trim() !== details.expected_confirm_text) {
      setError(`输入错误！请精确输入 '${details.expected_confirm_text}'`);
      return;
    }
    setLoading(true);
    setError("");
    try {
      await details.onConfirm(inputText);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "确认操作失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      ref={backdropRef}
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(15, 17, 23, 0.75)",
        backdropFilter: "blur(6px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 10000,
        padding: 24,
      }}
    >
      <div
        ref={cardRef}
        className="lab-card lab-card-elevated"
        style={{
          width: "100%",
          maxWidth: 500,
          background: "var(--bg-secondary)",
          border: "1px solid var(--accent-red)",
          boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.3)",
          borderRadius: 12,
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "16px 20px",
            borderBottom: "1px solid var(--border-light)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            background: "rgba(239, 68, 68, 0.08)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <ShieldAlert size={20} style={{ color: "var(--accent-red)" }} />
            <h4 style={{ margin: 0, fontSize: "1.05rem", fontWeight: 700, color: "var(--text-primary)" }}>
              安全中心：高危操作二次确认
            </h4>
          </div>
          <button
            style={{
              border: "none",
              background: "transparent",
              color: "var(--text-muted)",
              cursor: "pointer",
              padding: 4,
            }}
            onClick={details.onCancel}
            disabled={loading}
          >
            <X size={16} />
          </button>
        </div>

        {/* Content */}
        <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
          <div
            style={{
              whiteSpace: "pre-wrap",
              fontSize: "0.88rem",
              lineHeight: "1.5",
              color: "var(--text-primary)",
              background: "var(--bg-primary)",
              padding: 14,
              borderRadius: 8,
              border: "1px solid var(--border-light)",
              maxHeight: 250,
              overflow: "auto",
            }}
          >
            {details.impact_summary}
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <label className="field-label" style={{ fontSize: "0.82rem", color: "var(--accent-red)", fontWeight: 600 }}>
              请输入数据源名称 <code style={{ background: "rgba(239, 68, 68, 0.15)", padding: "2px 6px", borderRadius: 4, fontFamily: "var(--font-mono)" }}>{details.expected_confirm_text}</code> 以确认执行：
            </label>
            <input
              className="input-field"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder={details.expected_confirm_text}
              disabled={loading}
              style={{
                borderColor: inputText === details.expected_confirm_text ? "var(--accent-green)" : "var(--accent-red)",
              }}
            />
          </div>

          {error && (
            <div style={{ color: "var(--accent-red)", fontSize: "0.82rem", display: "flex", alignItems: "center", gap: 6 }}>
              <ShieldAlert size={14} />
              {error}
            </div>
          )}

          {/* Footer */}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 8 }}>
            <button className="btn-secondary" onClick={details.onCancel} disabled={loading}>
              取消
            </button>
            <button
              className="btn-primary"
              onClick={handleConfirm}
              disabled={loading || inputText.trim() !== details.expected_confirm_text}
              style={{
                background: "var(--accent-red)",
                borderColor: "var(--accent-red)",
                color: "#ffffff",
              }}
            >
              {loading && <Loader2 size={14} className="animate-spin" />}
              确认执行
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
