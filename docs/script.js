/* ================= SYNAPSE site interactions — modern redesign ================= */
(function () {
  "use strict";

  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- Nav: scrolled state + mobile toggle ---------- */
  const nav = document.getElementById("nav");
  const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > 30);
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  const menuToggle = document.getElementById("menu-toggle");
  if (menuToggle) {
    menuToggle.addEventListener("click", () => nav.classList.toggle("open"));
    nav.querySelectorAll(".nav-links a").forEach((a) =>
      a.addEventListener("click", () => nav.classList.remove("open"))
    );
  }

  /* ---------- Theme toggle (persisted, system-aware) ---------- */
  const root = document.documentElement;
  const themeToggle = document.getElementById("theme-toggle");
  const graphColors = () =>
    root.getAttribute("data-theme") === "light"
      ? { cyan: "10,158,147", violet: "106,79,224" }
      : { cyan: "63,240,230", violet: "147,123,255" };
  function applyThemeLabel() {
    const isLight = root.getAttribute("data-theme") === "light";
    if (themeToggle)
      themeToggle.setAttribute(
        "aria-label",
        isLight ? "Switch to dark theme" : "Switch to light theme"
      );
  }
  applyThemeLabel();
  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      const next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
      root.setAttribute("data-theme", next);
      try {
        localStorage.setItem("synapse-theme", next);
      } catch (e) {}
      applyThemeLabel();
      COL = graphColors();
    });
  }

  /* ---------- Scroll progress bar ---------- */
  const progress = document.getElementById("scroll-progress");
  function updateProgress() {
    const h = document.documentElement;
    const scrolled = h.scrollTop / (h.scrollHeight - h.clientHeight);
    if (progress) progress.style.width = Math.max(0, Math.min(1, scrolled)) * 100 + "%";
  }
  window.addEventListener("scroll", updateProgress, { passive: true });
  updateProgress();

  /* ---------- Back to top ---------- */
  const toTop = document.getElementById("to-top");
  if (toTop) {
    window.addEventListener(
      "scroll",
      () => toTop.classList.toggle("show", window.scrollY > 640),
      { passive: true }
    );
    toTop.addEventListener("click", () =>
      window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" })
    );
  }

  /* ---------- Active nav link on scroll (scroll spy) ---------- */
  const navLinks = Array.from(document.querySelectorAll(".nav-links a"));
  const spyTargets = navLinks
    .map((a) => {
      const id = a.getAttribute("href");
      return id && id.startsWith("#") ? { a, el: document.querySelector(id) } : null;
    })
    .filter((x) => x && x.el);
  if (spyTargets.length) {
    const spy = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            const match = spyTargets.find((t) => t.el === e.target);
            if (match) {
              navLinks.forEach((l) => l.classList.remove("active"));
              match.a.classList.add("active");
            }
          }
        });
      },
      { rootMargin: "-45% 0px -50% 0px" }
    );
    spyTargets.forEach((t) => spy.observe(t.el));
  }

  /* ---------- Reveal on scroll (with stagger) ---------- */
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          e.target.classList.add("in");
          io.unobserve(e.target);
        }
      });
    },
    { threshold: 0.12 }
  );
  document.querySelectorAll(".reveal").forEach((el, i) => {
    // stagger siblings inside the same grid for a nicer cascade
    const parent = el.parentElement;
    if (parent && /grid|gallery|verbs/.test(parent.className)) {
      const idx = Array.prototype.indexOf.call(parent.children, el);
      el.setAttribute("data-delay", String(Math.min(idx, 3)));
    }
    io.observe(el);
  });

  /* ---------- Animated counters ---------- */
  const easeOut = (t) => 1 - Math.pow(1 - t, 3);
  function runCounter(el) {
    const target = parseFloat(el.dataset.target);
    const suffix = el.dataset.suffix || "";
    const dur = 1500;
    const start = performance.now();
    function frame(now) {
      const p = Math.min((now - start) / dur, 1);
      const val = Math.floor(easeOut(p) * target);
      el.innerHTML = val.toLocaleString() + suffix;
      if (p < 1) requestAnimationFrame(frame);
      else el.innerHTML = target.toLocaleString() + suffix;
    }
    requestAnimationFrame(frame);
  }
  const counterIO = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          runCounter(e.target);
          counterIO.unobserve(e.target);
        }
      });
    },
    { threshold: 0.6 }
  );
  document.querySelectorAll(".count").forEach((el) => counterIO.observe(el));

  /* ---------- Code tabs (with keyboard support) ---------- */
  const tabs = Array.from(document.querySelectorAll(".tab"));
  function activateTab(tab) {
    const id = tab.dataset.tab;
    tabs.forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    const panel = document.getElementById(id);
    if (panel) panel.classList.add("active");
  }
  tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => activateTab(tab));
    tab.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight") activateTab(tabs[(i + 1) % tabs.length]);
      if (e.key === "ArrowLeft") activateTab(tabs[(i - 1 + tabs.length) % tabs.length]);
    });
  });

  /* ---------- Lightbox ---------- */
  const lightbox = document.getElementById("lightbox");
  const lightboxImg = document.getElementById("lightbox-img");
  document.querySelectorAll(".fig-card").forEach((fig) => {
    fig.addEventListener("click", () => {
      lightboxImg.src = fig.dataset.full;
      lightbox.classList.add("open");
    });
  });
  if (lightbox) {
    lightbox.addEventListener("click", () => lightbox.classList.remove("open"));
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") lightbox.classList.remove("open");
    });
  }

  /* ---------- Copy BibTeX ---------- */
  document.querySelectorAll(".copy-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = document.getElementById(btn.dataset.copy);
      const text = target ? target.innerText : "";
      navigator.clipboard.writeText(text).then(() => {
        const orig = btn.textContent;
        btn.textContent = "Copied!";
        setTimeout(() => (btn.textContent = orig), 1600);
      });
    });
  });

  /* ---------- Interactive scale explorer ---------- */
  const slider = document.getElementById("scale-slider");
  if (slider) {
    // T scale points (log): 300 .. 100000
    const scale = [300, 1000, 3000, 10000, 30000, 100000];
    const nf = new Intl.NumberFormat("en-US");
    // model constants derived from the paper's methodology
    const MEAN_LEN = 70.9; // mean tool description tokens
    const BASE = 500; // base prompt tokens
    const SYN_CONST = 971; // SYNAPSE per-turn context is ~constant
    const PRICE = 7.5e-6; // $ per input token (illustrative)
    const WINDOW = 32000; // context window tokens

    const elT = document.getElementById("ex-tval");
    const elSynCtx = document.getElementById("syn-ctx");
    const elSynCost = document.getElementById("syn-cost");
    const elSynBar = document.getElementById("syn-bar");
    const elMcpCtx = document.getElementById("mcp-ctx");
    const elMcpCost = document.getElementById("mcp-cost");
    const elMcpBar = document.getElementById("mcp-bar");
    const elFactor = document.getElementById("ex-factor");

    function fmtCost(c) {
      if (c >= 1) return "$" + c.toFixed(2);
      if (c >= 0.01) return "$" + c.toFixed(3);
      return "$" + c.toFixed(4);
    }

    function update() {
      const T = scale[parseInt(slider.value, 10)];
      const mcpCtx = Math.round(BASE + MEAN_LEN * T);
      const mcpCost = mcpCtx * PRICE;
      const synCost = SYN_CONST * PRICE;
      const factor = Math.round(mcpCtx / SYN_CONST);
      // bars: log-scaled fill so both remain visible
      const maxLog = Math.log10(BASE + MEAN_LEN * 100000);
      const synFill = (Math.log10(SYN_CONST) / maxLog) * 100;
      const mcpFill = (Math.log10(mcpCtx) / maxLog) * 100;
      const overflow = mcpCtx > WINDOW;

      if (elT) elT.textContent = nf.format(T);
      if (elSynCtx) elSynCtx.textContent = nf.format(SYN_CONST) + " tok";
      if (elSynCost) elSynCost.textContent = fmtCost(synCost) + " / task";
      if (elSynBar) elSynBar.style.width = synFill + "%";
      if (elMcpCtx)
        elMcpCtx.textContent = nf.format(mcpCtx) + " tok" + (overflow ? " ⚠" : "");
      if (elMcpCost) elMcpCost.textContent = fmtCost(mcpCost) + " / task";
      if (elMcpBar) elMcpBar.style.width = mcpFill + "%";
      if (elFactor) elFactor.textContent = nf.format(factor) + "×";

      // paint slider progress
      const pct = (slider.value / (scale.length - 1)) * 100;
      slider.style.backgroundSize = pct + "% 100%";
    }
    slider.addEventListener("input", update);
    update();
  }

  /* ---------- 3D tilt + sheen on interactive cards ---------- */
  if (!reduce && window.matchMedia("(pointer: fine)").matches) {
    document.querySelectorAll(".tilt").forEach((card) => {
      let raf = null;
      card.addEventListener("mousemove", (e) => {
        const r = card.getBoundingClientRect();
        const px = (e.clientX - r.left) / r.width;
        const py = (e.clientY - r.top) / r.height;
        card.style.setProperty("--mx", px * 100 + "%");
        card.style.setProperty("--my", py * 100 + "%");
        if (raf) return;
        raf = requestAnimationFrame(() => {
          const rx = (0.5 - py) * 6;
          const ry = (px - 0.5) * 6;
          card.style.transform = `perspective(900px) rotateX(${rx}deg) rotateY(${ry}deg) translateY(-6px)`;
          raf = null;
        });
      });
      card.addEventListener("mouseleave", () => {
        card.style.transform = "";
      });
    });
  }

  /* ---------- KaTeX render ---------- */
  function renderMath() {
    if (typeof katex === "undefined") {
      setTimeout(renderMath, 120);
      return;
    }
    document.querySelectorAll("[data-tex]").forEach((el) => {
      try {
        katex.render(el.dataset.tex, el, {
          throwOnError: false,
          displayMode: el.classList.contains("math-block"),
        });
      } catch (err) {
        el.textContent = el.dataset.tex;
      }
    });
  }
  renderMath();

  /* ---------- Cursor glow (fine pointers only) ---------- */
  const glow = document.getElementById("cursor-glow");
  if (glow && !reduce && window.matchMedia("(pointer: fine)").matches) {
    let gx = window.innerWidth / 2,
      gy = window.innerHeight / 2,
      tx = gx,
      ty = gy;
    window.addEventListener(
      "mousemove",
      (e) => {
        tx = e.clientX;
        ty = e.clientY;
        glow.style.opacity = "1";
      },
      { passive: true }
    );
    window.addEventListener("mouseout", () => (glow.style.opacity = "0"));
    (function follow() {
      gx += (tx - gx) * 0.15;
      gy += (ty - gy) * 0.15;
      glow.style.transform = `translate(${gx}px, ${gy}px)`;
      requestAnimationFrame(follow);
    })();
  }

  /* ---------- Mouse-reactive knowledge-graph background ---------- */
  const canvas = document.getElementById("graph-bg");
  const ctx = canvas.getContext("2d");
  let W, H, nodes, dpr;
  const mouse = { x: -9999, y: -9999 };

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = canvas.width = window.innerWidth * dpr;
    H = canvas.height = window.innerHeight * dpr;
    canvas.style.width = window.innerWidth + "px";
    canvas.style.height = window.innerHeight + "px";
    const count = Math.min(80, Math.floor((window.innerWidth * window.innerHeight) / 20000));
    nodes = Array.from({ length: count }, () => ({
      x: Math.random() * W,
      y: Math.random() * H,
      vx: (Math.random() - 0.5) * 0.22 * dpr,
      vy: (Math.random() - 0.5) * 0.22 * dpr,
      r: (Math.random() * 1.8 + 1.2) * dpr,
      hue: Math.random() < 0.5 ? "cyan" : "violet",
    }));
  }

  window.addEventListener(
    "mousemove",
    (e) => {
      mouse.x = e.clientX * dpr;
      mouse.y = e.clientY * dpr;
    },
    { passive: true }
  );
  window.addEventListener("mouseout", () => {
    mouse.x = mouse.y = -9999;
  });

  let COL = graphColors();
  const LINK = 150;
  const MOUSE_R = 170;

  function draw() {
    ctx.clearRect(0, 0, W, H);
    const linkDist = LINK * dpr;
    const mouseR = MOUSE_R * dpr;

    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      a.x += a.vx;
      a.y += a.vy;
      if (a.x < 0 || a.x > W) a.vx *= -1;
      if (a.y < 0 || a.y > H) a.vy *= -1;

      // gentle attraction toward the cursor
      const mdx = mouse.x - a.x;
      const mdy = mouse.y - a.y;
      const md = Math.hypot(mdx, mdy);
      if (md < mouseR && md > 0.001) {
        const f = (1 - md / mouseR) * 0.35;
        a.x += (mdx / md) * f * dpr;
        a.y += (mdy / md) * f * dpr;
      }

      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        const dx = a.x - b.x,
          dy = a.y - b.y;
        const d = Math.hypot(dx, dy);
        if (d < linkDist) {
          const alpha = (1 - d / linkDist) * 0.4;
          ctx.strokeStyle = `rgba(${COL[a.hue]},${alpha})`;
          ctx.lineWidth = 0.6 * dpr;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }

      // link nodes to the cursor for an interactive feel
      if (md < mouseR) {
        const alpha = (1 - md / mouseR) * 0.5;
        ctx.strokeStyle = `rgba(${COL[a.hue]},${alpha})`;
        ctx.lineWidth = 0.7 * dpr;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(mouse.x, mouse.y);
        ctx.stroke();
      }
    }

    for (const n of nodes) {
      ctx.beginPath();
      ctx.fillStyle = `rgba(${COL[n.hue]},0.9)`;
      ctx.shadowColor = `rgba(${COL[n.hue]},0.9)`;
      ctx.shadowBlur = 10 * dpr;
      ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
    }
    if (!reduce) requestAnimationFrame(draw);
  }

  resize();
  window.addEventListener("resize", resize);
  draw();
})();
