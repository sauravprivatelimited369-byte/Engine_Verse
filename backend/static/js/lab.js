/* ===========================================================================
   EngineVerse Adaptive Lab.

   The whole learning loop lives here and nowhere else:

       Learn -> Experiment -> Predict -> Verify -> Improve

   There is no server call, no API key and no model. Every number on the page
   comes from Ohm's law computed in this file, and every piece of feedback comes
   from a rule in DIAGNOSE below that names the specific step the learner got
   wrong. If no rule matches, the learner is told the working rather than being
   handed a guess about what they did.

   The file is written so that the maths can be exercised without a browser:
   every pure function hangs off window.EngineVerseLab and scripts/check_lab.js
   runs them under Node against a fixed answer key.

   Progress is written to localStorage under STORAGE_KEY and nothing else. It
   never leaves this device, and every surface that reads it says so.
   =========================================================================== */
(function () {
  "use strict";

  var Lab = (window.EngineVerseLab = window.EngineVerseLab || {});
  var STORAGE_KEY = "engineverse.lab.v1";

  /* --------------------------------------------------------------- maths */

  /** Current through a resistor, in amperes. Infinity for a short circuit. */
  Lab.current = function (volts, ohms) {
    if (!(ohms > 0)) return Infinity;
    return volts / ohms;
  };

  /** Power dissipated, in watts. P = V x I. */
  Lab.power = function (volts, amps) {
    return volts * amps;
  };

  /**
   * The full state of a one-resistor DC circuit. One source of truth: the SVG,
   * the readouts and the answer key are all rendered from this object, so the
   * display can never disagree with the maths.
   */
  Lab.solve = function (volts, ohms) {
    var amps = Lab.current(volts, ohms);
    var watts = Lab.power(volts, amps);
    return {
      v: volts,
      r: ohms,
      i: amps,
      p: watts,
      iText: Lab.ampsText(amps),
      pText: Lab.wattsText(watts),
      shorted: !isFinite(amps),
    };
  };

  /** Round to at most `places` decimals, then drop trailing zeros. */
  Lab.round = function (value, places) {
    if (!isFinite(value)) return value;
    var factor = Math.pow(10, places === undefined ? 3 : places);
    return Math.round(value * factor) / factor;
  };

  /** 0.002 A reads better as 2 mA. Engineers write it that way, so we do too. */
  Lab.ampsText = function (amps) {
    if (!isFinite(amps)) return "\u221e";
    if (amps !== 0 && Math.abs(amps) < 1) {
      return Lab.round(amps * 1000, 1) + " mA";
    }
    return Lab.round(amps, 3) + " A";
  };

  Lab.wattsText = function (watts) {
    if (!isFinite(watts)) return "\u221e";
    if (watts !== 0 && Math.abs(watts) < 1) {
      return Lab.round(watts * 1000, 1) + " mW";
    }
    return Lab.round(watts, 3) + " W";
  };

  /** Two resistors in series / parallel, in ohms. */
  Lab.series = function (a, b) { return a + b; };
  Lab.parallel = function (a, b) {
    if (a + b === 0) return 0;
    return (a * b) / (a + b);
  };

  /* ------------------------------------------------- mistake detection */
  /*
   * A rule is {id, test(answer, ctx), message(ctx)}. `test` gets the number the
   * learner typed and the circuit, and returns true when the answer matches the
   * arithmetic of that particular mistake. Rules run in order, so the specific
   * ones come first and GENERIC is the fallback.
   *
   * `near` compares with a relative tolerance: a learner who types 2.999 for 3
   * did not make a units error, they rounded.
   */
  function near(a, b, tolerance) {
    if (!isFinite(a) || !isFinite(b)) return false;
    if (a === b) return true;
    var scale = Math.max(Math.abs(a), Math.abs(b));
    if (scale === 0) return true;
    return Math.abs(a - b) / scale <= (tolerance || 0.01);
  }
  Lab.near = near;

  function ohms(ctx) { return ctx.ohms; }

  var FACTORS = [1000, 100, 10, 2, 0.5, 0.1, 0.01, 0.001];

  var CURRENT_RULES = [
    {
      id: "multiplied",
      test: function (ans, ctx) { return near(ans, ctx.volts * ctx.ohms); },
      message: function (ctx) {
        return "You multiplied " + ctx.volts + " V by " + ctx.ohms + " \u03a9 and got " +
          Lab.round(ctx.volts * ctx.ohms, 3) + ". Current is voltage divided by resistance: " +
          "I = V / R = " + ctx.volts + " / " + ctx.ohms + " = " + Lab.ampsText(ctx.truth) + ".";
      },
    },
    {
      id: "inverted",
      test: function (ans, ctx) { return ctx.volts !== 0 && near(ans, ctx.ohms / ctx.volts); },
      message: function (ctx) {
        return "You divided the wrong way round and got R / V = " + ctx.ohms + " / " + ctx.volts +
          ". Ohm's law reads I = V / R, so the voltage goes on top: " + ctx.volts + " / " +
          ctx.ohms + " = " + Lab.ampsText(ctx.truth) + ".";
      },
    },
    {
      id: "milliamps",
      test: function (ans, ctx) { return near(ans, ctx.truth * 1000); },
      message: function (ctx) {
        return "That number is right but it is in milliamps. " + Lab.round(ctx.truth * 1000, 3) +
          " mA = " + Lab.ampsText(ctx.truth) + ". Divide by 1000 to go from mA to A.";
      },
    },
    {
      id: "kiloamps",
      test: function (ans, ctx) { return near(ans, ctx.truth / 1000); },
      message: function (ctx) {
        return "That looks like kiloamps. " + Lab.round(ctx.truth / 1000, 4) + " kA = " +
          Lab.ampsText(ctx.truth) + ". Multiply by 1000 to go from kA to A.";
      },
    },
    {
      id: "used-power",
      test: function (ans, ctx) { return near(ans, ctx.volts * ctx.volts / ctx.ohms); },
      message: function (ctx) {
        return "You used the power formula. V\u00b2 / R = " +
          Lab.round(ctx.volts * ctx.volts / ctx.ohms, 3) + " is watts, not amps. " +
          "For current use I = V / R = " + ctx.volts + " / " + ctx.ohms + " = " +
          Lab.ampsText(ctx.truth) + ".";
      },
    },
    {
      id: "ohm-resistance",
      test: function (ans, ctx) { return near(ans, ctx.ohms); },
      message: function (ctx) {
        return "You wrote the resistance (" + ctx.ohms + " \u03a9) as the answer. The question asks " +
          "for the current: I = V / R = " + ctx.volts + " / " + ctx.ohms + " = " +
          Lab.ampsText(ctx.truth) + ".";
      },
    },
    {
      id: "factor",
      test: function (ans, ctx) {
        if (ctx.truth === 0 || ans === 0) return false;
        var ratio = ans / ctx.truth;
        return FACTORS.some(function (f) { return near(ratio, f, 0.005); });
      },
      message: function (ctx) {
        var ratio = ctx.truth === 0 ? 0 : ctx.answer / ctx.truth;
        var by = Math.abs(ratio) >= 1
          ? Lab.round(Math.abs(ratio), 2) + "x too big"
          : Lab.round(1 / (Math.abs(ratio) || 1), 2) + "x too small";
        return "Your answer is " + by + ". Check the powers of ten before you divide: " +
          ctx.volts + " V / " + ctx.ohms + " \u03a9 = " + Lab.ampsText(ctx.truth) + ".";
      },
    },
  ];

  var GENERIC = {
    id: "generic",
    message: function (ctx) {
      return "Not quite. Write the formula first, then substitute: I = V / R = " + ctx.volts +
        " V / " + ctx.ohms + " \u03a9 = " + Lab.ampsText(ctx.truth) +
        ". Keep the units next to every number and the mistake usually shows itself.";
    },
  };

  /**
   * Grade one prediction.
   *
   * @param {object} input {ask, volts, ohms, answer}
   *   ask: 'current' | 'voltage' | 'resistance' | 'power'
   *   For voltage/resistance the third value travels in `input.amps`.
   * @returns {{correct: boolean, truth: number, truthText: string,
   *            kind: string, message: string}}
   */
  Lab.diagnose = function (input) {
    var ask = input.ask || "current";
    var volts = Number(input.volts);
    var ohms = Number(input.ohms);
    var amps = Number(input.amps);
    var answer = Number(input.answer);

    var truth, unit, truthText, rules;
    if (ask === "voltage") {
      truth = amps * ohms; unit = "V"; truthText = Lab.round(truth, 3) + " V";
      rules = [
        {
          id: "divided",
          test: function (a) { return ohms !== 0 && near(a, amps / ohms); },
          message: function () {
            return "You divided current by resistance. Voltage is the product: V = I x R = " +
              amps + " A x " + ohms + " \u03a9 = " + truthText + ".";
          },
        },
        {
          id: "millivolts",
          test: function (a) { return near(a, truth * 1000); },
          message: function () {
            return "That is the right number in millivolts. " + Lab.round(truth * 1000, 3) +
              " mV = " + truthText + ".";
          },
        },
      ];
    } else if (ask === "resistance") {
      truth = amps === 0 ? Infinity : volts / amps; unit = "\u03a9";
      truthText = isFinite(truth) ? Lab.round(truth, 3) + " \u03a9" : "undefined (no current)";
      rules = [
        {
          id: "multiplied",
          test: function (a) { return near(a, volts * amps); },
          message: function () {
            return "You multiplied V by I, which gives power in watts. Resistance is " +
              "R = V / I = " + volts + " / " + amps + " = " + truthText + ".";
          },
        },
        {
          id: "inverted",
          test: function (a) { return volts !== 0 && near(a, amps / volts); },
          message: function () {
            return "You divided the wrong way round. R = V / I, so the voltage goes on top: " +
              volts + " / " + amps + " = " + truthText + ".";
          },
        },
        {
          id: "kiloohms",
          test: function (a) { return near(a, truth / 1000); },
          message: function () {
            return "That is the right number in k\u03a9. " + Lab.round(truth / 1000, 4) +
              " k\u03a9 = " + truthText + ".";
          },
        },
      ];
    } else if (ask === "power") {
      truth = volts * volts / ohms; unit = "W"; truthText = Lab.wattsText(truth);
      rules = [
        {
          id: "used-current",
          test: function (a) { return near(a, volts / ohms); },
          message: function () {
            return "That is the current, not the power. I = V / R = " +
              Lab.ampsText(volts / ohms) + ". Power is P = V x I = " + volts + " x " +
              Lab.round(volts / ohms, 3) + " = " + truthText + ".";
          },
        },
        {
          id: "milliwatts",
          test: function (a) { return near(a, truth * 1000); },
          message: function () {
            return "That is the right number in milliwatts. " + Lab.round(truth * 1000, 3) +
              " mW = " + truthText + ".";
          },
        },
        {
          id: "no-square",
          test: function (a) { return near(a, volts / ohms); },
          message: function () {
            return "P = V\u00b2 / R needs the voltage squared, so " + volts + "\u00b2 / " + ohms +
              " = " + truthText + ", not " + volts + " / " + ohms + ".";
          },
        },
      ];
    } else {
      truth = Lab.current(volts, ohms); unit = "A"; truthText = Lab.ampsText(truth);
      rules = CURRENT_RULES;
    }

    var ctx = { volts: volts, ohms: ohms, amps: amps, answer: answer, truth: truth, unit: unit };

    if (isFinite(answer) && near(answer, truth)) {
      return {
        correct: true, truth: truth, truthText: truthText, kind: "correct",
        message: "Correct. " + truthText + " \u2014 " + explain(ask, ctx) + ".",
      };
    }

    for (var index = 0; index < rules.length; index += 1) {
      if (rules[index].test(answer, ctx)) {
        return {
          correct: false, truth: truth, truthText: truthText, kind: rules[index].id,
          message: rules[index].message(ctx),
        };
      }
    }
    if (ask === "current") {
      return {
        correct: false, truth: truth, truthText: truthText, kind: GENERIC.id,
        message: GENERIC.message(ctx),
      };
    }
    return {
      correct: false, truth: truth, truthText: truthText, kind: GENERIC.id,
      message: "Not quite. The answer is " + truthText + ". " + explain(ask, ctx) + ".",
    };
  };

  /** The one-line working for each quantity, used in correct answers and hints. */
  function explain(ask, ctx) {
    if (ask === "voltage") return "V = I x R = " + ctx.amps + " x " + ctx.ohms;
    if (ask === "resistance") return "R = V / I = " + ctx.volts + " / " + ctx.amps;
    if (ask === "power") return "P = V\u00b2 / R = " + ctx.volts + "\u00b2 / " + ctx.ohms;
    return "I = V / R = " + ctx.volts + " / " + ctx.ohms;
  }
  Lab.explain = explain;

  /* --------------------------------------------------------- question bank */
  /*
   * Hand-written, not generated: every entry is a circuit a first-year student
   * would actually meet, and `why` is the explanation shown after a wrong
   * answer. `tag` drives the mistake tracking, `difficulty` drives the
   * sequencing. Answers are derived from the circuit by Lab.diagnose, never
   * typed in, so the bank cannot disagree with the simulator.
   */
  var BANK = [
    // --- formula: straight Ohm's law --------------------------------------
    { id: "f-e1", tag: "formula", difficulty: "easy", ask: "current", volts: 12, ohms: 6,
      prompt: "A 12 V battery drives a single 6 \u03a9 resistor. What current flows?",
      why: "Ohm's law: I = V / R. Twelve volts across six ohms is 2 A." },
    { id: "f-e2", tag: "formula", difficulty: "easy", ask: "current", volts: 9, ohms: 3,
      prompt: "A 9 V supply feeds a 3 \u03a9 resistor. What current flows?",
      why: "I = V / R = 9 / 3 = 3 A. Doubling the voltage doubles the current; doubling R halves it." },
    { id: "f-m1", tag: "formula", difficulty: "medium", ask: "resistance", volts: 12, amps: 0.04,
      prompt: "A 12 V supply drives 40 mA through one resistor. What is its resistance?",
      why: "Rearrange to R = V / I. Convert 40 mA to 0.04 A first: 12 / 0.04 = 300 \u03a9." },
    { id: "f-m2", tag: "formula", difficulty: "medium", ask: "voltage", amps: 0.25, ohms: 220,
      prompt: "250 mA flows through a 220 \u03a9 resistor. What is the voltage across it?",
      why: "V = I x R. 0.25 A x 220 \u03a9 = 55 V." },
    { id: "f-h1", tag: "formula", difficulty: "hard", ask: "current", volts: 5, ohms: 4700,
      prompt: "A 5 V logic rail feeds a 4.7 k\u03a9 pull-up resistor. What current flows?",
      why: "Convert 4.7 k\u03a9 to 4700 \u03a9: 5 / 4700 \u2248 1.06 mA. Small currents are written in mA." },

    // --- units: the mistake first-years actually make ----------------------
    { id: "u-e1", tag: "units", difficulty: "easy", ask: "current", volts: 3.3, ohms: 330,
      prompt: "A 3.3 V microcontroller pin drives an LED through a 330 \u03a9 resistor. What current flows?",
      why: "3.3 / 330 = 0.01 A, which engineers write as 10 mA. Divide by 1000 to go A \u2192 mA." },
    { id: "u-m1", tag: "units", difficulty: "medium", ask: "current", volts: 24, ohms: 1200,
      prompt: "24 V is applied across 1.2 k\u03a9. What current flows, in mA?",
      why: "1.2 k\u03a9 = 1200 \u03a9. 24 / 1200 = 0.02 A = 20 mA." },
    { id: "u-m2", tag: "units", difficulty: "medium", ask: "resistance", volts: 5, amps: 0.002,
      prompt: "A 5 V rail supplies 2 mA. What resistance is drawing it?",
      why: "2 mA = 0.002 A. R = 5 / 0.002 = 2500 \u03a9, which is 2.5 k\u03a9." },
    { id: "u-h1", tag: "units", difficulty: "hard", ask: "power", volts: 12, ohms: 100,
      prompt: "How much power does a 100 \u03a9 resistor dissipate at 12 V?",
      why: "P = V\u00b2 / R = 144 / 100 = 1.44 W. That is why a 0.25 W part would burn out." },

    // --- series: resistance adds ------------------------------------------
    { id: "s-e1", tag: "series", difficulty: "easy", ask: "current", volts: 12, ohms: 6, ohms2: 6,
      prompt: "12 V drives two 6 \u03a9 resistors in series. What current flows?",
      why: "Series resistances add: 6 + 6 = 12 \u03a9, so I = 12 / 12 = 1 A." },
    { id: "s-m1", tag: "series", difficulty: "medium", ask: "current", volts: 9, ohms: 1000, ohms2: 2000,
      prompt: "9 V drives 1 k\u03a9 and 2 k\u03a9 in series. What current flows?",
      why: "1 k\u03a9 + 2 k\u03a9 = 3 k\u03a9 = 3000 \u03a9. I = 9 / 3000 = 3 mA." },
    { id: "s-h1", tag: "series", difficulty: "hard", ask: "voltage", amps: 0.002, ohms: 2200,
      prompt: "2 mA flows through the 2.2 k\u03a9 lower half of a series divider. What voltage is across it?",
      why: "V = I x R = 0.002 x 2200 = 4.4 V. The same current flows through every series element." },

    // --- parallel: conductance adds ---------------------------------------
    { id: "p-m1", tag: "parallel", difficulty: "medium", ask: "current", volts: 12, ohms: 12, ohms2: 12,
      prompt: "12 V drives two 12 \u03a9 resistors in parallel. What total current flows?",
      why: "Two equal resistors in parallel halve: 12 || 12 = 6 \u03a9. I = 12 / 6 = 2 A." },
    { id: "p-h1", tag: "parallel", difficulty: "hard", ask: "current", volts: 24, ohms: 60, ohms2: 30,
      prompt: "24 V drives 60 \u03a9 in parallel with 30 \u03a9. What total current flows?",
      why: "60 || 30 = (60 x 30) / 90 = 20 \u03a9. I = 24 / 20 = 1.2 A. Adding a branch always lowers R." },

    // --- power ------------------------------------------------------------
    { id: "w-e1", tag: "power", difficulty: "easy", ask: "power", volts: 12, ohms: 6,
      prompt: "A 6 \u03a9 resistor sits across 12 V. How much power does it dissipate?",
      why: "P = V x I = 12 x 2 = 24 W, or V\u00b2 / R = 144 / 6 = 24 W. Both give the same answer." },
    { id: "w-m1", tag: "power", difficulty: "medium", ask: "power", volts: 5, ohms: 250,
      prompt: "How much power does a 250 \u03a9 resistor dissipate at 5 V?",
      why: "P = V\u00b2 / R = 25 / 250 = 0.1 W = 100 mW." },
  ];

  Lab.BANK = BANK;
  Lab.byId = function (id) {
    for (var i = 0; i < BANK.length; i += 1) if (BANK[i].id === id) return BANK[i];
    return null;
  };

  /** Total resistance of a question: one resistor, or the pair combined. */
  Lab.totalOhms = function (question) {
    if (!question.ohms2) return question.ohms;
    return question.tag === "parallel"
      ? Lab.parallel(question.ohms, question.ohms2)
      : Lab.series(question.ohms, question.ohms2);
  };

  /** The answer key entry for a question, computed from the circuit. */
  Lab.answerFor = function (question) {
    return Lab.diagnose({
      ask: question.ask, volts: question.volts,
      ohms: Lab.totalOhms(question), amps: question.amps, answer: NaN,
    });
  };

  Lab.TAG_LABEL = {
    formula: "Ohm's law", units: "Units and prefixes", series: "Series circuits",
    parallel: "Parallel circuits", power: "Power",
  };

  var LEVELS = ["easy", "medium", "hard"];
  Lab.LEVELS = LEVELS;

  /* ------------------------------------------------------- sequencing */

  /**
   * Pick the next question.
   *
   * Right answer: move up a level. Wrong answer: drop a level AND stay on the
   * tag that was just missed, so the learner gets an easier question about the
   * same thing rather than a random one.
   *
   * @param {object} state {level, focus, answered: {id: {correct, kind}}}
   * @returns {object|null} a bank entry, or null when nothing is left.
   */
  Lab.pickNext = function (state) {
    var level = LEVELS.indexOf(state.level) < 0 ? "easy" : state.level;
    var pool = BANK.filter(function (q) { return !(state.answered && state.answered[q.id]); });
    if (!pool.length) return null;

    var wanted = pool.filter(function (q) {
      return q.difficulty === level && (!state.focus || q.tag === state.focus);
    });
    if (wanted.length) return wanted[0];

    // No question at that exact level and tag: relax the tag first, then walk
    // the levels outward from where the learner is. A learner must never be
    // shown "nothing left" while unanswered questions exist.
    var byTag = pool.filter(function (q) { return !state.focus || q.tag === state.focus; });
    var candidates = byTag.length ? byTag : pool;
    var at = LEVELS.indexOf(level);
    var ordered = LEVELS.slice().sort(function (a, b) {
      return Math.abs(LEVELS.indexOf(a) - at) - Math.abs(LEVELS.indexOf(b) - at);
    });
    for (var i = 0; i < ordered.length; i += 1) {
      var found = candidates.filter(function (q) { return q.difficulty === ordered[i]; });
      if (found.length) return found[0];
    }
    return candidates[0];
  };

  /** One level harder / easier, clamped to the ends of the ladder. */
  Lab.stepLevel = function (level, direction) {
    var at = LEVELS.indexOf(level);
    if (at < 0) at = 0;
    var next = Math.min(LEVELS.length - 1, Math.max(0, at + direction));
    return LEVELS[next];
  };

  /**
   * "What to learn next", from the mistakes actually recorded.
   * Returns {tag, label, message} or null when there is nothing to say.
   */
  Lab.recommend = function (tags) {
    var worst = null;
    Object.keys(tags || {}).forEach(function (key) {
      var entry = tags[key];
      if (!entry || !entry.wrong) return;
      if (!worst || entry.wrong > tags[worst].wrong) worst = key;
    });
    if (!worst) return null;
    var seen = tags[worst].seen || 0;
    var wrong = tags[worst].wrong;
    var label = Lab.TAG_LABEL[worst] || worst;
    var advice = {
      formula: "Re-read Ohm's law and write I = V / R before substituting anything. ",
      units: "Practise converting A \u2194 mA and \u03a9 \u2194 k\u03a9 before you substitute. ",
      series: "Revise series circuits: resistances add, and the same current flows through each. ",
      parallel: "Revise parallel circuits: conductances add, so total resistance always falls. ",
      power: "Revise P = V x I = V\u00b2 / R, and check you squared the voltage. ",
    }[worst] || "Revise " + label.toLowerCase() + ". ";
    return {
      tag: worst, label: label, wrong: wrong,
      message: advice + "You missed " + wrong + " of " + seen + " " + label.toLowerCase() +
        " questions. Try " + (wrong > 1 ? 2 : 1) + " more easy " + label.toLowerCase() +
        (wrong > 1 ? " questions" : " question") + " before moving on.",
    };
  };

  /* ------------------------------------------------------------ storage */
  /*
   * localStorage only. A blocked or full store is a normal condition (private
   * browsing, a locked-down lab machine), so every call is wrapped and the
   * page says plainly that progress is not being kept.
   */
  function emptyState() {
    return {
      version: 1, savedAt: 0, attempts: 0, correct: 0,
      level: "easy", tags: {}, sessions: [], best: 0,
    };
  }

  Lab.storageAvailable = (function () {
    try {
      var probe = "__ev_probe__";
      window.localStorage.setItem(probe, "1");
      window.localStorage.removeItem(probe);
      return true;
    } catch (_) {
      return false;
    }
  })();

  Lab.load = function () {
    if (!Lab.storageAvailable) return emptyState();
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return emptyState();
      var parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object") return emptyState();
      var state = emptyState();
      state.attempts = Number(parsed.attempts) || 0;
      state.correct = Number(parsed.correct) || 0;
      state.best = Number(parsed.best) || 0;
      state.level = LEVELS.indexOf(parsed.level) >= 0 ? parsed.level : "easy";
      state.savedAt = Number(parsed.savedAt) || 0;
      state.tags = (parsed.tags && typeof parsed.tags === "object") ? parsed.tags : {};
      state.sessions = Array.isArray(parsed.sessions) ? parsed.sessions.slice(-10) : [];
      return state;
    } catch (_) {
      return emptyState();
    }
  };

  Lab.save = function (state) {
    if (!Lab.storageAvailable) return false;
    try {
      state.savedAt = Date.now();
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
      return true;
    } catch (_) {
      Lab.storageAvailable = false;
      return false;
    }
  };

  Lab.clear = function () {
    if (!Lab.storageAvailable) return false;
    try { window.localStorage.removeItem(STORAGE_KEY); return true; } catch (_) { return false; }
  };

  /** Accuracy as a whole percent, or null when nothing has been attempted. */
  Lab.accuracy = function (state) {
    if (!state || !state.attempts) return null;
    return Math.round((state.correct / state.attempts) * 100);
  };

  /* --------------------------------------------------------- circuit SVG */

  /**
   * The circuit diagram: a battery, a resistor and the wires between them.
   * Rendered from the solved state, so the labels always match the readouts.
   * The flow animation is a dashed stroke offset; the stylesheet switches it
   * off under prefers-reduced-motion.
   */
  /**
   * The circuit diagram: a battery, one or two resistors and the wires between
   * them. Rendered from the solved state, so the labels always match the
   * readouts and the answer key.
   *
   * options.resistors  [a] or [a, b]  - the values to draw, in ohms
   * options.arrangement 'series' | 'parallel' - how two resistors are wired
   * options.showPower  also print P on the diagram
   *
   * The flow animation is a dashed stroke offset; the stylesheet stops it under
   * prefers-reduced-motion, and a shorted circuit does not animate at all.
   */
  Lab.circuitSVG = function (state, options) {
    var opts = options || {};
    var values = (opts.resistors && opts.resistors.length) ? opts.resistors : [state.r];
    var arrangement = values.length > 1 ? (opts.arrangement || "series") : "single";
    var described = values.map(function (v) { return v + " \u03a9"; })
      .join(arrangement === "parallel" ? " in parallel with " : arrangement === "series" ? " in series with " : "");
    var speed = Math.min(4, Math.max(0.25, Math.abs(state.i) / 1.5));
    var flowing = !state.shorted && state.iText !== "?";
    var parts = [
      '<svg class="ev-circuit" viewBox="0 0 320 150" role="img" aria-label="',
      'Series circuit: a ', state.v, ' volt battery driving ', described,
      ', carrying ', state.iText, '">',
      '<title>', state.v, ' V across ', described, ' \u2014 ', state.iText, '</title>',
      '<g class="ev-wire">',
      '<path class="ev-wire-base" d="M60 30 H260 V120 H60 Z" fill="none"/>',
      '<path class="ev-wire-flow" d="M60 30 H260 V120 H60 Z" fill="none" style="',
      flowing ? 'animation-duration:' + (2.4 / speed).toFixed(2) + 's' : 'animation:none', '"/>',
      '</g>',
      '<g class="ev-battery" transform="translate(60 75)">',
      '<rect x="-13" y="-19" width="26" height="38" rx="3"/>',
      '<path d="M-5 -8 H5 M0 -13 V-3 M-5 8 H5" stroke-linecap="round"/>',
      '</g>',
      '<text class="ev-label" x="34" y="80" text-anchor="end">', state.v, ' V</text>',
    ];

    if (arrangement === "parallel") {
      // Two vertical branches between the top and bottom rails.
      [120, 200].forEach(function (x, index) {
        parts.push(
          '<g class="ev-resistor" transform="translate(' + x + ' 75) rotate(90)">',
          '<rect x="-30" y="-11" width="60" height="22" rx="3"/>',
          '<path d="M-22 0 h6 l4 -6 l6 12 l6 -12 l6 12 l4 -6 h6" fill="none"/>',
          '</g>',
          '<path class="ev-wire-base" d="M' + x + ' 30 V45 M' + x + ' 105 V120" fill="none"/>',
          '<text class="ev-label" x="' + x + '" y="22" text-anchor="middle">', values[index], ' \u03a9</text>'
        );
      });
    } else {
      var centres = values.length > 1 ? [120, 200] : [160];
      centres.forEach(function (x, index) {
        parts.push(
          '<g class="ev-resistor" transform="translate(' + x + ' 30)">',
          '<rect x="-32" y="-11" width="64" height="22" rx="3"/>',
          '<path d="M-24 0 h6 l4 -6 l6 12 l6 -12 l6 12 l4 -6 h6" fill="none"/>',
          '</g>',
          '<text class="ev-label" x="' + x + '" y="10" text-anchor="middle">', values[index], ' \u03a9</text>'
        );
      });
    }

    parts.push('<text class="ev-label ev-label-strong" x="160" y="142" text-anchor="middle">I = ', state.iText, '</text>');
    if (opts.showPower) {
      parts.push('<text class="ev-label" x="292" y="80" text-anchor="end">P = ', state.pText, '</text>');
    }
    parts.push("</svg>");
    return parts.join("");
  };

  /* --------------------------------------------------------------- UI */

  function $(selector, root) { return (root || document).querySelector(selector); }
  function $$(selector, root) { return Array.prototype.slice.call((root || document).querySelectorAll(selector)); }
  function on(element, event, handler) { if (element) element.addEventListener(event, handler); }
  function text(element, value) { if (element) element.textContent = value; }
  function hidden(element, isHidden) { if (element) element.hidden = !!isHidden; }

  function parseNumber(value) {
    if (value === null || value === undefined) return NaN;
    var cleaned = String(value).trim().toLowerCase()
      .replace(/[^0-9eE.\-+]/g, "")
      .replace(/([0-9])e([+\-]?[0-9])/, "$1e$2");
    if (cleaned === "" || cleaned === "-" || cleaned === ".") return NaN;
    return Number(cleaned);
  }
  Lab.parseNumber = parseNumber;

  /** Mount the compact simulator. Used on the home page and on /lab. */
  Lab.mountMini = function (root) {
    if (!root || root.dataset.evLabReady === "1") return null;
    root.dataset.evLabReady = "1";
    var volts = 12, ohms = 6;

    // The figure lives inside `root`; on /lab the sliders and readouts sit in a
    // sibling column, so fall back to the document for anything not found here.
    function find(selector) { return $(selector, root) || $(selector); }

    function render() {
      var state = Lab.solve(volts, ohms);
      var figure = find("[data-lab-figure]");
      if (figure) figure.innerHTML = Lab.circuitSVG(state, { showPower: true });
      text(find("[data-lab-v]"), state.v + " V");
      text(find("[data-lab-r]"), state.r + " \u03a9");
      text(find("[data-lab-i]"), state.iText);
      text(find("[data-lab-p]"), state.pText);
      var bar = find("[data-lab-bar]");
      if (bar) {
        var share = Math.min(1, Math.abs(state.i) / 4);
        bar.style.width = (share * 100).toFixed(1) + "%";
        var progress = bar.parentNode;
        if (progress && progress.setAttribute) {
          progress.setAttribute("aria-valuenow", Lab.round(state.i * 1000, 1));
          progress.setAttribute("aria-valuetext", state.iText);
        }
      }
    }

    var vSlider = find("[data-lab-volts]");
    var rSlider = find("[data-lab-ohms]");
    on(vSlider, "input", function () { volts = Number(vSlider.value) || 0; render(); });
    on(rSlider, "input", function () { ohms = Number(rSlider.value) || 1; render(); });
    render();
    return { render: render };
  };

  /* ---------------------------------------------------- prediction mode */
  /*
   * Three fixed challenges. The learner types a prediction and it is locked
   * in *before* the answer is revealed - the input is disabled on submit, so
   * the page cannot be accused of grading an answer that was edited after the
   * fact.
   */
  var CHALLENGES = [
    {
      id: "c1", volts: 12, ohms: 6, ask: "current",
      prompt: "A 12 V battery is connected across a 6 \u03a9 resistor. Predict the current before you reveal it.",
      hint: "I = V / R",
    },
    {
      id: "c2", volts: 12, ohms: 4, ask: "current",
      prompt: "Same battery, but the resistor is swapped for 4 \u03a9. Predict the new current.",
      hint: "Lower resistance, higher current",
    },
    {
      id: "c3", volts: 24, ohms: 1200, ask: "current",
      prompt: "Now 24 V across 1.2 k\u03a9. Predict the current, in milliamps.",
      hint: "1.2 k\u03a9 = 1200 \u03a9",
    },
  ];
  Lab.CHALLENGES = CHALLENGES;

  function mountPredict(root) {
    var cards = $$("[data-challenge]", root);
    var live = $("#ev-predict-live", root);
    var tally = $("[data-predict-tally]", root);
    var answered = 0;
    var right = 0;

    function updateTally() {
      if (!tally) return;
      text(tally, answered === 0
        ? "No predictions locked in yet."
        : right + " of " + answered + " predictions correct.");
    }

    cards.forEach(function (card) {
      var challenge = CHALLENGES.filter(function (c) { return c.id === card.dataset.challenge; })[0];
      if (!challenge) return;
      var figure = $("[data-challenge-figure]", card);
      var input = $("input", card);
      var submit = $("[data-challenge-submit]", card);
      var reveal = $("[data-challenge-reveal]", card);
      var feedback = $("[data-challenge-feedback]", card);
      var verdict = $("[data-challenge-verdict]", card);

      // The circuit is drawn with the answer covered: the current label is
      // hidden until the learner has committed to a number.
      var covered = Lab.solve(challenge.volts, challenge.ohms);
      covered.iText = "?";
      covered.pText = "?";
      if (figure) figure.innerHTML = Lab.circuitSVG(covered, { id: challenge.id });

      on(submit, "click", function () {
        var answer = parseNumber(input && input.value);
        if (!isFinite(answer)) {
          input.setAttribute("aria-invalid", "true");
          input.focus();
          text(feedback, "Enter a number first \u2014 a guess you can be wrong about is the point.");
          hidden(reveal, true);
          if (live) live.textContent = "Enter a number before checking.";
          return;
        }
        input.setAttribute("aria-invalid", "false");
        var result = Lab.diagnose({
          ask: challenge.ask, volts: challenge.volts,
          ohms: challenge.ohms, answer: answer,
        });
        // Lock the prediction in: no editing after the reveal.
        input.readOnly = true;
        submit.disabled = true;
        hidden(reveal, false);
        var revealed = Lab.solve(challenge.volts, challenge.ohms);
        var revealFigure = $("[data-challenge-revealed]", card);
        if (revealFigure) revealFigure.innerHTML = Lab.circuitSVG(revealed, { id: challenge.id + "-r", showPower: true });

        var unitLabel = challenge.ask === "current" ? "A (or mA)" : "";
        text(verdict, result.correct ? "Correct" : "Not quite");
        verdict.className = "ev-verdict " + (result.correct ? "is-right" : "is-wrong");
        feedback.innerHTML = "";
        var message = document.createElement("p");
        message.className = "ev-feedback-line";
        message.textContent = result.message;
        feedback.appendChild(message);
        var working = document.createElement("p");
        working.className = "ev-feedback-working";
        working.textContent = "Your prediction: " + Lab.round(answer, 4) +
          (unitLabel ? " " + unitLabel : "") + " \u00b7 Actual: " + result.truthText;
        feedback.appendChild(working);
        if (live) {
          live.textContent = "Challenge " + (cards.indexOf(card) + 1) + ": " +
            (result.correct ? "correct." : "not quite.") + " " + result.message;
        }
        answered += 1;
        if (result.correct) right += 1;
        updateTally();
      });
      updateTally();
    });
  }

  /* ---------------------------------------------------- challenge mode */

  function mountAdaptive(root) {
    var state = Lab.load();
    var session = { asked: 0, graded: 0, correct: 0, answered: {}, current: null, focus: null };

    var questionEl = $("[data-adaptive-question]", root);
    var figureEl = $("[data-adaptive-figure]", root);
    var inputEl = $("[data-adaptive-input]", root);
    var unitEl = $("[data-adaptive-unit]", root);
    var metaEl = $("[data-adaptive-meta]", root);
    var feedbackEl = $("[data-adaptive-feedback]", root);
    var liveEl = $("#ev-adaptive-live", root);
    var submitEl = $("[data-adaptive-submit]", root);
    var nextEl = $("[data-adaptive-next]", root);
    var summaryEl = $("[data-adaptive-summary]", root);
    var startPanel = $("[data-adaptive-start-panel]", root);
    var panel = $("[data-adaptive-panel]", root);
    var retryEl = $("[data-adaptive-retry]", root);

    // The progress panel and the reset button live in the page sidebar, outside
    // this root, so they are looked up in the document.
    var counters = $$("[data-progress-count]");
    var accuracyEl = $("[data-progress-accuracy]");
    var weakestEl = $("[data-progress-weakest]");
    var recommendEl = $("[data-adaptive-recommend]");
    var storageNotes = $$("[data-adaptive-storage]");

    storageNotes.forEach(function (note) {
      text(note, Lab.storageAvailable
        ? "Progress is saved on this device only. Clearing your browser data removes it."
        : "This browser is blocking storage, so progress will not be kept for this session.");
      note.classList.toggle("is-warn", !Lab.storageAvailable);
    });

    function paintProgress() {
      var accuracy = Lab.accuracy(state);
      counters.forEach(function (el) {
        text(el, el.dataset.progressCount === "correct" ? String(state.correct) : String(state.attempts));
      });
      text(accuracyEl, accuracy === null ? "\u2014" : accuracy + "%");
      var recommendation = Lab.recommend(state.tags);
      text(weakestEl, recommendation ? recommendation.label : "None yet");
      if (!recommendEl) return;
      if (recommendation) {
        hidden(recommendEl, false);
        text(recommendEl, "What to learn next: " + recommendation.message);
      } else if (state.attempts > 0) {
        hidden(recommendEl, false);
        text(recommendEl, "No repeated mistakes yet. Correct answers move you up to medium and hard questions automatically.");
      } else {
        hidden(recommendEl, true);
      }
    }

    function drawCircuit(question) {
      var total = Lab.totalOhms(question);
      var circuit = Lab.solve(question.volts, total);
      var values, arrangement;
      if (question.ohms2) {
        values = [question.ohms, question.ohms2];
        arrangement = question.tag === "parallel" ? "parallel" : "series";
      } else {
        values = [question.ohms];
        arrangement = "single";
      }
      // Cover the quantity being asked for: the learner sees the same diagram
      // the simulator draws, minus the answer.
      if (question.ask === "current") circuit.iText = "?";
      if (question.ask === "voltage") circuit.v = "?";
      if (question.ask === "power") circuit.pText = "?";
      var labels = values.slice();
      if (question.ask === "resistance") {
        labels = values.map(function () { return "?"; });
        circuit.r = "?";
      }
      return Lab.circuitSVG(circuit, {
        resistors: labels, arrangement: arrangement, showPower: question.ask === "power",
      });
    }

    function ask(question) {
      session.current = question;
      session.asked += 1;
      text(questionEl, question.prompt);
      text(unitEl, { current: "A or mA", voltage: "V", resistance: "\u03a9", power: "W or mW" }[question.ask] || "");
      text(metaEl, question.difficulty + " \u00b7 " + (Lab.TAG_LABEL[question.tag] || question.tag) +
        " \u00b7 question " + session.asked);
      figureEl.innerHTML = drawCircuit(question);
      if (inputEl) {
        inputEl.value = ""; inputEl.readOnly = false; inputEl.disabled = false;
        inputEl.setAttribute("aria-invalid", "false");
      }
      if (submitEl) submitEl.disabled = false;
      hidden(nextEl, true);
      hidden(retryEl, true);
      hidden(summaryEl, true);
      feedbackEl.innerHTML = "";
      if (inputEl) inputEl.focus();
    }

    function grade() {
      var question = session.current;
      if (!question) return;
      var answer = parseNumber(inputEl && inputEl.value);
      if (!isFinite(answer)) {
        inputEl.setAttribute("aria-invalid", "true");
        inputEl.focus();
        if (liveEl) liveEl.textContent = "Enter a number before checking your answer.";
        return;
      }
      inputEl.setAttribute("aria-invalid", "false");
      var result = Lab.diagnose({
        ask: question.ask, volts: question.volts,
        ohms: Lab.totalOhms(question), amps: question.amps, answer: answer,
      });

      // Record the attempt. This is what drives the next question, the weakest
      // concept and the recommendation, so it is written before anything else.
      var tag = state.tags[question.tag] || { seen: 0, wrong: 0 };
      tag.seen += 1;
      if (!result.correct) tag.wrong += 1;
      state.tags[question.tag] = tag;
      state.attempts += 1;
      session.graded += 1;
      if (result.correct) state.correct += 1;
      session.answered[question.id] = { correct: result.correct, kind: result.kind };
      if (result.correct) session.correct += 1;

      // Adaptive step: up on a correct answer; down a level AND onto the same
      // tag on a wrong one, so the next question is easier *and* about the
      // thing that was just missed.
      state.level = Lab.stepLevel(state.level, result.correct ? 1 : -1);
      session.focus = result.correct ? null : question.tag;

      var accuracy = Lab.accuracy(state) || 0;
      if (accuracy > state.best) state.best = accuracy;
      Lab.save(state);

      inputEl.readOnly = true;
      inputEl.disabled = true;
      submitEl.disabled = true;

      feedbackEl.innerHTML = "";
      var heading = document.createElement("p");
      heading.className = "ev-verdict " + (result.correct ? "is-right" : "is-wrong");
      heading.textContent = result.correct ? "Correct" : "Not quite";
      feedbackEl.appendChild(heading);

      var body = document.createElement("p");
      body.className = "ev-feedback-line";
      body.textContent = result.correct ? result.message : result.message + " " + question.why;
      feedbackEl.appendChild(body);

      var working = document.createElement("p");
      working.className = "ev-feedback-working";
      working.textContent = "Your answer: " + Lab.round(answer, 4) + " \u00b7 Actual: " + result.truthText;
      feedbackEl.appendChild(working);

      var nextLine = document.createElement("p");
      nextLine.className = "ev-feedback-next";
      nextLine.textContent = result.correct
        ? "Next: a harder question."
        : "Next: an easier " + (Lab.TAG_LABEL[question.tag] || question.tag).toLowerCase() +
          " question, to rebuild the step you missed.";
      feedbackEl.appendChild(nextLine);

      if (liveEl) liveEl.textContent = (result.correct ? "Correct. " : "Not quite. ") + result.message;
      paintProgress();
      hidden(nextEl, false);
      nextEl.focus();
    }

    function next() {
      var pick = Lab.pickNext({ level: state.level, focus: session.focus, answered: session.answered });
      if (!pick) { finish(); return; }
      ask(pick);
    }

    function finish() {
      if (!session.graded) {
        if (liveEl) liveEl.textContent = "No questions answered yet in this session.";
        return;
      }
      // The score is over questions actually answered. Counting the one on
      // screen would report 1 of 2 for a single answered question.
      var total = session.graded;
      var score = Math.round((session.correct / total) * 100);
      state.sessions.push({ at: Date.now(), score: score, total: total, correct: session.correct });
      state.sessions = state.sessions.slice(-10);
      Lab.save(state);

      var missed = Object.keys(session.answered)
        .filter(function (id) { return !session.answered[id].correct; })
        .map(function (id) { var q = Lab.byId(id); return q ? (Lab.TAG_LABEL[q.tag] || q.tag) : id; });
      var recommendation = Lab.recommend(state.tags);

      summaryEl.innerHTML = "";
      var title = document.createElement("p");
      title.className = "ev-summary-score";
      title.textContent = "Session: " + session.correct + " of " + total + " correct (" + score + "%)";
      summaryEl.appendChild(title);

      var detail = document.createElement("p");
      detail.className = "ev-feedback-line";
      detail.textContent = (missed.length ? "Missed: " + missed.join(", ") + ". " : "No mistakes this session. ") +
        "On this device overall: " + state.correct + " of " + state.attempts + " attempts correct.";
      summaryEl.appendChild(detail);

      if (recommendation) {
        var advice = document.createElement("p");
        advice.className = "ev-feedback-next";
        advice.textContent = "What to learn next: " + recommendation.message;
        summaryEl.appendChild(advice);
      }
      hidden(summaryEl, false);
      hidden(nextEl, true);
      hidden(retryEl, false);
      if (liveEl) liveEl.textContent = "Session finished. " + title.textContent;
      paintProgress();
      retryEl.focus();
    }

    function restart() {
      session.asked = 0; session.graded = 0; session.correct = 0; session.answered = {}; session.focus = null;
      next();
    }

    on(submitEl, "click", grade);
    on(nextEl, "click", next);
    on($("[data-adaptive-start]", root), "click", function () {
      hidden(startPanel, true);
      hidden(panel, false);
      restart();
    });
    on($("[data-adaptive-finish]", root), "click", finish);
    on(retryEl, "click", restart);
    on($("[data-adaptive-reset]"), "click", function () {
      state = Lab.load();
      state.tags = {};
      state.attempts = 0; state.correct = 0; state.best = 0; state.level = "easy";
      state.sessions = [];
      session = { asked: 0, graded: 0, correct: 0, answered: {}, current: null, focus: null };
      Lab.save(state);
      paintProgress();
      if (liveEl) liveEl.textContent = "Saved progress cleared on this device.";
    });
    if (inputEl) {
      on(inputEl, "keydown", function (event) {
        if (event.key !== "Enter") return;
        event.preventDefault();
        if (nextEl && !nextEl.hidden) next(); else grade();
      });
    }
    paintProgress();
  }

  /* ------------------------------------------------------------- boot */

  function boot() {
    $$("[data-ev-lab='mini']").forEach(function (root) { Lab.mountMini(root); });
    var predict = $("#ev-predict");
    if (predict) mountPredict(predict);
    var adaptive = $("#ev-adaptive");
    if (adaptive) mountAdaptive(adaptive);
    var progress = $("#ev-lab-progress");
    if (progress && !adaptive) {
      // Progress panel on its own (e.g. linked from the dashboard).
      var state = Lab.load();
      var accuracy = Lab.accuracy(state);
      $$("[data-progress-count]", progress).forEach(function (el) {
        text(el, el.dataset.progressCount === "correct" ? String(state.correct) : String(state.attempts));
      });
      var accuracyEl = $("[data-progress-accuracy]", progress);
      text(accuracyEl, accuracy === null ? "\u2014" : accuracy + "%");
      var recommendation = Lab.recommend(state.tags);
      text($("[data-progress-weakest]", progress), recommendation ? recommendation.label : "None yet");
      var note = $("[data-adaptive-storage]", progress);
      if (note) {
        text(note, Lab.storageAvailable
          ? "Progress is saved on this device only."
          : "This browser is blocking storage, so there is nothing to show.");
      }
    }
  }

  Lab.boot = boot;
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
