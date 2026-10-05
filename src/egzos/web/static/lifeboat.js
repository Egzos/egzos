// Copyright 2026 Ali Sasanian
// SPDX-License-Identifier: Apache-2.0
// The acts region is aria-busy while its request is in flight (lifeboat.md R9, the tap spec R9).
// htmx marks and disables; this adds the one attribute it does not. No other script runs here.
document.addEventListener("htmx:beforeRequest", function (e) {
  var region = e.target.closest("[data-acts]");
  if (region) region.setAttribute("aria-busy", "true");
});
document.addEventListener("htmx:afterRequest", function (e) {
  var region = e.target.closest("[data-acts]");
  if (region) region.removeAttribute("aria-busy");
});
