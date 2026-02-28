/**
 * iframe-handler.js
 * =================
 * Loaded via <script defer> in base.html on EVERY page of the site.
 * Handles two distinct runtime contexts:
 *
 *   1. PARENT PAGE (hub toolkit pages):
 *      freight_tools.html, glass_artist_toolkit.html, it_tools.html, etc.
 *      These pages contain two sets of cards (toggled by CSS breakpoint):
 *        - .non-iframe-cards  → plain links, shown on mobile (< 768px)
 *        - .iframe-cards      → tool pages embedded in <iframe> elements, shown on desktop (≥ 768px)
 *      This script keeps the embedded iframes sized to their content height.
 *
 *   2. EMBEDDED PAGE (individual tool pages loaded inside an iframe):
 *      cron_builder.html, deadhead_calculator.html, glass_volume_calculator.html, etc.
 *      When a tool page is the src of a hub-page iframe, this script strips
 *      elements that are redundant or distracting inside the iframe context
 *      (repo link, attribution paragraph). Site chrome (navbar, footer, secondary
 *      buttons) is hidden by CSS, not JS — see base.css for those rules.
 *
 * HOW THE EMBEDDED STATE IS DETECTED
 * ------------------------------------
 * base.html contains a synchronous inline script that runs before any CSS is
 * fetched or applied:
 *
 *     <script>if(window.self!==window.top)document.documentElement.classList.add('embedded');</script>
 *
 * This means by the time this deferred script executes, the 'embedded' class is
 * already present on <html> if the page is in an iframe. We read that class here
 * rather than re-checking window.self !== window.top, so both the inline script
 * and this file share a single source of truth.
 *
 * The CSS in base.css uses html.embedded selectors to hide the navbar, footer,
 * secondary buttons, related-tools sections, and body/main padding — all without
 * JavaScript, and with no flash of those elements.
 *
 * RESIZE STRATEGY
 * ----------------
 * Two complementary mechanisms keep iframes sized to their content:
 *
 *   A) Load-based (direct DOM access):
 *      On the hub parent page, after each iframe's 'load' event fires, we read
 *      iframe.contentWindow.document.body.scrollHeight and set the iframe height.
 *      This works for same-origin iframes and gives a correct initial height.
 *      Iframes with class="tool-iframe" are excluded from this mechanism (reserved
 *      for any future iframes that manage their own fixed height).
 *
 *   B) postMessage listener:
 *      Tool pages that resize dynamically after load (e.g., after a form submit
 *      that reveals a large results section) post a message to the parent:
 *          window.parent.postMessage({ type: 'setHeight', height: <px> }, '*');
 *      This listener receives that message and updates the matching iframe's height.
 *      The match is made by comparing iframe.contentWindow to e.source.
 *      Both mechanisms are registered on the parent page; they are not redundant —
 *      (A) handles initial load, (B) handles subsequent dynamic growth.
 */

(() => {
    // Read the embedded flag from the class set synchronously by base.html's inline
    // script. Do NOT re-derive from window.self !== window.top here — the inline
    // script is the canonical source of truth, and deriving it twice is redundant.
    const inIframe = document.documentElement.classList.contains("embedded");

    /**
     * Resize a same-origin iframe to fit its content height.
     * Wrapped in try/catch because cross-origin iframes will throw a SecurityError
     * on contentWindow access. All tool iframes on this site are same-origin, but
     * this guard prevents a hard failure if that ever changes.
     */
    function resizeIframe(iframe) {
        try {
            iframe.style.height = iframe.contentWindow.document.body.scrollHeight + "px";
        } catch (e) {
            // Cross-origin or access error — silently skip.
        }
    }

    /**
     * Run fn immediately if the DOM is already parsed, or defer until
     * DOMContentLoaded. Because this script is loaded with defer, the DOM is
     * almost always ready by the time this runs — but the guard is cheap insurance.
     */
    function onReady(fn) {
        if (document.readyState !== "loading") fn();
        else document.addEventListener("DOMContentLoaded", fn);
    }

    onReady(() => {

        // ── PARENT PAGE BEHAVIOUR ────────────────────────────────────────────────
        // Runs on hub pages (freight_tools, glass_artist_toolkit, it_tools, etc.)
        // that embed tool pages in iframes inside .iframe-card-wrapper elements.
        // These pages are NOT inside an iframe themselves.

        if (!inIframe) {

            // A) Load-based resize
            // After each iframe's initial page load completes, measure its content
            // height and apply it. This gives the correct initial height.
            // Excludes any iframe with class="tool-iframe" (reserved for future
            // iframes that control their own fixed height).
            document.querySelectorAll("iframe:not(.tool-iframe)").forEach((iframe) => {
                iframe.addEventListener("load", () => resizeIframe(iframe));
            });

            // B) postMessage resize listener
            // Tool pages post { type: 'setHeight', height: <px> } to window.parent
            // whenever their content height changes after initial load — typically
            // after a form submission that renders a results section, or after
            // a JavaScript-driven UI update expands the page.
            //
            // We identify which iframe sent the message by comparing
            // iframe.contentWindow to e.source (the window that posted the message).
            // We loop because querySelectorAll returns a NodeList, not an array,
            // and we need to break as soon as we find the match.
            window.addEventListener("message", function (e) {
                if (e.data && e.data.type === "setHeight" && e.data.height) {
                    var iframes = document.querySelectorAll("iframe");
                    for (var i = 0; i < iframes.length; i++) {
                        if (iframes[i].contentWindow === e.source) {
                            iframes[i].style.height = e.data.height + "px";
                            break;
                        }
                    }
                }
            });

            return; // Nothing below applies to parent pages.
        }

        // ── EMBEDDED PAGE BEHAVIOUR ──────────────────────────────────────────────
        // Runs on tool pages when they are loaded as the src of a hub-page iframe.
        // By this point, html.embedded is already set, so base.css has already
        // hidden the navbar, footer, secondary ("Go to [toolkit]") buttons,
        // related-tools blocks, and removed body/main padding. No JS is needed
        // for any of that — this block handles DOM node removal only.

        // Remove the GitHub repo icon link (the "view source" icon link present
        // in the attribution area of tool pages). Also removes the <br> that
        // immediately follows it, if present, to avoid a stray line break.
        document
            .querySelectorAll('a[href*="github.com/BenCritt/profile_workspace_heroku"]')
            .forEach((a) => {
                const next = a.nextElementSibling;
                if (next && next.tagName === "BR") next.remove();
                a.remove();
            });

        // Remove the "This tool was created by Ben Crittenden" attribution paragraph.
        // If it lives inside a .container wrapper, remove the whole container so no
        // empty box or padding remains. Otherwise remove the <p> directly.
        document.querySelectorAll("p").forEach((p) => {
            if ((p.textContent || "").includes("This tool was created by")) {
                const container = p.closest(".container");
                (container || p).remove();
            }
        });

    });
})();