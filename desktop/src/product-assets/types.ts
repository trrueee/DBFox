export type ProductAssetTone = "calm" | "expert" | "urgent" | "friendly" | "security";

export type IconKey =
  | "Sparkles"
  | "Database"
  | "Terminal"
  | "ShieldCheck"
  | "Workflow"
  | "LineChart"
  | "Cpu"
  | "FileText"
  | "GitBranch"
  | "Lock"
  | "CheckCircle2"
  | "AlertTriangle"
  | "MessageSquare"
  | "Layers3"
  | "FlaskConical"
  | "Clock3"
  | "Search";

export type ProductCta = {
  label: string;
  variant: "primary" | "secondary" | "ghost" | "danger";
  action: string;
  helperText?: string;
};

export type ProductHero = {
  eyebrow: string;
  title: string;
  subtitle: string;
  description: string;
  primaryCta: ProductCta;
  secondaryCta: ProductCta;
  proofPoints: string[];
};

export type ProductPersona = {
  id: string;
  name: string;
  role: string;
  pain: string;
  outcome: string;
  defaultPrompt: string;
  recommendedEntry: string;
};

export type ProductFeatureCard = {
  id: string;
  icon: IconKey;
  title: string;
  subtitle: string;
  description: string;
  bullets: string[];
  badge?: string;
  cta?: ProductCta;
};

export type ProductWorkflowStep = {
  id: string;
  step: number;
  title: string;
  description: string;
  surface: "datasource" | "schema" | "sql" | "agent" | "approval" | "eval" | "history";
  successState: string;
};

export type ProductOnboardingStep = {
  id: string;
  title: string;
  description: string;
  actionLabel: string;
  targetRoute: string;
  completionSignal: string;
  emptyStateCopy: string;
};

export type ProductPrompt = {
  id: string;
  label: string;
  prompt: string;
  intent: "ask" | "sql" | "explain" | "audit" | "compare" | "repair";
  requiredContext: string[];
  exampleResult: string;
};

export type ProductEmptyState = {
  id: string;
  surface: "datasource" | "schema" | "query" | "agent" | "history" | "eval" | "semantic";
  title: string;
  description: string;
  primaryAction?: ProductCta;
  secondaryAction?: ProductCta;
  tips: string[];
};

export type ProductTrustSignal = {
  id: string;
  icon: IconKey;
  label: string;
  value: string;
  description: string;
  tone: ProductAssetTone;
};

export type ProductKpiCard = {
  id: string;
  label: string;
  value: string;
  delta: string;
  caption: string;
  tone: "neutral" | "good" | "warning" | "danger";
};

export type ProductDemoScenario = {
  id: string;
  title: string;
  industry: string;
  userQuestion: string;
  tables: string[];
  agentPlan: string[];
  safeSqlPreview: string;
  insightCards: ProductKpiCard[];
  followUps: string[];
};

export type ProductReleaseHighlight = {
  id: string;
  title: string;
  description: string;
  tags: string[];
};

export type ProductFaqItem = {
  id: string;
  question: string;
  answer: string;
  relatedSurface: string;
};

export type ProductNavigationCopy = {
  headerTabs: Array<{ id: string; label: string; tooltip: string }>;
  commandItems: Array<{ id: string; label: string; hint: string; action: string }>;
  toast: Record<string, string>;
};

export type ProductAssets = {
  brand: {
    name: string;
    tagline: string;
    oneLiner: string;
    keywords: string[];
  };
  hero: ProductHero;
  personas: ProductPersona[];
  features: ProductFeatureCard[];
  workflow: ProductWorkflowStep[];
  onboarding: ProductOnboardingStep[];
  prompts: ProductPrompt[];
  emptyStates: ProductEmptyState[];
  trustSignals: ProductTrustSignal[];
  demoScenarios: ProductDemoScenario[];
  releaseHighlights: ProductReleaseHighlight[];
  faq: ProductFaqItem[];
  navigation: ProductNavigationCopy;
};
