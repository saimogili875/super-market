/* RDH Cafe — landing UI behaviour (CSP-safe: external, defer, addEventListener).
   Reveal-on-scroll via IntersectionObserver + a cheap rAF-throttled hero
   parallax. No inline handlers, no eval. */
(function () {
  "use strict";

  var reduceMotion =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function initReveal() {
    var els = Array.prototype.slice.call(document.querySelectorAll(".reveal"));
    if (!els.length) return;

    if (reduceMotion || !("IntersectionObserver" in window)) {
      els.forEach(function (el) {
        el.classList.add("active");
      });
      return;
    }

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("active");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
    );

    els.forEach(function (el) {
      observer.observe(el);
    });
  }

  function initParallax() {
    var glow = document.querySelector(".rdh-hero__glow");
    if (!glow || reduceMotion) return;

    var ticking = false;

    function update() {
      var offset = window.pageYOffset || 0;
      glow.style.transform = "translateY(" + offset * 0.25 + "px)";
      ticking = false;
    }

    function onScroll() {
      if (!ticking) {
        window.requestAnimationFrame(update);
        ticking = true;
      }
    }

    window.addEventListener("scroll", onScroll, { passive: true });
    update();
  }

  function init() {
    initReveal();
    initParallax();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
