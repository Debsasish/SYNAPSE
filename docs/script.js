/* ================= SYNAPSE site interactions ================= */
(function () {
  "use strict";

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

  /* ---------- Reveal on scroll ---------- */
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
  document.querySelectorAll(".reveal").forEach((el) => io.observe(el));

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

  /* ---------- Code tabs ---------- */
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      const id = tab.dataset.tab;
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(id).classList.add("active");
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
  lightbox.addEventListener("click", () => lightbox.classList.remove("open"));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") lightbox.classList.remove("open");
  });

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

  /* ---------- Animated knowledge-graph background ---------- */
  const canvas = document.getElementById("graph-bg");
  const ctx = canvas.getContext("2d");
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let W, H, nodes, dpr;

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = canvas.width = window.innerWidth * dpr;
    H = canvas.height = window.innerHeight * dpr;
    canvas.style.width = window.innerWidth + "px";
    canvas.style.height = window.innerHeight + "px";
    const count = Math.min(70, Math.floor((window.innerWidth * window.innerHeight) / 22000));
    nodes = Array.from({ length: count }, () => ({
      x: Math.random() * W,
      y: Math.random() * H,
      vx: (Math.random() - 0.5) * 0.22 * dpr,
      vy: (Math.random() - 0.5) * 0.22 * dpr,
      r: (Math.random() * 1.8 + 1.2) * dpr,
      hue: Math.random() < 0.5 ? "cyan" : "violet",
    }));
  }

  const COL = {
    cyan: "53,224,216",
    violet: "139,107,255",
  };
  const LINK = 140;

  function draw() {
    ctx.clearRect(0, 0, W, H);
    const linkDist = LINK * dpr;
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      a.x += a.vx;
      a.y += a.vy;
      if (a.x < 0 || a.x > W) a.vx *= -1;
      if (a.y < 0 || a.y > H) a.vy *= -1;
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
