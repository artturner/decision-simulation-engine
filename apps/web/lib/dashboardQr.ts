/**
 * The student dashboard's public URL and a QR code for it, for printed
 * handouts. The URL is the same for every student (the access code is what
 * identifies them), so the QR is generated once — the identical SVG is at
 * public/qr-me.svg for the Python print tooling (tools/unit-reports).
 * Regenerate both together if the URL ever changes.
 */

export const DASHBOARD_URL = "https://scenarios.cruxlabs.academy/me";
export const DASHBOARD_URL_SHORT = "scenarios.cruxlabs.academy/me";

export const DASHBOARD_QR_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 33 33" class="segno"><path class="qrline" stroke="#000" d="M2 2.5h7m1 0h5m3 0h5m1 0h7m-29 1h1m5 0h1m1 0h1m1 0h1m5 0h3m1 0h1m1 0h1m5 0h1m-29 1h1m1 0h3m1 0h1m2 0h6m4 0h1m2 0h1m1 0h3m1 0h1m-29 1h1m1 0h3m1 0h1m1 0h5m4 0h1m1 0h2m1 0h1m1 0h3m1 0h1m-29 1h1m1 0h3m1 0h1m3 0h1m3 0h4m1 0h1m2 0h1m1 0h3m1 0h1m-29 1h1m5 0h1m2 0h1m3 0h1m5 0h2m1 0h1m5 0h1m-29 1h7m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h7m-21 1h1m1 0h1m3 0h5m-19 1h1m1 0h2m1 0h3m1 0h1m1 0h1m1 0h1m1 0h6m1 0h1m2 0h1m1 0h2m-29 1h2m3 0h1m2 0h4m1 0h1m4 0h7m3 0h1m-27 1h1m3 0h1m1 0h2m1 0h3m2 0h1m3 0h1m2 0h2m1 0h2m-28 1h2m3 0h1m1 0h5m4 0h1m4 0h4m3 0h1m-29 1h1m5 0h1m2 0h2m3 0h1m1 0h2m2 0h1m4 0h2m-27 1h1m1 0h3m2 0h2m3 0h1m1 0h6m1 0h2m3 0h3m-29 1h3m2 0h3m1 0h2m1 0h2m3 0h1m1 0h2m1 0h2m2 0h3m-28 1h1m1 0h1m6 0h1m3 0h3m2 0h1m1 0h4m2 0h1m-28 1h3m1 0h3m1 0h2m1 0h1m2 0h2m4 0h2m1 0h3m1 0h1m-27 1h1m3 0h1m3 0h1m4 0h2m1 0h1m2 0h1m2 0h1m1 0h3m-28 1h1m1 0h1m1 0h1m1 0h2m2 0h1m2 0h5m3 0h3m2 0h1m-23 1h1m3 0h2m2 0h3m1 0h2m1 0h1m1 0h1m1 0h1m2 0h1m-26 1h2m2 0h5m1 0h4m1 0h3m1 0h7m-19 1h1m2 0h1m4 0h1m1 0h1m1 0h1m3 0h5m-29 1h7m1 0h2m4 0h1m2 0h1m1 0h2m1 0h1m1 0h2m1 0h1m-28 1h1m5 0h1m1 0h2m2 0h3m3 0h3m3 0h2m1 0h2m-29 1h1m1 0h3m1 0h1m4 0h2m2 0h1m1 0h1m2 0h5m1 0h1m-27 1h1m1 0h3m1 0h1m1 0h4m3 0h3m1 0h1m1 0h1m1 0h3m2 0h1m-29 1h1m1 0h3m1 0h1m1 0h2m1 0h2m4 0h1m1 0h1m3 0h1m2 0h1m1 0h1m-29 1h1m5 0h1m3 0h3m2 0h1m3 0h2m1 0h2m1 0h1m1 0h1m-28 1h7m1 0h1m1 0h2m2 0h1m3 0h6m1 0h1m1 0h1"/></svg>`;
