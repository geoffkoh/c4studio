// The site's behaviour: theme toggle, mobile navigation, copy buttons,
// search and the "On this page" highlight. No framework, no build step.
(function () {
  "use strict";

  var root = document.documentElement;

  // --- Theme ---------------------------------------------------------------
  function currentTheme() {
    var set = root.getAttribute("data-theme");
    if (set) return set;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
    button.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try {
        localStorage.setItem("c4studio-theme", next);
      } catch (e) {}
    });
  });

  // --- Mobile navigation ---------------------------------------------------
  var menu = document.querySelector(".menu-btn");
  function setNav(open) {
    document.body.classList.toggle("nav-open", open);
    if (menu) menu.setAttribute("aria-expanded", open ? "true" : "false");
  }
  if (menu) {
    menu.addEventListener("click", function () {
      setNav(!document.body.classList.contains("nav-open"));
    });
  }
  document.querySelectorAll("[data-close-nav], .sidebar a").forEach(function (el) {
    el.addEventListener("click", function () {
      setNav(false);
    });
  });

  // --- Copy buttons --------------------------------------------------------
  function copy(text, button) {
    function done() {
      var label = button.textContent;
      button.textContent = "Copied";
      button.classList.add("copied");
      setTimeout(function () {
        button.textContent = label;
        button.classList.remove("copied");
      }, 1400);
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () {});
    } else {
      var area = document.createElement("textarea");
      area.value = text;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      try {
        document.execCommand("copy");
        done();
      } catch (e) {}
      area.remove();
    }
  }
  document.querySelectorAll(".code").forEach(function (block) {
    var pre = block.querySelector("pre");
    if (!pre) return;
    var button = document.createElement("button");
    button.type = "button";
    button.className = "copy";
    button.textContent = "Copy";
    button.setAttribute("aria-label", "Copy code");
    button.addEventListener("click", function () {
      copy(pre.innerText.replace(/\n$/, ""), button);
    });
    block.appendChild(button);
  });
  document.querySelectorAll("[data-copy]").forEach(function (button) {
    button.addEventListener("click", function () {
      copy(button.getAttribute("data-copy"), button);
    });
  });

  // --- Search --------------------------------------------------------------
  var dialog = document.querySelector(".search");
  var input = dialog && dialog.querySelector("input");
  var list = dialog && dialog.querySelector(".search-results");
  var active = 0;
  var hits = [];

  function escapeHtml(text) {
    return text.replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function score(entry, terms) {
    var heading = entry.h.toLowerCase();
    var page = entry.p.toLowerCase();
    var body = entry.x.toLowerCase();
    var total = 0;
    for (var i = 0; i < terms.length; i++) {
      var t = terms[i];
      if (heading.indexOf(t) === 0) total += 12;
      else if (heading.indexOf(t) >= 0) total += 8;
      else if (page.indexOf(t) >= 0) total += 3;
      else if (body.indexOf(t) >= 0) total += 1;
      else return 0;
    }
    return total;
  }
  function render() {
    var query = input.value.trim().toLowerCase();
    var index = window.C4_SEARCH || [];
    if (!query) {
      hits = index.filter(function (e) {
        return e.u.indexOf("#") < 0;
      });
    } else {
      var terms = query.split(/\s+/);
      hits = index
        .map(function (e) {
          return { e: e, s: score(e, terms) };
        })
        .filter(function (r) {
          return r.s > 0;
        })
        .sort(function (a, b) {
          return b.s - a.s;
        })
        .slice(0, 12)
        .map(function (r) {
          return r.e;
        });
    }
    active = 0;
    if (!hits.length) {
      list.innerHTML = '<li class="search-empty">No matches. Try a keyword such as <code>autolayout</code>.</li>';
      return;
    }
    list.innerHTML = hits
      .map(function (e, i) {
        return (
          '<li role="option"' + (i === 0 ? ' aria-selected="true"' : "") + ">" +
          '<a href="' + e.u + '"><span class="sr-page">' + escapeHtml(e.p) + "</span>" +
          '<span class="sr-head">' + escapeHtml(e.h) + "</span>" +
          '<span class="sr-text">' + escapeHtml(e.x.slice(0, 140)) + "</span></a></li>"
        );
      })
      .join("");
  }
  function move(delta) {
    var items = list.querySelectorAll("li[role=option]");
    if (!items.length) return;
    items[active].removeAttribute("aria-selected");
    active = (active + delta + items.length) % items.length;
    items[active].setAttribute("aria-selected", "true");
    items[active].scrollIntoView({ block: "nearest" });
  }
  function openSearch() {
    if (!dialog) return;
    dialog.hidden = false;
    document.body.classList.add("search-open");
    input.value = "";
    render();
    input.focus();
  }
  function closeSearch() {
    if (!dialog) return;
    dialog.hidden = true;
    document.body.classList.remove("search-open");
  }
  if (dialog) {
    document.querySelectorAll("[data-search-open]").forEach(function (b) {
      b.addEventListener("click", openSearch);
    });
    input.addEventListener("input", render);
    input.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        move(1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        move(-1);
      } else if (event.key === "Enter") {
        var link = list.querySelectorAll("li[role=option] a")[active];
        if (link) window.location.href = link.getAttribute("href");
      }
    });
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) closeSearch();
    });
    document.addEventListener("keydown", function (event) {
      var typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
      if (event.key === "Escape") {
        closeSearch();
        setNav(false);
      } else if (
        (event.key === "/" && !typing) ||
        ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k")
      ) {
        event.preventDefault();
        openSearch();
      }
    });
  }

  // --- "On this page" follows the scroll ----------------------------------
  var tocLinks = document.querySelectorAll(".toc a");
  if (tocLinks.length && "IntersectionObserver" in window) {
    var byId = {};
    tocLinks.forEach(function (a) {
      byId[a.getAttribute("href").slice(1)] = a;
    });
    var visible = {};
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          visible[entry.target.id] = entry.isIntersecting;
        });
        var headings = document.querySelectorAll(".prose h2[id], .prose h3[id]");
        var current = null;
        for (var i = 0; i < headings.length; i++) {
          if (visible[headings[i].id]) {
            current = headings[i].id;
            break;
          }
        }
        if (!current) return;
        tocLinks.forEach(function (a) {
          a.classList.remove("active");
        });
        if (byId[current]) byId[current].classList.add("active");
      },
      { rootMargin: "-64px 0px -60% 0px" }
    );
    document.querySelectorAll(".prose h2[id], .prose h3[id]").forEach(function (h) {
      observer.observe(h);
    });
  }
})();
