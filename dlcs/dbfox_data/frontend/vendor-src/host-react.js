// Bind third-party hooks to the existing public Host SDK. No second React copy.
const React = window.__DBFOX_EXTENSION_HOST__?.React;
if (!React) throw new Error("DBFox frontend React SDK is unavailable");
export default React;
export const { useContext, useRef, useState, useMemo, useCallback, useEffect, useLayoutEffect, useImperativeHandle } = React;
