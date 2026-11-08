// Official Three primitives define both viewport geometry and offline exports.
import {
  BoxGeometry,
  ConeGeometry,
  CylinderGeometry,
  PlaneGeometry,
  SphereGeometry,
  TorusGeometry,
} from "three";

export * from "three";
export { OrbitControls } from "three/addons/controls/OrbitControls.js";
export { TransformControls } from "three/addons/controls/TransformControls.js";

export const PRIMITIVE_NAMES = Object.freeze([
  "box", "sphere", "cylinder", "cone", "plane", "torus",
]);

export function createPrimitive(name) {
  switch (name) {
    case "box": return new BoxGeometry(1, 1, 1);
    case "sphere": return new SphereGeometry(0.5, 24, 16);
    case "cylinder": return new CylinderGeometry(0.5, 0.5, 1, 24);
    case "cone": return new ConeGeometry(0.5, 1, 24);
    case "plane": return new PlaneGeometry(1, 1);
    case "torus": return new TorusGeometry(0.35, 0.15, 12, 32);
    default: throw new RangeError("Unknown Scene primitive");
  }
}
