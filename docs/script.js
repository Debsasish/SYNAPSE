(() => {
  "use strict";

  const root = document.documentElement;
  const header = document.querySelector(".site-header");
  const navToggle = document.querySelector(".nav-toggle");
  const nav = document.querySelector(".site-nav");
  const reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  const coarsePointerQuery = window.matchMedia("(pointer: coarse)");
  const smallViewportQuery = window.matchMedia("(max-width: 720px)");

  const setScrolled = () => {
    if (!header) {
      return;
    }
    header.classList.toggle("is-scrolled", window.scrollY > 12);
  };

  window.addEventListener("scroll", setScrolled, { passive: true });
  setScrolled();

  if (navToggle && nav) {
    navToggle.addEventListener("click", () => {
      const expanded = navToggle.getAttribute("aria-expanded") === "true";
      navToggle.setAttribute("aria-expanded", String(!expanded));
      nav.classList.toggle("is-open", !expanded);
    });

    nav.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        nav.classList.remove("is-open");
        navToggle.setAttribute("aria-expanded", "false");
      });
    });
  }

  document.querySelectorAll(".copy-button").forEach((button) => {
    button.addEventListener("click", async () => {
      const targetId = button.getAttribute("data-copy-target");
      const source = targetId ? document.getElementById(targetId) : null;
      const text = source ? source.innerText.trim() : "";
      if (!text) {
        return;
      }

      try {
        await navigator.clipboard.writeText(text);
        const previous = button.textContent;
        button.textContent = "Copied";
        window.setTimeout(() => {
          button.textContent = previous;
        }, 1600);
      } catch (_error) {
        button.textContent = "Copy failed";
        window.setTimeout(() => {
          button.textContent = "Copy citation";
        }, 1600);
      }
    });
  });

  const canvas = document.getElementById("hero-canvas");
  const hero = document.getElementById("hero");
  const context = canvas ? canvas.getContext("2d") : null;

  if (canvas && hero && context) {
    const worldSeeds = [
      [-0.75, -0.08, 0.22, 0.18],
      [-0.46, -0.16, 0.13, 0.09],
      [-0.38, 0.18, 0.11, 0.15],
      [-0.02, -0.05, 0.18, 0.12],
      [0.23, -0.1, 0.22, 0.16],
      [0.48, -0.01, 0.15, 0.11],
      [0.34, 0.22, 0.12, 0.12],
      [0.74, 0.22, 0.1, 0.08],
    ];

    let width = 0;
    let height = 0;
    let dpr = 1;
    let nodes = [];
    let animationFrame = 0;
    let resizeTimer = 0;
    let currentOffsetX = 0;
    let currentOffsetY = 0;
    let targetOffsetX = 0;
    let targetOffsetY = 0;
    let shouldAnimate = !reducedMotionQuery.matches;
    let simplified = coarsePointerQuery.matches || smallViewportQuery.matches;
    let running = false;

    const randomInCluster = (cx, cy, sx, sy) => {
      const angle = Math.random() * Math.PI * 2;
      const radius = Math.sqrt(Math.random());
      return {
        x: cx + Math.cos(angle) * sx * radius,
        y: cy + Math.sin(angle) * sy * radius,
      };
    };

    const rebuildNodes = () => {
      const baseCount = simplified ? 55 : 95;
      nodes = [];

      for (let index = 0; index < baseCount; index += 1) {
        const seed = worldSeeds[index % worldSeeds.length];
        const sample = randomInCluster(seed[0], seed[1], seed[2], seed[3]);
        const drift = simplified ? 0.05 : 0.12;
        nodes.push({
          x: sample.x,
          y: sample.y,
          driftX: (Math.random() - 0.5) * drift,
          driftY: (Math.random() - 0.5) * drift,
          radius: simplified ? 1.2 + Math.random() * 1.4 : 1 + Math.random() * 1.8,
          depth: 0.4 + Math.random() * 0.9,
        });
      }
    };

    const resizeCanvas = () => {
      const rect = hero.getBoundingClientRect();
      width = Math.max(1, Math.floor(rect.width));
      height = Math.max(1, Math.floor(rect.height));
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      simplified = coarsePointerQuery.matches || smallViewportQuery.matches || width < 720;
      rebuildNodes();
    };

    const project = (node, tick) => {
      const driftAmount = shouldAnimate ? tick * 0.00012 : 0;
      const driftX = shouldAnimate ? Math.sin(driftAmount + node.y * 12) * node.driftX : 0;
      const driftY = shouldAnimate ? Math.cos(driftAmount + node.x * 10) * node.driftY : 0;
      const ellipseX = width * 0.5 + node.x * width * 0.42;
      const ellipseY = height * 0.44 + node.y * height * 0.25;
      const parallaxX = currentOffsetX * node.depth;
      const parallaxY = currentOffsetY * node.depth;

      return {
        x: ellipseX + driftX * width + parallaxX,
        y: ellipseY + driftY * height + parallaxY,
        radius: node.radius,
      };
    };

    const renderFrame = (tick) => {
      context.clearRect(0, 0, width, height);

      currentOffsetX += (targetOffsetX - currentOffsetX) * 0.06;
      currentOffsetY += (targetOffsetY - currentOffsetY) * 0.06;

      const projected = nodes.map((node) => project(node, tick));
      const linkDistance = simplified ? 78 : 105;

      context.lineWidth = 1;

      for (let i = 0; i < projected.length; i += 1) {
        const a = projected[i];
        for (let j = i + 1; j < projected.length; j += 1) {
          const b = projected[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const distance = Math.hypot(dx, dy);

          if (distance > linkDistance) {
            continue;
          }

          const alpha = 0.18 * (1 - distance / linkDistance);
          context.strokeStyle = `rgba(124, 231, 255, ${alpha})`;
          context.beginPath();
          context.moveTo(a.x, a.y);
          context.lineTo(b.x, b.y);
          context.stroke();
        }
      }

      projected.forEach((point, index) => {
        const emphasis = index % 6 === 0;
        context.fillStyle = emphasis ? "rgba(159, 140, 255, 0.95)" : "rgba(124, 231, 255, 0.88)";
        context.beginPath();
        context.arc(point.x, point.y, point.radius, 0, Math.PI * 2);
        context.fill();
      });

      context.strokeStyle = "rgba(124, 231, 255, 0.13)";
      context.setLineDash([3, 8]);
      context.lineWidth = 1;
      context.beginPath();
      context.ellipse(width * 0.5, height * 0.44, width * 0.43, height * 0.28, 0, 0, Math.PI * 2);
      context.stroke();
      context.setLineDash([]);
    };

    const draw = (tick) => {
      if (!running) {
        return;
      }

      renderFrame(tick);
      if (shouldAnimate) {
        animationFrame = window.requestAnimationFrame(draw);
      }
    };

    const start = () => {
      shouldAnimate = !reducedMotionQuery.matches;
      resizeCanvas();

      if (!shouldAnimate) {
        running = false;
        window.cancelAnimationFrame(animationFrame);
        renderFrame(0);
        return;
      }

      window.cancelAnimationFrame(animationFrame);
      running = true;
      animationFrame = window.requestAnimationFrame(draw);
    };

    const staticRender = () => {
      running = false;
      shouldAnimate = false;
      window.cancelAnimationFrame(animationFrame);
      resizeCanvas();
      renderFrame(0);
    };

    const handlePointer = (event) => {
      if (simplified || reducedMotionQuery.matches) {
        return;
      }

      const rect = hero.getBoundingClientRect();
      const pointerX = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      const pointerY = ((event.clientY - rect.top) / rect.height) * 2 - 1;
      targetOffsetX = pointerX * 14;
      targetOffsetY = pointerY * 10;
    };

    const handleLeave = () => {
      targetOffsetX = 0;
      targetOffsetY = 0;
    };

    window.addEventListener("resize", () => {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => {
        if (shouldAnimate) {
          resizeCanvas();
        } else {
          staticRender();
        }
      }, 120);
    });

    hero.addEventListener("pointermove", handlePointer, { passive: true });
    hero.addEventListener("pointerleave", handleLeave, { passive: true });

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            shouldAnimate = !reducedMotionQuery.matches;
            if (shouldAnimate) {
              start();
            } else {
              staticRender();
            }
          } else {
            running = false;
            window.cancelAnimationFrame(animationFrame);
          }
        });
      },
      { threshold: 0.08 }
    );

    staticRender();
    observer.observe(hero);
  }

  root.classList.add("js-ready");
})();
