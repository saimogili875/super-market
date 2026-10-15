/* RDH Cafe — receipt print button (CSP-safe: external, addEventListener).
   Replaces an inline onclick="window.print()" so no 'unsafe-inline' script is
   needed. */
(function () {
  "use strict";
  function bind() {
    var btn = document.getElementById("print-receipt-btn");
    if (!btn) return;
    btn.addEventListener("click", function () {
      window.print();
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
