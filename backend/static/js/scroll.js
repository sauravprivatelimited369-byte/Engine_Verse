/* ===========================================================================
   Meridian — scroll storytelling, 3D stage orchestration & live workbench
   ---------------------------------------------------------------------------
   Progressive enhancement for the homepage and shared surfaces:
   - Reveal-on-scroll (.ev-reveal) and staggered groups ([data-stagger])
   - Scroll-linked parallax progress (--scroll-p) on visible [data-scroll-scene]
   - Topbar depth, reading progress bar and keyboard-safe auto-hide
   - Floating chapter rail active state ([data-rail-link])
   - Hero 3D Observatory model switcher ([data-stage-pick], [data-atlas-load])
   - Sticky 3D scroll-storytelling choreography (#mx-story-rail)
   - 4-tab Interactive Workbench (4-depth notes, live self-marking MCQ quiz,
     3D-flip flashcard deck, multi-language code preview + clipboard copy)
   - Horizontal 3D Atlas filtering, smooth track controls & 3D card tilt
   - Instant 45-branch search filter ([data-branch-filter])
   - Device-local Today's Plan checklist ([data-plan-step])

   Zero external dependencies, strict-CSP safe, reduced-motion respectful.
   =========================================================================== */

(function () {
  "use strict";

  var prefersReduced = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var canHover = !!(window.matchMedia && window.matchMedia("(hover: hover) and (pointer: fine)").matches);

  // Tell the stylesheet that the reveal observer is alive; without this the
  // CSS failsafe reveals every section after 2.6s.
  document.documentElement.classList.add("ev-script-ready");

  /* ---------- staggered groups ---------- */
  var staggerGroups = document.querySelectorAll("[data-stagger]");
  staggerGroups.forEach(function (group) {
    var kids = group.children;
    for (var i = 0; i < kids.length; i++) {
      kids[i].style.setProperty("--ev-stagger", Math.min(i * 60, 360) + "ms");
    }
  });

  /* ---------- scroll reveal ---------- */
  var revealEls = document.querySelectorAll(".ev-reveal");
  if (prefersReduced || !("IntersectionObserver" in window)) {
    revealEls.forEach(function (el) { el.classList.add("ev-show"); });
  } else {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("ev-show");
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.1, rootMargin: "0px 0px -8% 0px" });
    revealEls.forEach(function (el, index) {
      if (!el.style.getPropertyValue("--ev-delay")) {
        el.style.setProperty("--ev-delay", Math.min((index % 5) * 50, 200) + "ms");
      }
      observer.observe(el);
    });
  }

  /* ---------- animated counters ---------- */
  function formatNumber(n) {
    return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }
  function countUp(el) {
    if (el.dataset.evDone === "1") return;
    el.dataset.evDone = "1";
    var target = parseInt(el.getAttribute("data-target"), 10) || 0;
    if (!target || prefersReduced) {
      el.textContent = formatNumber(target);
      return;
    }
    var duration = 950;
    var startTime = performance.now();
    function frame(now) {
      var p = Math.min((now - startTime) / duration, 1);
      var ease = 1 - Math.pow(1 - p, 3);
      el.textContent = formatNumber(Math.floor(target * ease));
      el.classList.add("ev-counting");
      if (p < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }
  var counterEls = document.querySelectorAll(".ev-count .n[data-target], [data-count-target]");
  counterEls.forEach(function (el) {
    if (!el.getAttribute("data-target") && el.getAttribute("data-count-target")) {
      el.setAttribute("data-target", el.getAttribute("data-count-target"));
    }
  });
  if ("IntersectionObserver" in window && !prefersReduced) {
    var counterObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) countUp(entry.target);
      });
    }, { threshold: 0.35, rootMargin: "0px 0px -8% 0px" });
    counterEls.forEach(function (el) { counterObserver.observe(el); });
  } else {
    counterEls.forEach(function (el) { countUp(el); });
  }

  /* ---------- scroll-linked depth scenes (--scroll-p) ---------- */
  var scrollScenes = Array.prototype.slice.call(document.querySelectorAll("[data-scroll-scene]"));
  var activeScenes = [];
  if (scrollScenes.length && !prefersReduced && "IntersectionObserver" in window) {
    var sceneObs = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        var idx = activeScenes.indexOf(entry.target);
        if (entry.isIntersecting && idx === -1) activeScenes.push(entry.target);
        else if (!entry.isIntersecting && idx !== -1) activeScenes.splice(idx, 1);
      });
    }, { rootMargin: "120px 0px 120px 0px" });
    scrollScenes.forEach(function (el) { sceneObs.observe(el); });
  }

  /* ---------- topbar: depth, progress and auto-hide ---------- */
  var topbar = document.querySelector(".topbar");
  var progress = document.querySelector("[data-scroll-progress]");
  var lastY = window.scrollY || window.pageYOffset || 0;
  var queued = false;

  function applyScroll() {
    queued = false;
    var y = window.scrollY || window.pageYOffset || 0;
    var vh = window.innerHeight || 800;

    if (topbar) {
      topbar.classList.toggle("is-scrolled", y > 8);
      var busy = topbar.classList.contains("open") || topbar.contains(document.activeElement);
      if (prefersReduced || busy || y < 180) {
        topbar.classList.remove("is-hidden");
      } else {
        var delta = y - lastY;
        if (delta > 8) topbar.classList.add("is-hidden");
        else if (delta < -4) topbar.classList.remove("is-hidden");
      }
    }

    if (progress) {
      var max = document.documentElement.scrollHeight - vh;
      var pct = max > 0 ? Math.min(Math.max(y / max, 0), 1) : 0;
      progress.style.transform = "scaleX(" + pct + ")";
    }

    for (var i = 0; i < activeScenes.length; i++) {
      var sc = activeScenes[i];
      var rect = sc.getBoundingClientRect();
      var total = vh + rect.height;
      var p = total > 0 ? (vh - rect.top) / total : 0.5;
      p = Math.min(Math.max(p, 0), 1);
      sc.style.setProperty("--scroll-p", p.toFixed(4));
    }

    lastY = y;
  }

  window.addEventListener("scroll", function () {
    if (queued) return;
    queued = true;
    requestAnimationFrame(applyScroll);
  }, { passive: true });
  window.addEventListener("resize", applyScroll, { passive: true });
  applyScroll();

  if (topbar) {
    topbar.addEventListener("focusin", function () { topbar.classList.remove("is-hidden"); });
    topbar.addEventListener("pointerdown", function () {
      if (topbar.classList.contains("is-hidden")) topbar.classList.remove("is-hidden");
    });
  }

  /* ---------- floating chapter rail ---------- */
  var railLinks = Array.prototype.slice.call(document.querySelectorAll("[data-rail-link]"));
  var chapterSecs = Array.prototype.slice.call(document.querySelectorAll("[data-chapter-section]"));
  if (railLinks.length && chapterSecs.length && "IntersectionObserver" in window) {
    var activateRail = function (id) {
      railLinks.forEach(function (link) {
        var on = link.getAttribute("href") === "#" + id;
        link.classList.toggle("is-active", on);
        if (on) link.setAttribute("aria-current", "true");
        else link.removeAttribute("aria-current");
      });
    };
    var railObs = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting && entry.target.id) activateRail(entry.target.id);
      });
    }, { rootMargin: "-28% 0px -55% 0px", threshold: 0 });
    chapterSecs.forEach(function (sec) { railObs.observe(sec); });
  }

  /* ---------- helper: swap a [data-model3d] scene safely ---------- */
  function swapViewportScene(viewport, sceneJson, ariaLabel) {
    if (!viewport || !sceneJson) return;
    viewport.dataset.scene = sceneJson;
    var canvas = viewport.querySelector("canvas");
    if (canvas && ariaLabel) {
      canvas.setAttribute("aria-label", "Interactive 3D engineering model: " + ariaLabel);
    }
    if (window.EngineVerse3D && typeof window.EngineVerse3D.setScene === "function") {
      window.EngineVerse3D.setScene(viewport, sceneJson);
    }
  }

  /* ---------- Hero 3D Observatory switcher ---------- */
  var heroViewport = document.getElementById("mx-hero-viewport");
  var heroPicks = Array.prototype.slice.call(document.querySelectorAll("[data-stage-pick]"));
  var heroMetas = Array.prototype.slice.call(document.querySelectorAll("[data-stage-meta]"));
  var customMeta = document.querySelector("[data-stage-meta-custom]");

  function selectHeroModel(key, sceneJson, labelText) {
    heroPicks.forEach(function (btn) {
      var on = btn.getAttribute("data-stage-pick") === String(key);
      btn.classList.toggle("is-on", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    if (customMeta) customMeta.hidden = true;
    heroMetas.forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-stage-meta") !== String(key);
    });
    swapViewportScene(heroViewport, sceneJson, labelText);
  }

  if (heroViewport && heroPicks.length) {
    heroPicks.forEach(function (btn, idx) {
      btn.addEventListener("click", function () {
        selectHeroModel(
          btn.getAttribute("data-stage-pick"),
          btn.getAttribute("data-stage-scene"),
          btn.getAttribute("data-stage-label")
        );
      });
      btn.addEventListener("keydown", function (e) {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        e.preventDefault();
        var next = e.key === "ArrowRight"
          ? (idx + 1) % heroPicks.length
          : (idx - 1 + heroPicks.length) % heroPicks.length;
        heroPicks[next].focus();
        heroPicks[next].click();
      });
    });
  }

  /* ---------- Atlas "Load in 3D Stage" buttons ---------- */
  var atlasLoadBtns = document.querySelectorAll("[data-atlas-load]");
  atlasLoadBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var slug = btn.getAttribute("data-atlas-slug") || "";
      var matchingPick = heroPicks.find(function (p) {
        return p.getAttribute("data-stage-slug") === slug;
      });
      var stageCard = document.getElementById("mx-hero-stage-card");
      if (matchingPick) {
        matchingPick.click();
      } else if (heroViewport) {
        heroPicks.forEach(function (p) {
          p.classList.remove("is-on");
          p.setAttribute("aria-selected", "false");
        });
        heroMetas.forEach(function (m) { m.hidden = true; });
        if (customMeta) {
          var discEl = customMeta.querySelector("[data-custom-discipline]");
          var titleEl = customMeta.querySelector("[data-custom-title]");
          var capEl = customMeta.querySelector("[data-custom-caption]");
          var linkEl = customMeta.querySelector("[data-custom-link]");
          var cardLink = btn.closest(".mx-atlas-card")
            ? btn.closest(".mx-atlas-card").querySelector("[data-atlas-topic-link]")
            : null;
          if (discEl) discEl.textContent = btn.getAttribute("data-atlas-discipline") || "";
          if (titleEl) titleEl.textContent = btn.getAttribute("data-atlas-title") || "";
          if (capEl) capEl.textContent = btn.getAttribute("data-atlas-caption") || "";
          if (linkEl && cardLink) {
            linkEl.setAttribute("href", cardLink.getAttribute("href"));
            linkEl.textContent = "Open " + (btn.getAttribute("data-atlas-topic") || "topic") + " →";
          }
          customMeta.hidden = false;
        }
        swapViewportScene(
          heroViewport,
          btn.getAttribute("data-atlas-scene"),
          btn.getAttribute("data-atlas-title")
        );
      }
      if (stageCard && stageCard.scrollIntoView) {
        stageCard.scrollIntoView({ behavior: prefersReduced ? "auto" : "smooth", block: "center" });
      }
    });
  });

  /* ---------- Sticky 3D scroll-storytelling (#mx-story-rail) ---------- */
  var storyRoot = document.getElementById("mx-story-rail");
  if (storyRoot) {
    var storyViewport = document.getElementById("mx-story-viewport");
    var storySteps = Array.prototype.slice.call(storyRoot.querySelectorAll("[data-story-step]"));
    var storyTabs = Array.prototype.slice.call(storyRoot.querySelectorAll("[data-story-tab]"));
    var storyMetas = Array.prototype.slice.call(storyRoot.querySelectorAll("[data-story-meta]"));
    var currentStep = "";

    var activateStoryStep = function (stepId) {
      if (stepId === currentStep) return;
      currentStep = stepId;
      storySteps.forEach(function (el) {
        el.classList.toggle("is-active", el.getAttribute("data-story-step") === stepId);
      });
      storyTabs.forEach(function (tab) {
        var on = tab.getAttribute("data-story-tab") === stepId;
        tab.classList.toggle("is-on", on);
        tab.setAttribute("aria-selected", on ? "true" : "false");
        if (on && storyViewport) {
          swapViewportScene(
            storyViewport,
            tab.getAttribute("data-story-scene"),
            tab.getAttribute("data-story-label")
          );
        }
      });
      storyMetas.forEach(function (meta) {
        meta.hidden = meta.getAttribute("data-story-meta") !== stepId;
      });
    };

    storyTabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        var stepId = tab.getAttribute("data-story-tab");
        activateStoryStep(stepId);
        var chapter = storyRoot.querySelector('[data-story-step="' + stepId + '"]');
        if (chapter && window.innerWidth > 980 && chapter.scrollIntoView) {
          chapter.scrollIntoView({ behavior: prefersReduced ? "auto" : "smooth", block: "center" });
        }
      });
    });

    if ("IntersectionObserver" in window && storySteps.length) {
      var storyObs = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            activateStoryStep(entry.target.getAttribute("data-story-step"));
          }
        });
      }, { rootMargin: "-32% 0px -48% 0px", threshold: 0 });
      storySteps.forEach(function (step) { storyObs.observe(step); });
    }
  }

  /* ---------- Interactive 4-Tab Workbench ---------- */
  var wbRoot = document.getElementById("mx-workbench");
  if (wbRoot) {
    var wbTabs = Array.prototype.slice.call(wbRoot.querySelectorAll("[data-wb-tab]"));
    var wbPanels = Array.prototype.slice.call(wbRoot.querySelectorAll("[data-wb-panel]"));

    var selectWbTab = function (key) {
      wbTabs.forEach(function (tab) {
        var on = tab.getAttribute("data-wb-tab") === key;
        tab.classList.toggle("is-on", on);
        tab.setAttribute("aria-selected", on ? "true" : "false");
        tab.setAttribute("tabindex", on ? "0" : "-1");
      });
      wbPanels.forEach(function (panel) {
        panel.hidden = panel.getAttribute("data-wb-panel") !== key;
      });
    };

    wbTabs.forEach(function (tab, idx) {
      tab.addEventListener("click", function () {
        selectWbTab(tab.getAttribute("data-wb-tab"));
      });
      tab.addEventListener("keydown", function (e) {
        var nextIdx = -1;
        if (e.key === "ArrowRight") nextIdx = (idx + 1) % wbTabs.length;
        else if (e.key === "ArrowLeft") nextIdx = (idx - 1 + wbTabs.length) % wbTabs.length;
        else if (e.key === "Home") nextIdx = 0;
        else if (e.key === "End") nextIdx = wbTabs.length - 1;
        if (nextIdx >= 0) {
          e.preventDefault();
          wbTabs[nextIdx].focus();
          selectWbTab(wbTabs[nextIdx].getAttribute("data-wb-tab"));
        }
      });
    });

    /* 1. Four-depth note reader */
    var depthTabs = Array.prototype.slice.call(wbRoot.querySelectorAll("[data-depth-tab]"));
    var depthPanes = Array.prototype.slice.call(wbRoot.querySelectorAll("[data-depth-pane]"));
    depthTabs.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var level = btn.getAttribute("data-depth-tab");
        depthTabs.forEach(function (b) {
          var on = b === btn;
          b.classList.toggle("is-on", on);
          b.setAttribute("aria-selected", on ? "true" : "false");
        });
        depthPanes.forEach(function (pane) {
          pane.hidden = pane.getAttribute("data-depth-pane") !== level;
        });
      });
    });

    /* 2. Instant self-marking MCQ practice quiz */
    var quizItems = Array.prototype.slice.call(wbRoot.querySelectorAll("[data-mx-quiz-item]"));
    var quizPicks = Array.prototype.slice.call(wbRoot.querySelectorAll("[data-mx-quiz-pick]"));
    var quizScoreEl = wbRoot.querySelector("[data-mx-quiz-score]");
    var solvedState = {};

    var updateQuizScore = function () {
      if (!quizScoreEl) return;
      var keys = Object.keys(solvedState);
      var correctCount = keys.filter(function (k) { return solvedState[k] === true; }).length;
      quizScoreEl.textContent = keys.length
        ? correctCount + " of " + quizItems.length + " correct"
        : quizItems.length + " questions ready";
    };

    var showQuizIndex = function (idx) {
      quizItems.forEach(function (item, i) { item.hidden = i !== idx; });
      quizPicks.forEach(function (btn, i) {
        var on = i === idx;
        btn.classList.toggle("is-on", on);
        btn.setAttribute("aria-selected", on ? "true" : "false");
      });
    };

    quizPicks.forEach(function (btn, idx) {
      btn.addEventListener("click", function () { showQuizIndex(idx); });
    });

    quizItems.forEach(function (item, idx) {
      var correct = item.getAttribute("data-correct") || "";
      var optBtns = Array.prototype.slice.call(item.querySelectorAll("[data-mx-opt]"));
      var checkBtn = item.querySelector("[data-mx-check]");
      var nextBtn = item.querySelector("[data-mx-next-q]");
      var feedback = item.querySelector("[data-mx-feedback]");
      var verdictEl = item.querySelector("[data-mx-verdict]");
      var chosen = "";

      optBtns.forEach(function (opt) {
        opt.addEventListener("click", function () {
          chosen = opt.getAttribute("data-mx-opt") || "";
          optBtns.forEach(function (o) {
            var sel = o === opt;
            o.classList.toggle("is-selected", sel);
            o.classList.remove("is-right", "is-wrong");
            o.setAttribute("aria-checked", sel ? "true" : "false");
          });
          if (checkBtn) checkBtn.disabled = false;
        });
      });

      if (checkBtn) {
        checkBtn.addEventListener("click", function () {
          if (!chosen) return;
          var isRight = chosen === correct;
          solvedState[String(idx)] = isRight;
          optBtns.forEach(function (o) {
            var label = o.getAttribute("data-mx-opt");
            o.classList.toggle("is-right", label === correct);
            o.classList.toggle("is-wrong", label === chosen && !isRight);
          });
          if (verdictEl) {
            verdictEl.textContent = isRight
              ? "Correct — Option " + correct + "."
              : "Not quite — Option " + correct + " is the right answer.";
            verdictEl.className = "mx-quiz-verdict " + (isRight ? "is-ok" : "is-bad");
          }
          if (feedback) feedback.hidden = false;
          if (quizPicks[idx]) {
            quizPicks[idx].classList.remove("is-ok", "is-bad");
            quizPicks[idx].classList.add(isRight ? "is-ok" : "is-bad");
          }
          updateQuizScore();
        });
      }

      if (nextBtn) {
        nextBtn.addEventListener("click", function () {
          showQuizIndex((idx + 1) % quizItems.length);
        });
      }
    });
    updateQuizScore();

    /* 3. 3D-perspective flashcard deck */
    var fcDeck = wbRoot.querySelector("[data-mx-deck]");
    if (fcDeck) {
      var fcCards = Array.prototype.slice.call(fcDeck.querySelectorAll("[data-mx-card]"));
      var fcCounter = fcDeck.querySelector("[data-mx-fc-counter]");
      var fcTally = fcDeck.querySelector("[data-mx-fc-tally]");
      var fcPrev = fcDeck.querySelector("[data-mx-fc-prev]");
      var fcNext = fcDeck.querySelector("[data-mx-fc-next]");
      var fcFlip = fcDeck.querySelector("[data-mx-fc-flip]");
      var fcKnow = fcDeck.querySelector("[data-mx-fc-know]");
      var fcAgain = fcDeck.querySelector("[data-mx-fc-again]");
      var fcIdx = 0;
      var fcStatus = {};

      var renderFc = function () {
        fcCards.forEach(function (card, i) {
          var active = i === fcIdx;
          card.hidden = !active;
          if (!active) {
            card.classList.remove("is-flipped");
            card.setAttribute("aria-pressed", "false");
          }
        });
        if (fcCounter) fcCounter.textContent = "Card " + (fcIdx + 1) + " of " + fcCards.length;
        if (fcTally) {
          var known = Object.keys(fcStatus).filter(function (k) { return fcStatus[k] === "known"; }).length;
          var review = Object.keys(fcStatus).filter(function (k) { return fcStatus[k] === "again"; }).length;
          fcTally.textContent = known + " known · " + review + " to review";
        }
      };

      var flipCurrent = function () {
        var card = fcCards[fcIdx];
        if (!card) return;
        var flipped = card.classList.toggle("is-flipped");
        card.setAttribute("aria-pressed", flipped ? "true" : "false");
      };

      fcCards.forEach(function (card) {
        card.addEventListener("click", flipCurrent);
        card.addEventListener("keydown", function (e) {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            flipCurrent();
          }
        });
      });
      if (fcFlip) fcFlip.addEventListener("click", flipCurrent);
      if (fcPrev) fcPrev.addEventListener("click", function () {
        fcIdx = (fcIdx - 1 + fcCards.length) % fcCards.length;
        renderFc();
      });
      if (fcNext) fcNext.addEventListener("click", function () {
        fcIdx = (fcIdx + 1) % fcCards.length;
        renderFc();
      });
      if (fcKnow) fcKnow.addEventListener("click", function () {
        fcStatus[String(fcIdx)] = "known";
        fcIdx = (fcIdx + 1) % fcCards.length;
        renderFc();
      });
      if (fcAgain) fcAgain.addEventListener("click", function () {
        fcStatus[String(fcIdx)] = "again";
        fcIdx = (fcIdx + 1) % fcCards.length;
        renderFc();
      });
      renderFc();
    }

    /* 4. Multi-language judged code switcher + clipboard copy */
    var codeTabs = Array.prototype.slice.call(wbRoot.querySelectorAll("[data-code-lang]"));
    var codePanes = Array.prototype.slice.call(wbRoot.querySelectorAll("[data-code-pane]"));
    var copyBtn = wbRoot.querySelector("[data-copy-code]");
    codeTabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        var lang = tab.getAttribute("data-code-lang");
        codeTabs.forEach(function (t) {
          var on = t === tab;
          t.classList.toggle("is-on", on);
          t.setAttribute("aria-selected", on ? "true" : "false");
        });
        codePanes.forEach(function (pane) {
          pane.hidden = pane.getAttribute("data-code-pane") !== lang;
        });
      });
    });
    if (copyBtn && navigator.clipboard && navigator.clipboard.writeText) {
      copyBtn.addEventListener("click", function () {
        var visiblePane = codePanes.find(function (p) { return !p.hidden; });
        var codeEl = visiblePane ? visiblePane.querySelector("code") : null;
        if (!codeEl) return;
        navigator.clipboard.writeText(codeEl.textContent || "").then(function () {
          var orig = copyBtn.textContent;
          copyBtn.textContent = "Copied";
          setTimeout(function () { copyBtn.textContent = orig; }, 1600);
        }).catch(function () {});
      });
    }
  }

  /* ---------- Horizontal 3D Atlas filtering, track scroll & 3D tilt ---------- */
  var atlasRoot = document.getElementById("mx-atlas");
  if (atlasRoot) {
    var atlasTrack = atlasRoot.querySelector("[data-atlas-track]");
    var atlasCards = Array.prototype.slice.call(atlasRoot.querySelectorAll("[data-atlas-card]"));
    var atlasFilters = Array.prototype.slice.call(atlasRoot.querySelectorAll("[data-atlas-filter]"));
    var atlasPrev = atlasRoot.querySelector("[data-atlas-prev]");
    var atlasNext = atlasRoot.querySelector("[data-atlas-next]");
    var atlasBar = atlasRoot.querySelector("[data-atlas-progress]");

    atlasFilters.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var cat = btn.getAttribute("data-atlas-filter") || "all";
        atlasFilters.forEach(function (b) {
          var on = b === btn;
          b.classList.toggle("is-on", on);
          b.setAttribute("aria-pressed", on ? "true" : "false");
        });
        atlasCards.forEach(function (card) {
          var match = cat === "all" || card.getAttribute("data-atlas-cat") === cat;
          card.hidden = !match;
        });
        if (atlasTrack) atlasTrack.scrollLeft = 0;
      });
    });

    var updateAtlasBar = function () {
      if (!atlasTrack || !atlasBar) return;
      var maxScroll = atlasTrack.scrollWidth - atlasTrack.clientWidth;
      var pct = maxScroll > 4 ? Math.min(Math.max(atlasTrack.scrollLeft / maxScroll, 0), 1) : 1;
      atlasBar.style.transform = "scaleX(" + Math.max(0.18, pct) + ")";
    };

    if (atlasTrack) {
      atlasTrack.addEventListener("scroll", updateAtlasBar, { passive: true });
      window.addEventListener("resize", updateAtlasBar, { passive: true });
      updateAtlasBar();
    }
    if (atlasPrev && atlasTrack) {
      atlasPrev.addEventListener("click", function () {
        atlasTrack.scrollBy({ left: -340, behavior: prefersReduced ? "auto" : "smooth" });
      });
    }
    if (atlasNext && atlasTrack) {
      atlasNext.addEventListener("click", function () {
        atlasTrack.scrollBy({ left: 340, behavior: prefersReduced ? "auto" : "smooth" });
      });
    }
  }

  /* ---------- Subtle 3D perspective card tilt ---------- */
  if (canHover && !prefersReduced) {
    var tiltCards = document.querySelectorAll("[data-tilt-card]");
    tiltCards.forEach(function (card) {
      card.addEventListener("pointermove", function (e) {
        var rect = card.getBoundingClientRect();
        if (!rect.width || !rect.height) return;
        var px = (e.clientX - rect.left) / rect.width;
        var py = (e.clientY - rect.top) / rect.height;
        var ry = ((px - 0.5) * 7).toFixed(2) + "deg";
        var rx = ((0.5 - py) * 6).toFixed(2) + "deg";
        card.style.setProperty("--rx", rx);
        card.style.setProperty("--ry", ry);
        card.style.setProperty("--gx", Math.round(px * 100) + "%");
        card.style.setProperty("--gy", Math.round(py * 100) + "%");
      });
      card.addEventListener("pointerleave", function () {
        card.style.setProperty("--rx", "0deg");
        card.style.setProperty("--ry", "0deg");
      });
    });
  }

  /* ---------- Instant 45-branch search inside the branch drawer ---------- */
  var branchFilter = document.querySelector("[data-branch-filter]");
  if (branchFilter) {
    var allDetails = branchFilter.closest("details") || document;
    var branchItems = Array.prototype.slice.call(allDetails.querySelectorAll(".mx-branch-all-grid li"));
    var branchGroups = Array.prototype.slice.call(allDetails.querySelectorAll(".mx-branch-all-grid > div"));
    var branchEmpty = allDetails.querySelector("[data-branch-filter-empty]");
    branchFilter.addEventListener("input", function () {
      var q = (branchFilter.value || "").trim().toLowerCase();
      var visibleCount = 0;
      branchItems.forEach(function (li) {
        var txt = (li.textContent || "").toLowerCase();
        var show = !q || txt.indexOf(q) !== -1;
        li.hidden = !show;
        if (show) visibleCount++;
      });
      branchGroups.forEach(function (grp) {
        var any = Array.prototype.some.call(grp.querySelectorAll("li"), function (li) { return !li.hidden; });
        grp.hidden = !any;
      });
      if (branchEmpty) branchEmpty.hidden = visibleCount > 0;
    });
  }

  /* ---------- today's study plan tick-boxes ---------- */
  var planBoxes = document.querySelectorAll("[data-plan-step]");
  if (planBoxes.length) {
    var summary = document.querySelector("[data-plan-summary]");
    var bar = document.querySelector("[data-plan-bar]");
    var progressbar = document.querySelector("[data-plan-progressbar]");
    var today = new Date();
    var key = "ev:today-plan:" + today.getFullYear() + "-" +
      String(today.getMonth() + 1).padStart(2, "0") + "-" +
      String(today.getDate()).padStart(2, "0");
    var done = {};
    try { done = JSON.parse(localStorage.getItem(key) || "{}") || {}; } catch (e) { done = {}; }
    var update = function () {
      var n = 0;
      planBoxes.forEach(function (box) {
        var on = !!done[box.getAttribute("data-plan-step")];
        box.checked = on;
        var card = box.closest("[data-plan-card]");
        if (card) card.classList.toggle("is-done", on);
        if (on) n++;
      });
      var pct = Math.round((n / planBoxes.length) * 100);
      if (bar) bar.style.width = pct + "%";
      if (progressbar) {
        progressbar.setAttribute("aria-valuenow", String(n));
        progressbar.setAttribute("aria-valuetext", n + " of " + planBoxes.length + " steps done");
      }
      if (summary) {
        summary.textContent = n === planBoxes.length
          ? "All " + planBoxes.length + " done — nice work today"
          : n + " of " + planBoxes.length + " done";
      }
    };
    planBoxes.forEach(function (box) {
      box.addEventListener("change", function () {
        done[box.getAttribute("data-plan-step")] = box.checked;
        try { localStorage.setItem(key, JSON.stringify(done)); } catch (e) { /* storage blocked */ }
        update();
      });
    });
    update();
  }
})();
