/* Parametric sculptures, projected and depth-sorted without a GPU dependency. */
(() => {
  const live = document.querySelector("#live");
  if (!live) return;
  const $ = (id) => document.getElementById(id);
  const { sin, cos, PI, hypot, exp } = Math,
    turn = 2 * PI;
  const chapters = [...document.querySelectorAll(".chapter")];
  const objects = chapters.map(({ dataset }) => [
    dataset.name,
    dataset.tint,
    dataset.color.split(",").map(Number),
  ]);
  if (!chapters.length || !live.getContext("2d")) return;
  document.body.classList.add("interactive");
  const norm = (v) => v.map((x) => x / (hypot(...v) || 1));
  const cross = (a, b) => [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
  function point(k, u, v, parameter) {
    if (k === 0) {
      const r = 1 + 0.45 * cos(3 * u),
        dr = -1.35 * sin(3 * u),
        c = cos(2 * u),
        s = sin(2 * u);
      const t = norm([
        dr * c - 2 * r * s,
        dr * s + 2 * r * c,
        1.8 * cos(3 * u),
      ]);
      const n = norm([-t[1], t[0], 0]),
        b = cross(t, n);
      return [r * c, r * s, 0.6 * sin(3 * u)].map(
        (x, i) => x + parameter * (n[i] * cos(v) + b[i] * sin(v)),
      );
    }
    if (k === 1) {
      const lat = v / 2,
        r = 1.15 + 0.15 * cos(parameter * u + 2 * lat) * sin(lat) ** 2;
      return [r * sin(lat) * cos(u), r * sin(lat) * sin(u), 1.35 * cos(lat)];
    }
    if (k === 3) {
      const t = 0.55 * ((2 * v) / turn - 1),
        angle = (parameter * u) / 2,
        r = 1.1 + t * cos(angle);
      return [r * cos(u), r * sin(u), t * sin(angle)];
    }
    const r = 0.77 + 0.51 * cos(v),
      a = u * parameter;
    return [r * cos(a), r * sin(a), 2.5 * (u / turn - 0.5) + 0.12 * sin(v)];
  }
  function mesh(k, parameter) {
    const vertices = [],
      faces = [],
      rows = 92,
      cols = 30;
    for (let i = 0; i <= rows; i++)
      for (let j = 0; j <= cols; j++)
        vertices.push(
          point(k, (i * turn) / rows, (j * turn) / cols, parameter),
        );
    for (let i = 0; i < rows; i++)
      for (let j = 0; j < cols; j++) {
        const a = i * (cols + 1) + j,
          b = a + cols + 1;
        const delta = (p, q) => vertices[p].map((x, d) => x - vertices[q][d]);
        faces.push({
          ids: [a, b, b + 1, a + 1],
          normal: norm(cross(delta(b + 1, a), delta(a + 1, b))),
        });
      }
    return { vertices, faces, rows, cols, parameter };
  }
  const defaults = chapters.map((chapter) => Number(chapter.dataset.initial));
  const meshes = defaults.map((value, k) => mesh(k, value));
  let variant = meshes[0],
    meshMode = false;

  function draw(
    el,
    k,
    yaw,
    pitch,
    geometry = el === live ? variant : meshes[k],
    wire = el === live && meshMode,
  ) {
    const w = el.clientWidth,
      h = el.clientHeight,
      d = Math.min(devicePixelRatio, 2);
    if (!w || !h) return;
    if (el.width !== Math.round(w * d) || el.height !== Math.round(h * d)) {
      el.width = Math.round(w * d);
      el.height = Math.round(h * d);
    }
    const ctx = el.getContext("2d");
    ctx.setTransform(d, 0, 0, d, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const ca = cos(yaw),
      sa = sin(yaw),
      cb = cos(pitch),
      sb = sin(pitch);
    const rot = ([x, y, z]) => [
      x * ca - y * sa,
      (y * ca + x * sa) * cb - z * sb,
      (y * ca + x * sa) * sb + z * cb,
    ];
    const scale =
      Math.min(w * 0.245, h * (el === live ? 0.26 : 0.27)) *
      (k === 0 ? 1 : 1.07);
    const pts = geometry.vertices.map((p) => {
      const [x, y, z] = rot(p),
        s = (scale * 6) / (6 - z);
      return [w / 2 + x * s, h * 0.49 + y * s, z];
    });
    if (wire) {
      const { rows, cols } = geometry;
      ctx.strokeStyle = `rgb(${objects[k][2].map((x) => Math.round(x * 0.55)).join(",")})`;
      ctx.lineWidth = 0.9;
      const line = (a, b) => {
        ctx.beginPath();
        ctx.moveTo(a[0], a[1]);
        ctx.lineTo(b[0], b[1]);
        ctx.globalAlpha = Math.max(
          0.13,
          Math.min(0.96, 0.5 + (a[2] + b[2]) * 0.14),
        );
        ctx.stroke();
      };
      for (let i = 0; i < rows; i++)
        for (let j = 0; j < cols; j++) {
          const index = i * (cols + 1) + j;
          if (j % 3 === 0) line(pts[index], pts[index + cols + 1]);
          if (i % 2 === 0) line(pts[index], pts[index + 1]);
        }
      // The strip has two parameter edges. Odd half twists join them into
      // one boundary; even counts keep them separate. Trace them in mesh mode.
      if (k === 3) {
        const halfTwists = geometry.parameter;
        for (const edge of [0, cols]) {
          ctx.strokeStyle =
            halfTwists % 2 || edge === 0 ? "#65318c" : "#1a6d80";
          ctx.lineWidth = 2.2;
          for (let i = 0; i < rows; i++)
            line(pts[i * (cols + 1) + edge], pts[(i + 1) * (cols + 1) + edge]);
        }
      }
      ctx.globalAlpha = 1;
      return;
    }
    const faces = geometry.faces
      .map((f) => [f, f.ids.reduce((n, i) => n + pts[i][2], 0)])
      .sort((a, b) => a[1] - b[1]);
    const base = objects[k][2];
    ctx.lineWidth = 0.62;
    ctx.lineJoin = "round";
    for (const [f] of faces) {
      let [x, y, z] = rot(f.normal);
      if (z < 0) {
        x = -x;
        y = -y;
        z = -z;
      }
      const rx = 2 * z * x,
        ry = 2 * z * y,
        rz = 2 * z * z - 1;
      const band = exp(-((ry + 0.39 * rx + 0.42) ** 2) / 0.038),
        rim = exp(-((rx - 0.68) ** 2) / 0.022) * (0.6 + 0.4 * rz);
      const shine = Math.min(
          0.97,
          0.76 * band + 0.63 * rim + 0.36 * (1 - z) ** 3,
        ),
        light = 0.41 + 0.51 * z - 0.23 * y - 0.11 * x;
      ctx.fillStyle =
        ctx.strokeStyle = `rgb(${base.map((c) => Math.round(c * light * (1 - shine) + 252 * shine)).join(",")})`;
      ctx.beginPath();
      f.ids.forEach((id, j) => {
        const p = pts[id];
        if (j) ctx.lineTo(p[0], p[1]);
        else ctx.moveTo(p[0], p[1]);
      });
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    }
  }
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  let k = 0,
    yaw = 0.34,
    pitch = 0.62,
    playing = !reduced.matches,
    drag = false,
    visible = true,
    timer;
  const paint = () => draw(live, k, yaw, pitch);
  function schedule() {
    clearInterval(timer);
    if (playing && visible && !document.hidden && !drag && !$("notebook").open)
      timer = setInterval(() => {
        yaw += 0.009;
        paint();
      }, 60);
  }
  function state() {
    $("pause").textContent = playing ? "Ⅱ" : "▷";
    $("pause").setAttribute(
      "aria-label",
      playing ? "Pause rotation" : "Play rotation",
    );
    schedule();
  }
  const slider = $("parameter");
  function measurement(index, value) {
    return [
      () => `Tube diameter · ${(2 * value).toFixed(2)} units`,
      () => `Crest spacing · ${(360 / value).toFixed(1)}°`,
      () => `Rise per turn · ${(2.5 / value).toFixed(2)} units`,
      () =>
        value % 2 ? "One side · one boundary" : "Two sides · two boundaries",
    ][index]();
  }
  function configureParameter() {
    const spec = chapters[k].dataset;
    $("parameter-label").textContent = spec.parameter;
    slider.min = spec.min;
    slider.max = spec.max;
    slider.step = spec.step;
    slider.value = spec.initial;
    $("parameter-value").value = slider.value;
    $("derived").textContent = measurement(k, slider.valueAsNumber);
    variant = meshes[k];
  }
  slider.oninput = () => {
    $("parameter-value").value = slider.value;
    $("derived").textContent = measurement(k, slider.valueAsNumber);
    variant = mesh(k, slider.valueAsNumber);
    paint();
  };
  function setMode(wire) {
    meshMode = wire;
    $("solid").setAttribute("aria-pressed", String(!wire));
    $("wire").setAttribute("aria-pressed", String(wire));
    paint();
  }
  $("solid").onclick = () => setMode(false);
  $("wire").onclick = () => setMode(true);
  $("reset-view").onclick = () => {
    choose(k);
    setMode(false);
  };
  configureParameter();
  function choose(i) {
    k = (i + objects.length) % objects.length;
    configureParameter();
    yaw = 0.34;
    pitch = 0.62;
    $("study-link").hash = chapters[k].id;
    $("model").textContent = objects[k][0];
    $("num").textContent = `OBJECT — 00${k + 1}`;
    live.parentElement.style.setProperty("--tint", objects[k][1]);
    paint();
  }
  document.querySelectorAll(".inspect").forEach(
    (button) =>
      (button.onclick = () => {
        choose(Number(button.dataset.object));
        live.focus({ preventScroll: true });
        live.scrollIntoView({ block: "center" });
      }),
  );
  $("prev").onclick = () => choose(k - 1);
  $("next").onclick = () => choose(k + 1);
  $("pause").onclick = () => {
    playing = !playing;
    state();
  };
  // Two compact parameter records, not persistent image blobs. Recreate each
  // plate from its saved pose so revisiting it is independent of canvas size.
  const book = $("notebook"),
    slots = [...book.querySelectorAll(".book-slot")],
    storageKey = "form-atlas.notebook.v1";
  let plates = [null, null];
  function valid(p) {
    const i = chapters.findIndex((ch) => ch.id === p?.slug);
    if (i < 0) return false;
    const spec = chapters[i].dataset;
    return (
      Number.isFinite(p.value) &&
      p.value >= Number(spec.min) &&
      p.value <= Number(spec.max) &&
      [p.yaw, p.pitch].every(Number.isFinite) &&
      typeof p.wire === "boolean"
    );
  }
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    if (Array.isArray(saved?.plates))
      plates = plates.map((_, i) =>
        valid(saved.plates[i]) ? saved.plates[i] : null,
      );
    if (typeof saved?.note === "string")
      $("observation").value = saved.note.slice(0, 500);
  } catch {
    /* Private browsing and old data do not block the studio. */
  }
  function persist(message) {
    try {
      localStorage.setItem(
        storageKey,
        JSON.stringify({ plates, note: $("observation").value }),
      );
      $("book-status").textContent = message + " · Saved in this browser.";
    } catch {
      $("book-status").textContent =
        message + " · Session only; storage unavailable.";
    }
  }
  const objIndex = (p) => chapters.findIndex((ch) => ch.id === p.slug);
  function refreshBook() {
    slots.forEach((slot, i) => {
      const p = plates[i];
      slot.classList.toggle("filled", !!p);
      slot.querySelector(".restore").disabled = slot.querySelector(
        ".remove",
      ).disabled = !p;
      slot.querySelector(".capture").textContent =
        (p ? "Replace " : "Capture ") + (i ? "B" : "A");
      slot.querySelector("strong").textContent = p
        ? objects[objIndex(p)][0]
        : "Empty plate";
      const j = p ? objIndex(p) : 0;
      slot.querySelector(".settings-line").textContent = p
        ? `${chapters[j].dataset.parameter}: ${p.value} · ${p.wire ? "Mesh" : "Solid"}`
        : "Ready for a studio view.";
      slot.style.setProperty("--tint", p ? objects[j][1] : "#f0f0ea");
      if (p)
        draw(
          slot.querySelector("canvas"),
          j,
          p.yaw,
          p.pitch,
          mesh(j, p.value),
          p.wire,
        );
    });
    const [a, b] = plates;
    $("difference").textContent =
      !a || !b
        ? "Capture two plates to compare their settings."
        : a.slug === b.slug
          ? `A → B: ${measurement(objIndex(a), a.value)} → ${measurement(objIndex(b), b.value)}.`
          : `A: ${measurement(objIndex(a), a.value)}. B: ${measurement(objIndex(b), b.value)}. Different forms use different measures.`;
    $("download-plate").disabled = !a && !b;
  }
  slots.forEach((slot, i) => {
    slot.querySelector(".capture").onclick = () => {
      playing = false;
      state();
      plates[i] = {
        slug: chapters[k].id,
        value: slider.valueAsNumber,
        wire: meshMode,
        yaw,
        pitch,
      };
      refreshBook();
      persist(`Plate ${i ? "B" : "A"} captured`);
    };
    slot.querySelector(".remove").onclick = () => {
      plates[i] = null;
      refreshBook();
      persist("Plate cleared");
      slot.querySelector(".capture").focus();
    };
    slot.querySelector(".restore").onclick = () => {
      const p = plates[i];
      choose(objIndex(p));
      slider.value = p.value;
      slider.oninput();
      yaw = p.yaw;
      pitch = p.pitch;
      playing = false;
      setMode(p.wire);
      book.close();
      state();
      live.focus();
    };
  });
  $("open-notebook").onclick = () => {
    book.showModal();
    schedule();
    refreshBook();
  };
  $("close-notebook").onclick = () => book.close();
  book.addEventListener("close", schedule);
  $("observation").addEventListener("input", () =>
    persist("Observation updated"),
  );
  new ResizeObserver(() => {
    if (book.open) refreshBook();
  }).observe(book);
  $("download-plate").onclick = () => {
    const canvas = document.createElement("canvas");
    canvas.width = 1200;
    const ctx = canvas.getContext("2d");
    ctx.font = "18px sans-serif";
    const lines = [];
    let line = "";
    for (const char of $("observation").value) {
      if (char === "\n" || ctx.measureText(line + char).width > 1100) {
        lines.push(line);
        line = "";
      }
      if (char !== "\n") line += char;
    }
    lines.push(line);
    canvas.height = Math.max(720, 670 + 25 * lines.length);
    ctx.fillStyle = "#faf9f5";
    ctx.fillRect(0, 0, 1200, canvas.height);
    ctx.fillStyle = "#25271f";
    ctx.font = "18px monospace";
    ctx.fillText("FORM ATLAS   /   FIELD RECORD", 44, 48);
    ctx.font = "48px Georgia";
    ctx.fillText("Comparative study", 44, 112);
    slots.forEach((slot, i) => {
      const x = 44 + i * 574,
        p = plates[i];
      ctx.fillStyle = p ? objects[objIndex(p)][1] : "#ecece6";
      ctx.fillRect(x, 150, 540, 290);
      ctx.fillStyle = "#282a26";
      ctx.font = "16px monospace";
      ctx.fillText("PLATE " + (i ? "B" : "A"), x + 15, 180);
      if (!p) return;
      const source = slot.querySelector("canvas"),
        ratio = Math.min(540 / source.width, 260 / source.height);
      ctx.drawImage(
        source,
        x + (540 - source.width * ratio) / 2,
        175 + (260 - source.height * ratio) / 2,
        source.width * ratio,
        source.height * ratio,
      );
      ctx.font = "bold 22px sans-serif";
      ctx.fillText(slot.querySelector("strong").textContent, x, 480);
      ctx.font = "17px sans-serif";
      ctx.fillText(slot.querySelector(".settings-line").textContent, x, 510);
      ctx.fillText(measurement(objIndex(p), p.value), x, 539);
    });
    ctx.fillStyle = "#25271f";
    ctx.font = "17px monospace";
    ctx.fillText("OBSERVATION", 44, 601);
    ctx.font = "18px sans-serif";
    lines.forEach((line, i) => ctx.fillText(line, 44, 638 + 25 * i));
    canvas.toBlob((blob) => {
      if (!blob) return;
      const url = URL.createObjectURL(blob),
        link = document.createElement("a");
      link.href = url;
      link.download = "form-atlas-study.png";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    }, "image/png");
  };

  let px, py;
  live.onpointerdown = (e) => {
    px = e.clientX;
    py = e.clientY;
    drag = true;
    live.setPointerCapture(e.pointerId);
    schedule();
  };
  live.onpointermove = (e) => {
    if (!drag) return;
    yaw += (e.clientX - px) * 0.012;
    pitch += (e.clientY - py) * 0.012;
    px = e.clientX;
    py = e.clientY;
    paint();
  };
  live.onlostpointercapture = () => {
    drag = false;
    schedule();
  };
  live.onkeydown = (e) => {
    const moves = {
      ArrowLeft: [-0.12, 0],
      ArrowRight: [0.12, 0],
      ArrowUp: [0, -0.12],
      ArrowDown: [0, 0.12],
    };
    if (moves[e.key]) {
      e.preventDefault();
      yaw += moves[e.key][0];
      pitch += moves[e.key][1];
      paint();
    }
  };
  new ResizeObserver(paint).observe(live);
  new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting;
    schedule();
  }).observe(live);
  document.addEventListener("visibilitychange", schedule);
  reduced.onchange = () => {
    playing = !reduced.matches;
    state();
  };
  state();
  const links = [
    ...document.querySelectorAll('nav[aria-label="Gallery sections"] a'),
  ];
  const sections = links.map((link) => document.querySelector(link.hash));
  const study = $("study"),
    plate = study.parentElement,
    progress = document.querySelector(".progress");
  const desktop = matchMedia("(min-width: 761px)");
  let pending = false,
    lastPose = "",
    activeStudy = -1;
  function updateScroll() {
    pending = false;
    const range = document.documentElement.scrollHeight - innerHeight;
    const fraction = Math.min(1, Math.max(0, scrollY / Math.max(1, range)));
    progress.style.transform = `scaleX(${fraction})`;
    let section = 0;
    sections.forEach((s, i) => {
      if (s.getBoundingClientRect().top <= 150) section = i;
    });
    if (fraction >= 0.999) section = sections.length - 1;
    links.forEach((link, i) =>
      i === section
        ? link.setAttribute("aria-current", "location")
        : link.removeAttribute("aria-current"),
    );
    if (!desktop.matches) return;
    const bounds = plate.getBoundingClientRect();
    if (bounds.bottom < 0 || bounds.top > innerHeight) return;
    const center = bounds.top + bounds.height / 2;
    const rects = chapters.map((ch) => ch.getBoundingClientRect());
    const i = Math.max(
      0,
      rects.findLastIndex((rect) => rect.top <= center),
    );
    const r = rects[i],
      t = Math.min(1, Math.max(0, (center - r.top) / r.height));
    const pose = reduced.matches ? 0 : Math.round(t * 40);
    const key = `${i}/${pose}/${study.clientWidth}/${study.clientHeight}`;
    if (lastPose === key) return;
    if (activeStudy !== i) {
      plate.style.setProperty("--tint", objects[i][1]);
      $("plate-num").textContent = `00${i + 1}`;
      $("plate-caption").textContent = objects[i][0];
      activeStudy = i;
    }
    draw(study, i, 0.34 + pose * 0.018, 0.62);
    lastPose = key;
  }
  function queueScroll() {
    if (!pending) {
      pending = true;
      requestAnimationFrame(updateScroll);
    }
  }
  window.addEventListener("scroll", queueScroll, { passive: true });
  new ResizeObserver(queueScroll).observe(document.body);
  window.addEventListener("resize", queueScroll);
  desktop.addEventListener("change", queueScroll);
  reduced.addEventListener("change", queueScroll);
  queueScroll();
})();
