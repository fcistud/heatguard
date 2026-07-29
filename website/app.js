/* HeatGuard docs — theme toggle + mobile nav. No dependencies. */
(function () {
  "use strict";

  var STORAGE_KEY = "heatguard-theme";

  function getStored() {
    try { return localStorage.getItem(STORAGE_KEY); } catch (e) { return null; }
  }
  function setStored(v) {
    try { localStorage.setItem(STORAGE_KEY, v); } catch (e) { /* ignore */ }
  }

  // Resolve the initial theme: stored choice wins; otherwise respect the OS
  // preference on first load; default to dark.
  function resolveInitial() {
    var stored = getStored();
    if (stored === "light" || stored === "dark") return stored;
    if (window.matchMedia &&
        window.matchMedia("(prefers-color-scheme: light)").matches) {
      return "light";
    }
    return "dark";
  }

  function apply(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    var labels = document.querySelectorAll("[data-theme-label]");
    var icons = document.querySelectorAll("[data-theme-icon]");
    var next = theme === "dark" ? "light" : "dark";
    for (var i = 0; i < labels.length; i++) {
      labels[i].textContent = next.charAt(0).toUpperCase() + next.slice(1) + " mode";
    }
    for (var j = 0; j < icons.length; j++) {
      icons[j].textContent = theme === "dark" ? "☀️" : "🌙";
    }
  }

  // Apply ASAP (this script is loaded in <head> with defer-like placement via
  // being before paint where possible). Set the attribute immediately.
  apply(resolveInitial());

  function toggle() {
    var current = document.documentElement.getAttribute("data-theme") || "dark";
    var next = current === "dark" ? "light" : "dark";
    setStored(next);
    apply(next);
  }

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  ready(function () {
    // re-apply so the toggle labels are populated once the DOM exists
    apply(document.documentElement.getAttribute("data-theme") || resolveInitial());

    var toggles = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < toggles.length; i++) {
      toggles[i].addEventListener("click", toggle);
    }

    // Mobile nav
    var sidebar = document.querySelector(".sidebar");
    var scrim = document.querySelector(".scrim");
    var menuBtn = document.querySelector("[data-menu-toggle]");

    function openNav() {
      if (sidebar) sidebar.classList.add("open");
      if (scrim) scrim.classList.add("show");
    }
    function closeNav() {
      if (sidebar) sidebar.classList.remove("open");
      if (scrim) scrim.classList.remove("show");
    }

    if (menuBtn) menuBtn.addEventListener("click", function () {
      if (sidebar && sidebar.classList.contains("open")) closeNav();
      else openNav();
    });
    if (scrim) scrim.addEventListener("click", closeNav);

    // Close the drawer when a nav link is tapped (mobile)
    var navLinks = document.querySelectorAll(".sidebar .nav a");
    for (var k = 0; k < navLinks.length; k++) {
      navLinks[k].addEventListener("click", closeNav);
    }

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeNav();
    });
  });

  // Keep tabs in sync with OS theme changes only when the user hasn't chosen.
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: light)");
    var handler = function () {
      if (!getStored()) apply(resolveInitial());
    };
    if (mq.addEventListener) mq.addEventListener("change", handler);
    else if (mq.addListener) mq.addListener(handler);
  }
})();
