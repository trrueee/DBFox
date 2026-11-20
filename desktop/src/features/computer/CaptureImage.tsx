import { useEffect, useRef } from "react";

/** Blob lifetime is local UI state; image bytes never enter persisted stores. */
export function CaptureImage({ image, alt }: { image: Blob; alt: string }) {
  const element = useRef<HTMLImageElement>(null);
  useEffect(() => {
    const url = URL.createObjectURL(image);
    if (element.current) element.current.src = url;
    return () => URL.revokeObjectURL(url);
  }, [image]);
  return <img ref={element} alt={alt} draggable={false} className="computer-capture" />;
}
