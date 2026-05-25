import { useState, useEffect } from "react";
import { Sparkles, ChevronDown, ChevronUp, ArrowRight, Play, Check, AlertCircle } from "lucide-react";
import type { DataSource, Project, SchemaTable } from "../lib/api";

interface DemoTourGuideProps {
  activeTab: string;
  setActiveTab: (tab: any) => void;
  activeProject: Project | null;
  projects: Project[];
  activeDataSource: DataSource | null;
  datasources: DataSource[];
  schemaTables: SchemaTable[];
  handleCreateProject: (name?: string) => Promise<void>;
}

export const DemoTourGuide = ({
  activeTab,
  setActiveTab,
  projects,
  activeDataSource,
  datasources,
  schemaTables,
  handleCreateProject,
}: DemoTourGuideProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [completedSteps, setCompletedSteps] = useState<number[]>([]);
  const [activeStep, setActiveStep] = useState(0);

  // 10 key steps representing the user lifecycle
  const steps = [
    {
      id: 0,
      title: "新建项目空间",
      desc: "创建项目用来划分独立的多租户环境与安全边界。",
      badge: "安全隔离",
      tab: "datasources",
      isActive: () => projects.length === 0,
      isDone: () => projects.length > 0,
      onAction: async () => {
        await handleCreateProject("演示项目");
      },
      actionText: "新建项目",
    },
    {
      id: 1,
      title: "启动 MySQL 本地环境",
      desc: "去「Environments」秒级拉起一个本地隔离的 MySQL 容器。",
      badge: "Docker 编排",
      tab: "environments",
      isActive: () => projects.length > 0 && datasources.length === 0,
      isDone: () => datasources.length > 0, // An active datasource means environment exists and was registered!
      onAction: () => {
        setActiveTab("environments");
      },
      actionText: "前往拉起环境",
    },
    {
      id: 2,
      title: "连接数据源",
      desc: "进入「数据源」管理并双击激活当前的测试连接。",
      badge: "配置加密",
      tab: "datasources",
      isActive: () => datasources.length > 0 && !activeDataSource,
      isDone: () => !!activeDataSource,
      onAction: () => {
        setActiveTab("datasources");
      },
      actionText: "激活连接",
    },
    {
      id: 3,
      title: "AI 智能辅助建模",
      desc: "进入「Schema」的「设计草稿」，通过自然语言生成表定义模型。",
      badge: "本地语义匹配",
      tab: "schema",
      isActive: () => !!activeDataSource && schemaTables.length === 0 && activeTab !== "schema",
      isDone: () => schemaTables.length > 0, // If tables exist, the schema has tables!
      onAction: () => {
        setActiveTab("schema");
        // We can let them click to switch to design tab in schema page
      },
      actionText: "AI 辅助建表",
      hasTemplate: true,
      templateText: "设计一个电商订单系统，包含 users、orders、order_items、products 表，并建立正确的主外键关系，字段需要添加详细注释和默认值。",
      targetSelector: "textarea[placeholder*='输入建表需求']",
    },
    {
      id: 4,
      title: "保存设计草稿",
      desc: "在建表界面左侧，点击「保存草稿」持久化设计到 SQLite 元数据库。",
      badge: "草稿持久化",
      tab: "schema",
      isActive: () => activeTab === "schema" && schemaTables.length === 0,
      isDone: () => schemaTables.length > 0, // Keep simple flow check
      onAction: () => {
        setActiveTab("schema");
      },
      actionText: "查看设计草稿",
    },
    {
      id: 5,
      title: "安全审计与 DDL 执行",
      desc: "生成 DDL CREATE 语句，核对安全提示后点击「执行 DDL」写入真实数据库。",
      badge: "安全执行边界",
      tab: "schema",
      isActive: () => activeTab === "schema" && schemaTables.length > 0,
      isDone: () => schemaTables.length > 0,
      onAction: () => {
        setActiveTab("schema");
      },
      actionText: "安全审计 DDL",
    },
    {
      id: 6,
      title: "数据关系 ER 图展示",
      desc: "切换到「关系图」，查看由主外键拓扑链路自动生成的炫酷 ER 实体关系图。",
      badge: "主外键拓扑",
      tab: "schema",
      isActive: () => activeTab === "schema" && schemaTables.length > 1,
      isDone: () => schemaTables.length > 1,
      onAction: () => {
        setActiveTab("schema");
      },
      actionText: "查看 ER 关系图",
    },
    {
      id: 7,
      title: "智能填充关联测试数据",
      desc: "在 Schema 的「数据预览」中，点击「AI 造数据」，智能填充高仿真多表外键关联记录！",
      badge: "智能外键映射",
      tab: "schema",
      isActive: () => activeTab === "schema" && schemaTables.length > 0,
      isDone: () => schemaTables.some(t => (t.row_count_estimate || 0) > 0),
      onAction: () => {
        setActiveTab("schema");
      },
      actionText: "AI 注入测试数据",
    },
    {
      id: 8,
      title: "NL 问数与安全 SQL 审计",
      desc: "在「工作台」输入中文需求，AI 智能翻译 SQL，经 AST 语法网关安全审计后执行。",
      badge: "AST 语法网关",
      tab: "query",
      isActive: () => activeTab === "query" || (!!activeDataSource && schemaTables.length > 0 && activeTab !== "query"),
      isDone: () => false, // Let user explore
      onAction: () => {
        setActiveTab("query");
      },
      actionText: "AI 安全问数",
      hasTemplate: true,
      templateText: "查询每个用户的订单总额，按总额降序排列，只返回排名前 5 的用户。",
      targetSelector: "textarea[placeholder*='用自然语言描述']",
    },
    {
      id: 9,
      title: "一键备份与灾备重建",
      desc: "进入「Backups」对数据源进行快速备份；并在环境崩溃时支持秒级重建一键恢复！",
      badge: "高可用灾备",
      tab: "backups",
      isActive: () => activeTab === "backups",
      isDone: () => false,
      onAction: () => {
        setActiveTab("backups");
      },
      actionText: "前往灾备中心",
    },
  ];

  // Recalculate which steps are done
  useEffect(() => {
    const done: number[] = [];
    steps.forEach((s) => {
      if (s.isDone()) done.push(s.id);
    });
    setCompletedSteps(done);

    // Set active step based on active tab and conditions
    let foundActive = 0;
    for (let i = steps.length - 1; i >= 0; i--) {
      if (steps[i].isActive()) {
        foundActive = i;
        break;
      }
    }
    setActiveStep(foundActive);
  }, [projects.length, datasources.length, activeDataSource?.id, schemaTables.length, activeTab]);

  const handleTemplateInject = (text: string, selector: string) => {
    // Elegant typing animation helper
    const textarea = document.querySelector(selector) as HTMLTextAreaElement | null;
    if (!textarea) {
      alert("请先前往该步骤页面，激活输入区域！");
      return;
    }

    textarea.focus();
    let currentText = "";
    let charIdx = 0;

    // Clear existing
    textarea.value = "";
    
    const interval = setInterval(() => {
      if (charIdx < text.length) {
        currentText += text[charIdx];
        textarea.value = currentText;
        // Trigger React's Synthetic Event handler to sync state
        const event = new Event("input", { bubbles: true });
        textarea.dispatchEvent(event);
        charIdx++;
      } else {
        clearInterval(interval);
      }
    }, 20);
  };

  const doneCount = completedSteps.length;
  const progressPercent = Math.min(100, Math.round((doneCount / 7) * 100)); // Out of 7 core milestone steps

  return (
    <div
      style={{
        position: "fixed",
        bottom: 24,
        right: 24,
        zIndex: 900,
        fontFamily: "Inter, system-ui, sans-serif",
      }}
    >
      {/* ── Collapsed Capsule State ── */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="hover-lift"
          style={{
            background: "linear-gradient(135deg, var(--accent-indigo) 0%, #4f46e5 100%)",
            color: "#fff",
            padding: "10px 18px",
            borderRadius: "30px",
            border: "none",
            boxShadow: "0 10px 25px -5px rgba(79, 70, 229, 0.4), 0 8px 10px -6px rgba(79, 70, 229, 0.4)",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: 8,
            fontSize: "0.85rem",
            fontWeight: 600,
          }}
        >
          <Sparkles size={16} className="animate-pulse" />
          <span>💡 体验 Demo 引导向导</span>
          <span
            style={{
              background: "rgba(255, 255, 255, 0.2)",
              padding: "2px 8px",
              borderRadius: 20,
              fontSize: "0.72rem",
            }}
          >
            {doneCount}/7 已完成
          </span>
          <ChevronUp size={14} />
        </button>
      )}

      {/* ── Expanded Stepper Panel State ── */}
      {isOpen && (
        <div
          className="lab-card animate-scale-up"
          style={{
            width: 390,
            maxHeight: 520,
            background: "var(--bg-surface)",
            boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.12), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
            border: "1px solid var(--border-light)",
            borderRadius: 16,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
          {/* Header */}
          <div
            style={{
              padding: "16px 20px",
              background: "linear-gradient(to right, var(--bg-secondary), var(--bg-surface))",
              borderBottom: "1px solid var(--border-light)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Sparkles size={16} style={{ color: "var(--accent-indigo)" }} />
              <div>
                <h4 style={{ fontWeight: 700, fontSize: "0.92rem", margin: 0, color: "var(--text-primary)" }}>
                  DataBox 全链路极速体验
                </h4>
                <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", margin: "2px 0 0" }}>
                  本地优先、安全可控的 AI 数据库开发工作台
                </p>
              </div>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="btn-ghost"
              style={{ padding: 4, borderRadius: 6 }}
            >
              <ChevronDown size={16} />
            </button>
          </div>

          {/* Progress Bar */}
          <div style={{ padding: "12px 20px 8px", borderBottom: "1px solid var(--border-light)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.74rem", marginBottom: 6 }}>
              <span style={{ color: "var(--text-secondary)", fontWeight: 500 }}>核心步骤演示进度</span>
              <strong style={{ color: "var(--accent-indigo)" }}>{progressPercent}% ({doneCount}/7)</strong>
            </div>
            <div style={{ width: "100%", height: 6, background: "var(--bg-active)", borderRadius: 3, overflow: "hidden" }}>
              <div
                style={{
                  width: `${progressPercent}%`,
                  height: "100%",
                  background: "linear-gradient(to right, var(--accent-indigo), var(--accent-teal))",
                  borderRadius: 3,
                  transition: "width 0.4s ease-out",
                }}
              />
            </div>
          </div>

          {/* Stepper Content */}
          <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
              {steps.map((step, idx) => {
                const isCompleted = completedSteps.includes(step.id);
                const isCurrent = activeStep === step.id;
                
                return (
                  <div key={step.id} style={{ display: "flex", gap: 12, position: "relative" }}>
                    {/* Visual Connector Line */}
                    {idx < steps.length - 1 && (
                      <div
                        style={{
                          position: "absolute",
                          left: 10,
                          top: 24,
                          bottom: -20,
                          width: 2,
                          background: isCompleted ? "var(--accent-green)" : "var(--border-light)",
                          opacity: 0.6,
                        }}
                      />
                    )}

                    {/* Step Dot Icon */}
                    <div style={{ position: "relative", zIndex: 1, marginTop: 2 }}>
                      {isCompleted ? (
                        <div
                          style={{
                            width: 20,
                            height: 20,
                            borderRadius: "50%",
                            background: "rgba(16, 185, 129, 0.12)",
                            color: "var(--accent-green)",
                            display: "grid",
                            placeItems: "center",
                          }}
                        >
                          <Check size={12} strokeWidth={3} />
                        </div>
                      ) : isCurrent ? (
                        <div
                          style={{
                            width: 20,
                            height: 20,
                            borderRadius: "50%",
                            background: "var(--accent-indigo)",
                            color: "#fff",
                            display: "grid",
                            placeItems: "center",
                            boxShadow: "0 0 0 4px rgba(79, 70, 229, 0.15)",
                          }}
                        >
                          <Play size={8} fill="#fff" style={{ marginLeft: 1 }} />
                        </div>
                      ) : (
                        <div
                          style={{
                            width: 20,
                            height: 20,
                            borderRadius: "50%",
                            background: "var(--bg-active)",
                            color: "var(--text-muted)",
                            display: "grid",
                            placeItems: "center",
                            fontSize: "0.7rem",
                            fontWeight: 600,
                          }}
                        >
                          {idx + 1}
                        </div>
                      )}
                    </div>

                    {/* Step Texts */}
                    <div style={{ flex: 1 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                        <span
                          style={{
                            fontWeight: isCurrent ? 700 : 600,
                            fontSize: "0.84rem",
                            color: isCurrent ? "var(--text-primary)" : "var(--text-secondary)",
                          }}
                        >
                          {step.title}
                        </span>
                        <span
                          style={{
                            fontSize: "0.64rem",
                            padding: "1px 5px",
                            borderRadius: 4,
                            background: "var(--bg-secondary)",
                            color: "var(--text-muted)",
                            fontWeight: 500,
                          }}
                        >
                          {step.badge}
                        </span>
                      </div>

                      <p
                        style={{
                          fontSize: "0.78rem",
                          color: "var(--text-muted)",
                          lineHeight: 1.4,
                          margin: "4px 0 6px",
                        }}
                      >
                        {step.desc}
                      </p>

                      {/* Step Actions */}
                      {isCurrent && (
                        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                          <button
                            className="btn-primary hover-lift"
                            style={{
                              padding: "4px 10px",
                              fontSize: "0.74rem",
                              display: "flex",
                              alignItems: "center",
                              gap: 4,
                              fontWeight: 600,
                            }}
                            onClick={() => step.onAction()}
                          >
                            <span>{step.actionText}</span>
                            <ArrowRight size={10} />
                          </button>

                          {step.hasTemplate && (
                            <button
                              className="btn-secondary hover-lift"
                              style={{
                                padding: "4px 10px",
                                fontSize: "0.74rem",
                                borderColor: "rgba(74, 91, 192, 0.2)",
                                color: "var(--accent-indigo)",
                                fontWeight: 600,
                              }}
                              onClick={() => handleTemplateInject(step.templateText!, step.targetSelector!)}
                            >
                              🪄 快捷填入
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Footer Note */}
          <div
            style={{
              padding: "12px 16px",
              background: "var(--bg-secondary)",
              borderTop: "1px solid var(--border-light)",
              fontSize: "0.7rem",
              color: "var(--text-muted)",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <AlertCircle size={12} style={{ color: "var(--accent-indigo)" }} />
            <span>向导将跟随您的操作自动记录和提示，加油！</span>
          </div>
        </div>
      )}
    </div>
  );
};
