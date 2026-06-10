import type { ReactNode } from "react";

interface LayoutRegionProps {
  top: ReactNode;
  left: ReactNode;
  center: ReactNode;
  right: ReactNode;
  bottom: ReactNode;
}

export function LayoutRegion({ top, left, center, right, bottom }: LayoutRegionProps) {
  return (
    <div className="wb">
      <div className="wb-top">{top}</div>
      <div className="wb-body">
        <div className="wb-left">{left}</div>
        <div className="wb-center">{center}</div>
        <div className="wb-right">{right}</div>
      </div>
      <div className="wb-bottom">{bottom}</div>
    </div>
  );
}
