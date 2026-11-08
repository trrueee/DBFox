import { forwardRef, type ForwardRefExoticComponent, type RefAttributes, type SVGProps } from "react";

export type IconWeight = "regular" | "duotone" | "fill";
export type IconProps = Omit<SVGProps<SVGSVGElement>, "width" | "height"> & {
  size?: number | string;
  weight?: IconWeight;
  mirrored?: boolean;
};
export type IconComponent = ForwardRefExoticComponent<IconProps & RefAttributes<SVGSVGElement>>;

/** Native SVG rendering of the pinned upstream artwork. No icon or UI state lives here. */
export function createIcon(sprite: string, name: string, defaultWeight: IconWeight = "regular"): IconComponent {
  const Icon = forwardRef<SVGSVGElement, IconProps>(({ size = 20, weight = defaultWeight, mirrored = false, ...props }, ref) => (
    <svg ref={ref} xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 256 256"
      fill="currentColor" aria-hidden={props["aria-label"] ? undefined : true} focusable="false"
      role={props["aria-label"] ? "img" : undefined} {...props} data-ui-icon={name} data-weight={weight}>
      <use href={`${sprite}#${name}-${weight}`} transform={mirrored ? "translate(256 0) scale(-1 1)" : undefined} />
    </svg>
  ));
  Icon.displayName = name;
  return Icon;
}
