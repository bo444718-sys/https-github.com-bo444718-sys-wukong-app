const WUKONG_SHELL_VERSION = new URL(document.currentScript?.src || window.location.href).searchParams.get("v") || "122";

if (window.location.protocol !== "file:" && "serviceWorker" in navigator) {
  navigator.serviceWorker.register(`./sw.js?v=${WUKONG_SHELL_VERSION}`);
}
