import { JsonView } from "react-json-view-lite";
import { type JsonValue } from "./jsonValue";

const jsonViewStyles = {
  container: "dbfox-json-view",
  basicChildStyle: "dbfox-json-view__item",
  label: "dbfox-json-view__label",
  clickableLabel: "dbfox-json-view__label dbfox-json-view__label--clickable",
  nullValue: "dbfox-json-view__value dbfox-json-view__value--null",
  undefinedValue: "dbfox-json-view__value dbfox-json-view__value--null",
  numberValue: "dbfox-json-view__value dbfox-json-view__value--number",
  stringValue: "dbfox-json-view__value dbfox-json-view__value--string",
  booleanValue: "dbfox-json-view__value dbfox-json-view__value--boolean",
  otherValue: "dbfox-json-view__value",
  punctuation: "dbfox-json-view__punctuation",
  expandIcon: "dbfox-json-view__toggle dbfox-json-view__toggle--collapsed",
  collapseIcon: "dbfox-json-view__toggle dbfox-json-view__toggle--expanded",
  collapsedContent: "dbfox-json-view__collapsed-content",
  childFieldsContainer: "dbfox-json-view__children",
  quotesForFieldNames: true,
  noQuotesForStringValues: false,
  stringifyStringValues: false,
  ariaLables: {
    collapseJson: "折叠 JSON 节点",
    expandJson: "展开 JSON 节点",
  },
};

// Upstream calls this CSS-class map `style`, but it never becomes a DOM style
// attribute. Keep it in a component-props object so the CSP source contract can
// continue rejecting every JSX inline-style attribute without a false positive.
const jsonViewPresentationProps = {
  style: jsonViewStyles,
  shouldExpandNode: shouldExpandJsonNode,
  clickToExpandNode: true,
};

export function JsonTree({ data }: { data: JsonValue }) {
  if (data === null || typeof data !== "object") {
    return <span className={scalarClassName(data)}>{formatScalar(data)}</span>;
  }

  return (
    <JsonView
      aria-label="JSON 结构"
      data={data}
      {...jsonViewPresentationProps}
    />
  );
}

function shouldExpandJsonNode(level: number, value: unknown) {
  if (level === 0) return true;
  if (level >= 2) return false;
  if (Array.isArray(value)) return value.length <= 24;
  return value !== null && typeof value === "object" && Object.keys(value).length <= 24;
}

function scalarClassName(value: null | boolean | number | string) {
  if (value === null) return "dbfox-json-view__value dbfox-json-view__value--null";
  return `dbfox-json-view__value dbfox-json-view__value--${typeof value}`;
}

function formatScalar(value: null | boolean | number | string) {
  return typeof value === "string" ? JSON.stringify(value) : String(value);
}
