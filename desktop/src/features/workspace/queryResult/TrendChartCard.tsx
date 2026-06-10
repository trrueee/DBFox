export function TrendChartCard() {
  return (
    <div className="hifi-ai-card mt-2">
      <div className="hifi-ai-card-header flex justify-between items-center">
        <span>数据趋势分析</span>
        <span className="hifi-guide-chip-prod">LINE CHART</span>
      </div>
      <div className="hifi-ai-card-body p-3">
        <svg viewBox="0 0 400 120" width="100%" height="100">
          <line x1="30" y1="20" x2="380" y2="20" stroke="#F1F5F9" strokeWidth="1" />
          <line x1="30" y1="50" x2="380" y2="50" stroke="#F1F5F9" strokeWidth="1" />
          <line x1="30" y1="80" x2="380" y2="80" stroke="#F1F5F9" strokeWidth="1" />
          <line x1="30" y1="100" x2="380" y2="100" stroke="#E2E8F0" strokeWidth="1.5" />
          <text x="5" y="23" fontSize="8" fill="#64748B">1.5K</text>
          <text x="10" y="53" fontSize="8" fill="#64748B">1K</text>
          <text x="10" y="83" fontSize="8" fill="#64748B">500</text>
          <text x="20" y="103" fontSize="8" fill="#64748B">0</text>
          <defs>
            <linearGradient id="glow-grad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#4F46E5" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#4F46E5" stopOpacity="0.0" />
            </linearGradient>
          </defs>
          <path d="M 30 100 Q 60 70 90 85 Q 130 40 160 90 Q 210 50 250 80 Q 300 30 380 60 L 380 100 Z" fill="url(#glow-grad)" />
          <path d="M 30 100 Q 60 70 90 85 Q 130 40 160 90 Q 210 50 250 80 Q 300 30 380 60" fill="none" stroke="#4F46E5" strokeWidth="2.5" />
          <circle cx="90" cy="85" r="3" fill="#FFFFFF" stroke="#4F46E5" strokeWidth="1.5" />
          <circle cx="160" cy="90" r="3" fill="#FFFFFF" stroke="#4F46E5" strokeWidth="1.5" />
          <circle cx="250" cy="80" r="3" fill="#FFFFFF" stroke="#4F46E5" strokeWidth="1.5" />
          <circle cx="380" cy="60" r="3" fill="#FFFFFF" stroke="#4F46E5" strokeWidth="1.5" />
        </svg>
      </div>
    </div>
  );
}
