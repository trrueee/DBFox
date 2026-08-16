/**
 * 数据库官方品牌标识组件。
 *
 * 路径数据来自 simple-icons（CC0 公共领域，无署名要求），见
 * databaseBrandData.ts；品牌色为数据常量而非主题令牌。
 */
import "./DatabaseBrandIcon.css";
import { BRAND_PATHS, isDatabaseBrandType } from "./databaseBrandData";

export function DatabaseBrandIcon({
  dbType,
  size = 16,
  className,
}: {
  dbType: string | null | undefined;
  size?: number;
  className?: string;
}) {
  const type = isDatabaseBrandType(dbType) ? dbType : null;
  const path = type ? BRAND_PATHS[type] : null;
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={`database-brand-icon${className ? ` ${className}` : ""}`}
      data-db={type ?? "generic"}
      aria-hidden="true"
      role="img"
    >
      {path ? <path d={path} fill="currentColor" /> : null}
    </svg>
  );
}
