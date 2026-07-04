export interface ERNode {
  id: string;
  label: string;
  fields: Array<{
    name: string;
    type: string;
    is_pk: boolean;
    is_fk: boolean;
    comment?: string;
  }>;
  comment: string;
  row_count_estimate?: number;
  module_tag: string;
}

export interface EREdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
  edge_type?: "real" | "inferred";
  label?: string;
}

export interface ERDiagramData {
  nodes: ERNode[];
  edges: EREdge[];
}
