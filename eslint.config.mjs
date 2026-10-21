// Contrôle statique du front (sans build) : variables non définies et redéclarations. Lancé par scripts/lint-js.sh sur i18n.js + app.js + stats.js concaténés,
// car ces trois fichiers partagent la même portée globale (balises <script> classiques).
const browser = [
  "window", "document", "navigator", "location", "history", "localStorage", "sessionStorage", "console", "fetch", "Request", "Response", "Headers", "URL", "URLSearchParams",
  "FormData", "Blob", "File", "FileReader", "Image", "Event", "CustomEvent", "KeyboardEvent", "MouseEvent", "AbortController", "AbortSignal", "TextEncoder", "TextDecoder",
  "setTimeout", "clearTimeout", "setInterval", "clearInterval", "requestAnimationFrame", "cancelAnimationFrame", "queueMicrotask", "structuredClone", "matchMedia",
  "getComputedStyle", "alert", "confirm", "prompt", "atob", "btoa", "crypto", "caches", "indexedDB", "Notification", "PushManager", "BarcodeDetector", "createImageBitmap",
  "ResizeObserver", "IntersectionObserver", "MutationObserver", "Intl", "performance", "screen", "innerWidth", "innerHeight", "scrollTo", "addEventListener",
  "removeEventListener", "dispatchEvent", "HTMLElement", "Element", "Node", "SVGElement", "DOMParser", "XMLSerializer", "OffscreenCanvas", "ImageData", "Audio",
  "MediaQueryListEvent", "IDBKeyRange", "WebSocket", "Worker", "ServiceWorkerRegistration", "self", "globalThis",
];
const tolerated = ["I18N", "module", "t"];  // I18N et t() sont posés par i18n.js sur `root` ; `module` sert au test Node de i18n.js
const readonly = Object.fromEntries([...browser, ...tolerated].map((n) => [n, "readonly"]));

export default [{
  files: ["**/*.js"],
  languageOptions: { ecmaVersion: 2023, sourceType: "script", globals: readonly },
  linterOptions: { reportUnusedDisableDirectives: false },
  rules: {
    "no-undef": "error",
    "no-redeclare": "error",       // deux `function f` de même nom dans deux fichiers : le dernier écrase le premier (bug réel de weekCard)
    "no-const-assign": "error",
    "no-dupe-keys": "error",
    "no-dupe-args": "error",
    "no-func-assign": "error",
    "no-import-assign": "error",
    "no-unreachable": "error",
  },
}];
