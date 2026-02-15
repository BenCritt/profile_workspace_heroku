/**
 * gtm-events.js
 * Centralized GTM dataLayer event tracking for bencritt.net
 *
 * HOW IT WORKS
 * ------------
 * This file auto-instruments events by reading data-gtm-* attributes
 * from the DOM. Drop it into base.html once; then annotate each
 * template's interactive elements with the attributes described below.
 *
 * DATA ATTRIBUTES (add these to your templates)
 * -----------------------------------------------
 * data-gtm-tool       – (on <form> or wrapper div) Human-readable tool
 *                        name, e.g. "DNS Lookup Tool"
 * data-gtm-category   – (on <form> or wrapper div) Tool hub/category,
 *                        e.g. "IT Tools"
 * data-gtm-download   – (on <a> or <button>) Marks a download action.
 *                        Value = file type: "csv", "pdf", "zip", "qr", etc.
 * data-gtm-external   – (on <a>) Marks an outbound link click.
 *                        Value = human-readable label, e.g. "Resume"
 * data-gtm-print      – (on <button>) Marks a print action.
 *                        Value = label, e.g. "Kiln Schedule"
 *
 * EVENTS PUSHED TO dataLayer
 * ---------------------------
 * 1. tool_form_submit   – User submits a tool form
 *    { event, tool_name, tool_category }
 *
 * 2. file_download      – User clicks a download button/link
 *    { event, tool_name, tool_category, file_type }
 *
 * 3. outbound_link_click – User clicks an external link
 *    { event, link_label, link_url }
 *
 * 4. print_action       – User clicks a print button
 *    { event, print_label }
 *
 * 5. hub_tool_click     – User clicks through from a hub page to a tool
 *    { event, hub_name, tool_destination }
 *
 * GTM SETUP NOTES
 * ----------------
 * In GTM, create a "Custom Event" trigger for each event name above,
 * then a GA4 Event tag that fires on that trigger. Use Data Layer
 * Variables to capture tool_name, tool_category, file_type, etc.
 * as GA4 event parameters.
 */

(function () {
  "use strict";

  // Safety check: bail if dataLayer is somehow missing.
  window.dataLayer = window.dataLayer || [];

  // ─── Utility ───────────────────────────────────────────────
  function pushEvent(eventName, params) {
    var payload = { event: eventName };
    for (var key in params) {
      if (params.hasOwnProperty(key)) {
        payload[key] = params[key];
      }
    }
    window.dataLayer.push(payload);
  }

  // Walk up from an element to find the closest ancestor (or self)
  // that has the given data attribute.  Returns the attribute value
  // or null.
  function closestData(el, attr) {
    var node = el;
    while (node && node !== document) {
      if (node.hasAttribute && node.hasAttribute(attr)) {
        return node.getAttribute(attr);
      }
      node = node.parentElement;
    }
    return null;
  }

  // ─── 1. FORM SUBMISSIONS ──────────────────────────────────
  // Listens for the native "submit" event on any <form> that has
  // data-gtm-tool.  Works for both standard POST forms AND JS-
  // intercepted forms (the dataLayer push fires before
  // preventDefault, so GTM still captures it).
  document.addEventListener(
    "submit",
    function (e) {
      var form = e.target;
      if (!form || form.tagName !== "FORM") return;

      var toolName = form.getAttribute("data-gtm-tool");
      if (!toolName) return;

      var category = form.getAttribute("data-gtm-category") || "";

      pushEvent("tool_form_submit", {
        tool_name: toolName,
        tool_category: category,
      });
    },
    true // capture phase so we fire even if the handler calls preventDefault
  );

  // ─── 2. CLICK-BASED EVENTS ────────────────────────────────
  // Single delegated listener on document for downloads, external
  // links, print actions, and hub navigation.
  document.addEventListener("click", function (e) {
    var target = e.target;

    // Resolve clicks on child elements (e.g. <i> inside <a>)
    var anchor = target.closest ? target.closest("a, button") : target;
    if (!anchor) return;

    // ── 2a. Download clicks ──────────────────────────────────
    var fileType = anchor.getAttribute("data-gtm-download");
    if (fileType) {
      pushEvent("file_download", {
        tool_name: closestData(anchor, "data-gtm-tool") || "",
        tool_category: closestData(anchor, "data-gtm-category") || "",
        file_type: fileType,
      });
      return;
    }

    // ── 2b. External / outbound link clicks ──────────────────
    var extLabel = anchor.getAttribute("data-gtm-external");
    if (extLabel) {
      pushEvent("outbound_link_click", {
        link_label: extLabel,
        link_url: anchor.href || "",
      });
      return;
    }

    // ── 2c. Print actions ────────────────────────────────────
    var printLabel = anchor.getAttribute("data-gtm-print");
    if (printLabel) {
      pushEvent("print_action", {
        print_label: printLabel,
      });
      return;
    }

    // ── 2d. Hub → tool navigation clicks ─────────────────────
    var hubTool = anchor.getAttribute("data-gtm-hub-tool");
    if (hubTool) {
      pushEvent("hub_tool_click", {
        hub_name: closestData(anchor, "data-gtm-hub") || "",
        tool_destination: hubTool,
      });
      return;
    }
  });

  // ─── 3. ASYNC TOOL HELPERS ─────────────────────────────────
  // Expose global helpers that async tools (SEO Head Checker,
  // Font Inspector, Cookie Audit) can call directly from their
  // inline scripts.
  //
  // Usage in template JS:
  //   window.gtmTrack.scanStart("SEO Head Checker", "SEO Tools");
  //   window.gtmTrack.scanComplete("SEO Head Checker", "SEO Tools");
  //   window.gtmTrack.reportDownload("SEO Head Checker", "SEO Tools", "csv");

  window.gtmTrack = {
    scanStart: function (toolName, category) {
      pushEvent("scan_start", {
        tool_name: toolName,
        tool_category: category || "",
      });
    },
    scanComplete: function (toolName, category) {
      pushEvent("scan_complete", {
        tool_name: toolName,
        tool_category: category || "",
      });
    },
    reportDownload: function (toolName, category, fileType) {
      pushEvent("file_download", {
        tool_name: toolName,
        tool_category: category || "",
        file_type: fileType || "csv",
      });
    },
  };
})();
