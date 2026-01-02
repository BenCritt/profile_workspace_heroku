(() => {
      const inIframe = (window.self !== window.top);

      // Mark iframe state ASAP (prevents flicker; also usable for CSS hooks if you want later)
      if (inIframe) {
        document.documentElement.classList.add("embedded");
      }

      function resizeIframe(iframe) {
        try {
          iframe.style.height = iframe.contentWindow.document.body.scrollHeight + "px";
        } catch (e) {
          // ignore cross-origin or access issues
        }
      }

      function onReady(fn) {
        if (document.readyState !== "loading") fn();
        else document.addEventListener("DOMContentLoaded", fn);
      }

      onReady(() => {
        // Parent pages: auto-resize ONLY non-tool iframes
        // (tool iframes use fixed height + internal scrolling)
        if (!inIframe) {
          document.querySelectorAll("iframe:not(.tool-iframe)").forEach((iframe) => {
            iframe.addEventListener("load", () => resizeIframe(iframe));
          });
          return;
        }

        // Embedded pages (inside an iframe): hide site chrome + remove extra blocks
        document.body.classList.add("in-iframe");
        // The hiding of the navbar and footer is now done via CSS.
        // I'm keeping this code here commented out in case I want to revert back to JS-based hiding later.
        /*
        const navbar = document.querySelector("nav");
        if (navbar) navbar.style.display = "none";

        const footer = document.querySelector("footer");
        if (footer) footer.style.cssText = "display: none !important;";
        */
        document.querySelectorAll(".btn.btn-secondary").forEach((btn) => {
          btn.style.display = "none";
        });

        // Remove the repo icon link (the app source link) + its adjacent <br> if present
        document
          .querySelectorAll('a[href*="github.com/BenCritt/profile_workspace_heroku"]')
          .forEach((a) => {
            const next = a.nextElementSibling;
            if (next && next.tagName === "BR") next.remove();
            a.remove();
          });
          
        // Remove the attribution paragraph (and its container if present)
        document.querySelectorAll("p").forEach((p) => {
          if ((p.textContent || "").includes("This tool was created by")) {
            const container = p.closest(".container");
            (container || p).remove();
          }
        });
      });
    })();