export const RETRY_INTERVAL = 60 * 1000;
export const DOMAIN = window.location.href.split("/")[2];
export const ROOT_URL = `${window.location.protocol}//${DOMAIN}`;
export const MAX_CONCURRENT_CHECKS = 16;

export const IS_DARK_MODE = window.matchMedia("(prefers-color-scheme: dark)")
  .matches;

export const PLOT_COLORS = {
  MARKERS_FAILURE: "#fa4654",
  FILL_SCALAR: "#ffb70030",
  LINE_SCALAR: "#ffb700",
  AXIS: IS_DARK_MODE ? "#afbdd1" : "#444",
  GRID: IS_DARK_MODE ? "#484f59" : "#eee",
};
