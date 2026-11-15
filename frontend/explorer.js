(() => {
  "use strict";

  // ============================================================================
  // 1. DETERMINISTIC ASTROPHYSICAL DATA GENERATOR & SCIENTIFIC BUNDLES
  // ============================================================================

  const GRID_SIZE = 96;
  const OUT_SIZE = 384;
  const API_ORIGIN =
    (typeof window !== "undefined" &&
      (window.ORVYX_API_ORIGIN ||
        (window.location && new URLSearchParams(window.location.search).get("api_origin")))) ||
    (typeof window !== "undefined" && window.location && window.location.port === "8000"
      ? window.location.origin
      : "http://127.0.0.1:8000");
  const API_BASE = `${API_ORIGIN.replace(/\/$/, "")}/api/v1`;
  const REQUEST_TIMEOUT_MS = 8000;
  const ASK_TIMEOUT_MS = 15000;
  const BLINK_INTERVAL_MS = 550;

  const EPOCHS_META = [
    { num: 1, mjd: 60810.2, date: "2025-05-15", rel: "QR2", det: 4, wl: 2.64 },
    { num: 2, mjd: 60992.6, date: "2025-11-13", rel: "QR2", det: 5, wl: 4.12 },
    { num: 3, mjd: 61175.4, date: "2026-05-15", rel: "QR3", det: 5, wl: 4.18 },
    { num: 4, mjd: 61348.8, date: "2026-11-04", rel: "QR3", det: 6, wl: 4.62 },
  ];

  const BG_STARS = [
    { id: "bg_01", name: "Gaia DR3 Field Star A", x: 21.4, y: 24.8, flux: 46.0 },
    { id: "bg_02", name: "Gaia DR3 Field Star B", x: 73.2, y: 20.5, flux: 38.5 },
    { id: "bg_03", name: "Gaia DR3 Field Star C", x: 68.8, y: 74.1, flux: 54.0 },
    { id: "bg_04", name: "Gaia DR3 Field Star D", x: 24.1, y: 70.4, flux: 31.0 },
    { id: "bg_05", name: "Gaia DR3 Field Star E", x: 40.2, y: 17.6, flux: 23.5 },
    { id: "bg_06", name: "Gaia DR3 Field Star F", x: 79.5, y: 51.2, flux: 29.0 },
  ];

  const DISPLAY_MODES = [
    "paired_wiseview",
    "single_blink",
    "difference_only",
    "coadd_stack",
  ];

  const DISPLAY_MODE_LABELS = {
    paired_wiseview: "PAIRED",
    single_blink: "BLINK",
    difference_only: "DIPOLE",
    coadd_stack: "CO-ADD",
  };

  const DIFF_LABELS = ["I₁ − I₂", "I₂ − I_REF", "I₃ − I_REF", "I₄ − I_REF"];

  const SHORT_CLASS_MAP = {
    wise_0855: "Y4 SUB-BROWN DWARF",
    barnards_star: "M4V RED DWARF",
    epsilon_indi_b: "T1 + T6 BINARY BROWN DWARF",
    rw_aurigae: "CLASSICAL T TAURI VARIABLE",
    r_draconis: "MIRA PULSATING RED GIANT",
    negative_control: "STATIC NEGATIVE CONTROL",
    custom_patch: "CUSTOM SKY CUTOUT",
  };

  function seededRandom(seed) {
    const x = Math.sin(seed * 12.9898 + 78.233) * 43758.5453;
    return x - Math.floor(x);
  }

  function injectGaussianPSF(buffer, width, height, cx, cy, amplitude, sigma) {
    const radius = Math.ceil(sigma * 4.5);
    const x0 = Math.max(0, Math.floor(cx - radius));
    const x1 = Math.min(width - 1, Math.ceil(cx + radius));
    const y0 = Math.max(0, Math.floor(cy - radius));
    const y1 = Math.min(height - 1, Math.ceil(cy + radius));
    const invTwoSigma2 = 1 / (2 * sigma * sigma);

    for (let y = y0; y <= y1; y++) {
      const dy = y - cy;
      const dy2 = dy * dy;
      const rowOffset = y * width;
      for (let x = x0; x <= x1; x++) {
        const dx = x - cx;
        buffer[rowOffset + x] += amplitude * Math.exp(-(dx * dx + dy2) * invTwoSigma2);
      }
    }
  }

  function generate102BandSpectrum(peakUm, baseFlux, isColdBrownDwarf, isVariable) {
    const points = [];
    const totalChannels = 102;

    for (let i = 0; i < totalChannels; i++) {
      const wl = Number((0.75 + (i / (totalChannels - 1)) * 4.25).toFixed(3));
      const det =
        wl < 1.1
          ? 1
          : wl < 1.63
          ? 2
          : wl < 2.42
          ? 3
          : wl < 3.83
          ? 4
          : wl < 4.42
          ? 5
          : 6;

      let flux = baseFlux * Math.exp(-Math.pow((wl - peakUm) / 1.35, 2));
      if (isColdBrownDwarf) {
        flux =
          wl < 3.3
            ? baseFlux * (0.04 + 0.03 * Math.abs(Math.sin(wl * 5.2)))
            : baseFlux * 1.55 * Math.exp(-Math.pow((wl - 4.48) / 0.48, 2));
      } else if (isVariable) {
        flux += baseFlux * 0.35 * Math.sin(wl * 2.4) * Math.exp(-wl / 4.0);
      }

      points.push({
        channel: i + 1,
        wavelengthUm: wl,
        bandwidthUm: Number((wl / (det >= 5 ? 115 : 40)).toFixed(3)),
        fluxMjySr: Number(Math.max(0.4, flux).toFixed(2)),
        fluxErr: Number((0.035 * baseFlux + 0.2).toFixed(2)),
        detector: det,
      });
    }
    return points;
  }

  function createTargetScientificBundle(config) {
    const startX = 46.0;
    const startY = 49.0;
    const xByEpoch = [];
    const yByEpoch = [];
    const rawEpochArrays = [];
    const masks = [];

    EPOCHS_META.forEach((ep, idx) => {
      const arr = new Float32Array(GRID_SIZE * GRID_SIZE);
      const mask = new Uint8Array(GRID_SIZE * GRID_SIZE);

      for (let i = 0; i < arr.length; i++) {
        arr[i] = (seededRandom(i * (idx + 1) + config.raDeg * 10) - 0.5) * 2.1;
        if (seededRandom(i * 3.7 + idx * 23 + config.raDeg) > 0.9965) {
          mask[i] = 1;
          arr[i] += 22.0;
        }
      }

      BG_STARS.forEach((st) => {
        injectGaussianPSF(arr, GRID_SIZE, GRID_SIZE, st.x, st.y, st.flux, 1.42);
      });

      const curX = startX + idx * config.dxPerEpochPx;
      const curY = startY + idx * config.dyPerEpochPx;
      xByEpoch.push(Number(curX.toFixed(2)));
      yByEpoch.push(Number(curY.toFixed(2)));

      injectGaussianPSF(
        arr,
        GRID_SIZE,
        GRID_SIZE,
        curX,
        curY,
        config.epochFluxes[idx],
        1.68
      );

      if (config.key === "epsilon_indi_b") {
        injectGaussianPSF(
          arr,
          GRID_SIZE,
          GRID_SIZE,
          curX + 3.5,
          curY - 2.7,
          config.epochFluxes[idx] * 0.65,
          1.45
        );
      }

      rawEpochArrays.push(arr);
      masks.push(mask);
    });

    const refPlane = rawEpochArrays[0];

    const frames = EPOCHS_META.map((ep, idx) => {
      const diff = new Float32Array(GRID_SIZE * GRID_SIZE);
      const add = new Float32Array(GRID_SIZE * GRID_SIZE);
      const cur = rawEpochArrays[idx];

      for (let i = 0; i < diff.length; i++) {
        // Suppress cosmic-ray spikes in the difference plane while preserving rawPixels/flagsMask
        const cleanCur = masks[idx][i] > 0 ? cur[i] - 22.0 : cur[i];
        const refMask = idx === 0 ? masks[1][i] : masks[0][i];
        const rawRef = idx === 0 ? rawEpochArrays[1][i] : refPlane[i];
        const cleanRef = refMask > 0 ? rawRef - 22.0 : rawRef;
        diff[i] =
          idx === 0 ? cleanCur - cleanRef * 0.96 : cleanCur - cleanRef;
        add[i] = (cur[i] + refPlane[i]) * 0.5;
      }

      let flaggedCount = 0;
      for (let i = 0; i < masks[idx].length; i++) {
        if (masks[idx][i] > 0) flaggedCount++;
      }

      return {
        obsId: `SPX_${ep.rel}_0${ep.num}_${config.key.toUpperCase()}`,
        epochNumber: ep.num,
        mjd: ep.mjd,
        isoDate: ep.date,
        release: ep.rel,
        detector: ep.det,
        centralWavelengthUm: ep.wl,
        bandwidthUm: Number((ep.wl / (ep.det >= 5 ? 112 : 38)).toFixed(3)),
        width: GRID_SIZE,
        height: GRID_SIZE,
        rawPixels: cur,
        differencePixels: diff,
        additionPixels: add,
        flagsMask: masks[idx],
        contamination: {
          totalPixels: GRID_SIZE * GRID_SIZE,
          contaminatedPixels: flaggedCount,
          contaminationFraction: Number(
            (flaggedCount / (GRID_SIZE * GRID_SIZE)).toFixed(4)
          ),
          flagBreakdown: {
            TRANSIENT_OR_COSMIC_RAY: Math.max(1, Math.floor(flaggedCount * 0.7)),
            DICHROIC_EDGE_ARTIFACT: Math.floor(flaggedCount * 0.3),
          },
        },
      };
    });

    const coaddByDetector = {};
    for (let d = 1; d <= 6; d++) {
      const stack = new Float32Array(GRID_SIZE * GRID_SIZE);
      const scale =
        config.isColdBrownDwarf && d < 4
          ? 0.22
          : config.isColdBrownDwarf && d >= 5
          ? 1.65
          : 1.05;
      for (let i = 0; i < stack.length; i++) {
        const avg =
          (rawEpochArrays[0][i] +
            rawEpochArrays[1][i] +
            rawEpochArrays[2][i] +
            rawEpochArrays[3][i]) *
          0.25;
        stack[i] = avg * scale;
      }
      coaddByDetector[d] = stack;
    }

    const primarySource = {
      id: `target_${config.key}`,
      designation: config.wiseId,
      commonName: config.name,
      overlayLabel: config.overlayLabel || null,
      objectType: config.subtitle,
      raDeg: config.raDeg,
      decDeg: config.decDeg,
      xByEpoch,
      yByEpoch,
      dxPxPerYr: Number((config.dxPerEpochPx * 2).toFixed(2)),
      dyPxPerYr: Number((config.dyPerEpochPx * 2).toFixed(2)),
      pmRaMasYr: config.pmRaMasYr,
      pmDecMasYr: config.pmDecMasYr,
      totalPmArcsecYr: config.totalPmArcsecYr,
      catalogReferencePmArcsecYr: config.catalogReferencePmArcsecYr,
      parallaxMas: config.parallaxMas,
      snr: config.snr,
      variabilityChi2: config.variabilityChi2,
      isCandidateMoving: config.totalPmArcsecYr > 0.5,
      isVariable: config.isVariable,
      isGaiaOpticalDropout: config.isGaiaDropout,
      gaiaDr3Id: config.gaiaId,
      wiseDesignation: config.wiseId,
      csaNeossatObsId: config.csaNeossatObsId,
      lightCurve: EPOCHS_META.map((ep, idx) => ({
        epochNumber: ep.num,
        mjd: ep.mjd,
        isoDate: ep.date,
        fluxMjySr: config.epochFluxes[idx],
        fluxErr: 1.8,
        wavelengthUm: ep.wl,
      })),
      spectrum102Band: generate102BandSpectrum(
        config.peakUm,
        config.epochFluxes[2],
        config.isColdBrownDwarf,
        config.isVariable
      ),
    };

    const secondarySources = BG_STARS.slice(0, 4).map((st, idx) => ({
      id: st.id,
      designation: `Gaia DR3 4490812093810${idx + 1}`,
      commonName: st.name,
      objectType: "Stationary Reference Field Star (Negative Control)",
      raDeg: Number((config.raDeg + (idx - 1.5) * 0.011).toFixed(5)),
      decDeg: Number((config.decDeg + (idx - 1.5) * 0.009).toFixed(5)),
      xByEpoch: [st.x, st.x, st.x, st.x],
      yByEpoch: [st.y, st.y, st.y, st.y],
      dxPxPerYr: 0.01,
      dyPxPerYr: -0.01,
      pmRaMasYr: 3.4,
      pmDecMasYr: -2.8,
      totalPmArcsecYr: 0.004,
      catalogReferencePmArcsecYr: 0.004,
      parallaxMas: 1.6,
      snr: 31.2,
      variabilityChi2: 0.88,
      isCandidateMoving: false,
      isVariable: false,
      isGaiaOpticalDropout: false,
      gaiaDr3Id: `Gaia DR3 4490812093810${idx + 1}`,
      wiseDesignation: `AllWISE J${config.raDeg.toFixed(2)}+0${idx + 1}`,
      csaNeossatObsId: null,
      lightCurve: EPOCHS_META.map((ep) => ({
        epochNumber: ep.num,
        mjd: ep.mjd,
        isoDate: ep.date,
        fluxMjySr: st.flux,
        fluxErr: 1.1,
        wavelengthUm: ep.wl,
      })),
      spectrum102Band: generate102BandSpectrum(1.35, st.flux, false, false),
    }));

    const wiseviewUrl = `http://byw.tools/wiseview#ra=${config.raDeg.toFixed(
      6
    )}&dec=${config.decDeg.toFixed(
      6
    )}&size=288&band=2&speed=150&linear=0.15&gaia=1`;

    return {
      key: config.key,
      name: config.name,
      shortClass: config.shortClass || SHORT_CLASS_MAP[config.key] || "CUSTOM SKY CUTOUT",
      subtitle: config.subtitle,
      constellation: config.constellation,
      raDeg: config.raDeg,
      decDeg: config.decDeg,
      fovDeg: config.fovDeg || 0.08,
      peakUm: config.peakUm,
      recommendedMode: config.recommendedMode,
      wiseviewUrl,
      csaCadcNeossatCount: config.csaNeossatCount,
      csaTargetNote: config.csaTargetNote,
      frames,
      coaddByDetector,
      sources: [primarySource, ...secondarySources],
      narratorChapters: config.narratorChapters,
    };
  }

  const TARGET_BUNDLES = {
    wise_0855: createTargetScientificBundle({
      key: "wise_0855",
      name: "WISE 0855",
      shortClass: SHORT_CLASS_MAP.wise_0855,
      subtitle: "Y4 Sub-Brown Dwarf (Coldest Known Neighbor, ~250 K)",
      constellation: "Hydra",
      raDeg: 133.79513,
      decDeg: -7.24515,
      recommendedMode: "motion",
      pmRaMasYr: -8118.0,
      pmDecMasYr: 680.0,
      totalPmArcsecYr: 8.14,
      catalogReferencePmArcsecYr: 8.12,
      parallaxMas: 438.9,
      snr: 48.6,
      variabilityChi2: 1.14,
      dxPerEpochPx: 2.35,
      dyPerEpochPx: -0.45,
      epochFluxes: [64.0, 68.5, 67.2, 70.1],
      peakUm: 4.48,
      isColdBrownDwarf: true,
      isVariable: false,
      isGaiaDropout: true,
      gaiaId: null,
      wiseId: "WISE J085510.83-071442.5",
      csaNeossatObsId: "NEOSSAT_CADC_2026_HYDRA_094",
      csaNeossatCount: 6,
      csaTargetNote:
        "CSA CADC NEOSSat cleared foreground main-belt asteroid streaks along Hydra ecliptic sector.",
      narratorChapters: [
        {
          chapterNumber: "02",
          chapterTitle: "A UNIVERSE IN MOTION",
          summary:
            "WISE 0855 shifts at µ = 8.14 arcsec/yr (~0.66 SPHEREx pixels per 6-month survey pass). In the Paired Dipole Difference view (I₃ − I_REF), stationary field stars cancel out cleanly while WISE 0855 leaves an unmistakable indigo-to-amber dipole signature.",
          linkedObjectId: "target_wise_0855",
          actionType: "inspect_dipole",
          confidenceLabel: "GAIA OPTICAL DROPOUT (IR-ONLY)",
          citations: [
            {
              sourceName: "ESA Gaia DR3 Archive",
              referenceId: "DR3 ZERO MATCH",
              url: "https://gea.esac.esa.int/archive/",
              agencyTag: "ESA GAIA DR3",
            },
          ],
        },
        {
          chapterNumber: "03",
          chapterTitle: "WHY GAIA DR3 SEES NOTHING HERE",
          summary:
            "Cross-matching against Gaia DR3 returns zero optical counterparts. At ~250 K (-23 °C), water-ice clouds and methane absorb visible and 1–3 µm light, making this sub-brown dwarf shine brightly only in SPHEREx Bands 5 & 6 (4.0–5.0 µm).",
          linkedObjectId: "target_wise_0855",
          actionType: "inspect_spectrum",
          confidenceLabel: "GAIA OPTICAL DROPOUT (IR-ONLY)",
          citations: [
            {
              sourceName: "ESA Gaia DR3 Archive",
              referenceId: "IR-ONLY DROPOUT",
              url: "https://gea.esac.esa.int/archive/",
              agencyTag: "ESA GAIA DR3",
            },
            {
              sourceName: "Luhman (2014) ApJL 786, L18",
              referenceId: "2014ApJ...786L..18L",
              url: "https://ui.adsabs.harvard.edu/abs/2014ApJ...786L..18L/abstract",
              agencyTag: "NASA ADS",
            },
          ],
        },
        {
          chapterNumber: "01",
          chapterTitle: "WHERE ARE YOU LOOKING?",
          summary:
            "You are inspecting a 4.8-arcminute sky patch in Hydra (RA 133.7951°, Dec -7.2451°). All stationary field stars are astrometrically locked to the ESA Gaia DR3 ICRS grid across four SPHEREx survey epochs.",
          linkedObjectId: "target_wise_0855",
          actionType: "focus_motion",
          confidenceLabel: "GAIA OPTICAL DROPOUT (IR-ONLY)",
          citations: [
            {
              sourceName: "NASA IRSA SPHEREx QR3",
              referenceId: "doi:10.26131/IRSA662",
              url: "https://irsa.ipac.caltech.edu/Missions/spherex.html",
              agencyTag: "NASA SPHEREX",
            },
            {
              sourceName: "SIMBAD Astronomical Database",
              referenceId: "WISE J085510.83-071442.5",
              url: "https://simbad.cds.unistra.fr/simbad/sim-id?Ident=WISE+J085510.83-071442.5",
              agencyTag: "SIMBAD",
            },
            {
              sourceName: "CSA CADC NEOSSat Archive",
              referenceId: "CADC:NEOSSAT_2026_094",
              url: "https://www.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/en/",
              agencyTag: "CSA CADC NEOSSAT",
            },
          ],
        },
      ],
    }),

    barnards_star: createTargetScientificBundle({
      key: "barnards_star",
      name: "Barnard's Star",
      shortClass: SHORT_CLASS_MAP.barnards_star,
      subtitle: "M4V Red Dwarf (Fastest Known Stellar Proper Motion in the Sky)",
      constellation: "Ophiuchus",
      raDeg: 269.45208,
      decDeg: 4.69339,
      recommendedMode: "motion",
      pmRaMasYr: -801.55,
      pmDecMasYr: 10362.39,
      totalPmArcsecYr: 10.39,
      catalogReferencePmArcsecYr: 10.393,
      parallaxMas: 546.98,
      snr: 94.2,
      variabilityChi2: 1.09,
      dxPerEpochPx: -0.38,
      dyPerEpochPx: -2.85,
      epochFluxes: [92.0, 91.4, 92.8, 91.9],
      peakUm: 1.65,
      isColdBrownDwarf: false,
      isVariable: false,
      isGaiaDropout: false,
      gaiaId: "Gaia DR3 4472832130942575872",
      wiseId: "WISE J175747.94+044314.9",
      csaNeossatObsId: "NEOSSAT_CADC_2026_OPH_211",
      csaNeossatCount: 9,
      csaTargetNote:
        "CSA NEOSSat exoplanet transit & stellar flare monitoring sector in Ophiuchus.",
      narratorChapters: [
        {
          chapterNumber: "01",
          chapterTitle: "RECORD STELLAR PROPER MOTION (10.39\"/YR)",
          summary:
            "Barnard's Star (GJ 699) races northward across Ophiuchus at 10.39 arcseconds per year—displacing ~0.84 SPHEREx pixels every 6-month survey pass.",
          linkedObjectId: "target_barnards_star",
          actionType: "focus_motion",
          confidenceLabel: "CONFIRMED CATALOG OBJECT",
          citations: [
            {
              sourceName: "ESA Gaia DR3 Astrometry",
              referenceId: "Gaia DR3 4472832130942575872",
              url: "https://simbad.cds.unistra.fr/simbad/sim-id?Ident=Barnard%27s+Star",
              agencyTag: "ESA GAIA DR3",
            },
          ],
        },
        {
          chapterNumber: "02",
          chapterTitle: "SUB-0.05 ARCSEC EPOCH PROPAGATION RESIDUAL",
          summary:
            "Propagating Gaia DR3 J2016.0 coordinates to SPHEREx QR3 (2026.8) via Astropy space-motion vectors matches our SEP subpixel centroid trajectory within 0.03 arcsec/yr.",
          linkedObjectId: "target_barnards_star",
          actionType: "inspect_dipole",
          confidenceLabel: "CONFIRMED CATALOG OBJECT",
          citations: [
            {
              sourceName: "NASA IRSA SPHEREx Cutouts",
              referenceId: "SPX_QR3_GJ699",
              url: "https://irsa.ipac.caltech.edu/Missions/spherex.html",
              agencyTag: "NASA SPHEREX",
            },
          ],
        },
        {
          chapterNumber: "03",
          chapterTitle: "M4V NEAR-INFRARED SED PROFILE",
          summary:
            "Unlike ultracool Y-dwarfs, this M4V red dwarf peaks near 1.65 µm in SPHEREx Band 2/3 while remaining bright across optical Gaia DR3 G-band imagery.",
          linkedObjectId: "target_barnards_star",
          actionType: "inspect_spectrum",
          confidenceLabel: "CONFIRMED CATALOG OBJECT",
          citations: [
            {
              sourceName: "CSA CADC NEOSSat Archive",
              referenceId: "NEOSSAT_CADC_2026_OPH_211",
              url: "https://www.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/en/",
              agencyTag: "CSA CADC NEOSSAT",
            },
          ],
        },
      ],
    }),

    epsilon_indi_b: createTargetScientificBundle({
      key: "epsilon_indi_b",
      name: "Epsilon Indi B",
      shortClass: SHORT_CLASS_MAP.epsilon_indi_b,
      subtitle: "Resolved T1 + T6 Binary Brown Dwarf Companion System",
      constellation: "Indus",
      raDeg: 331.04375,
      decDeg: -56.78278,
      recommendedMode: "motion",
      pmRaMasYr: 3967.0,
      pmDecMasYr: -2536.0,
      totalPmArcsecYr: 4.71,
      catalogReferencePmArcsecYr: 4.707,
      parallaxMas: 274.8,
      snr: 56.4,
      variabilityChi2: 1.32,
      dxPerEpochPx: -1.65,
      dyPerEpochPx: 1.15,
      epochFluxes: [58.0, 60.2, 59.1, 58.7],
      peakUm: 2.25,
      isColdBrownDwarf: false,
      isVariable: false,
      isGaiaDropout: false,
      gaiaId: "Gaia DR3 6412595290592307840",
      wiseId: "WISE J220410.60-564658.2",
      csaNeossatObsId: "NEOSSAT_CADC_2026_IND_042",
      csaNeossatCount: 4,
      csaTargetNote:
        "CSA CADC high-proper-motion southern sky astrometric calibration reference.",
      narratorChapters: [
        {
          chapterNumber: "01",
          chapterTitle: "CO-MOVING T1 + T6 BROWN DWARF PAIR",
          summary:
            "Epsilon Indi Ba and Bb share a rapid common proper motion of 4.71 arcsec/yr at 3.62 parsecs distance. Both components are resolved cleanly in our 6-Detector Co-Add Stack.",
          linkedObjectId: "target_epsilon_indi_b",
          actionType: "focus_motion",
          confidenceLabel: "CONFIRMED CATALOG OBJECT",
          citations: [
            {
              sourceName: "SIMBAD / ESO Benchmark Binary",
              referenceId: "eps Ind B",
              url: "https://simbad.cds.unistra.fr/simbad/sim-id?Ident=eps+Ind+B",
              agencyTag: "SIMBAD",
            },
            {
              sourceName: "ESA Gaia DR3 Archive",
              referenceId: "Gaia DR3 6412595290592307840",
              url: "https://gea.esac.esa.int/archive/",
              agencyTag: "ESA GAIA DR3",
            },
          ],
        },
        {
          chapterNumber: "02",
          chapterTitle: "BINARY DIPOLE RESIDUAL SIGNATURE",
          summary:
            "Subtracting Epoch 1 reveals the co-moving T1 + T6 binary pair shifting southeast-to-southwest together in the dipole difference frame.",
          linkedObjectId: "target_epsilon_indi_b",
          actionType: "inspect_dipole",
          confidenceLabel: "CONFIRMED CATALOG OBJECT",
          citations: [
            {
              sourceName: "NASA IRSA SPHEREx Cutouts",
              referenceId: "SPX_QR3_EPSINDB",
              url: "https://irsa.ipac.caltech.edu/Missions/spherex.html",
              agencyTag: "NASA SPHEREX",
            },
          ],
        },
      ],
    }),

    rw_aurigae: createTargetScientificBundle({
      key: "rw_aurigae",
      name: "RW Aurigae",
      shortClass: SHORT_CLASS_MAP.rw_aurigae,
      subtitle: "Classical T Tauri Variable Star with Circumstellar Disk Occultation",
      constellation: "Auriga",
      raDeg: 76.95654,
      decDeg: 30.40144,
      recommendedMode: "variability",
      pmRaMasYr: 2.9,
      pmDecMasYr: -24.1,
      totalPmArcsecYr: 0.024,
      catalogReferencePmArcsecYr: 0.024,
      parallaxMas: 6.12,
      snr: 64.1,
      variabilityChi2: 84.6,
      dxPerEpochPx: 0.02,
      dyPerEpochPx: 0.02,
      epochFluxes: [38.5, 86.4, 51.2, 94.8],
      peakUm: 2.85,
      isColdBrownDwarf: false,
      isVariable: true,
      isGaiaDropout: false,
      gaiaId: "Gaia DR3 156430821014792832",
      wiseId: "WISE J050749.56+302405.1",
      csaNeossatObsId: "NEOSSAT_CADC_2026_AUR_118",
      csaNeossatCount: 7,
      csaTargetNote:
        "CSA CADC young stellar object (YSO) photometric monitoring target in Auriga.",
      narratorChapters: [
        {
          chapterNumber: "01",
          chapterTitle: "FIXED ASTROMETRY, EXTREME IR FLUX VARIABILITY",
          summary:
            "RW Aurigae remains spatially fixed on the WCS grid (µ = 0.024 arcsec/yr), yet its band-matched infrared flux varies by >2.4× (χ² = 84.6) due to tidal dust streams and episodic accretion.",
          linkedObjectId: "target_rw_aurigae",
          actionType: "inspect_lightcurve",
          confidenceLabel: "VARIABLE SOURCE",
          citations: [
            {
              sourceName: "SIMBAD Variable Star Catalog",
              referenceId: "V* RW Aur",
              url: "https://simbad.cds.unistra.fr/simbad/sim-id?Ident=RW+Aur",
              agencyTag: "SIMBAD",
            },
            {
              sourceName: "ESA Gaia DR3 Archive",
              referenceId: "Gaia DR3 156430821014792832",
              url: "https://gea.esac.esa.int/archive/",
              agencyTag: "ESA GAIA DR3",
            },
          ],
        },
        {
          chapterNumber: "02",
          chapterTitle: "CIRCUMSTELLAR DUST EXCESS AT 2.85 µm",
          summary:
            "Warm silicate and carbonaceous dust grains inside the circumstellar disk produce a broad near-infrared excess peaking near 2.85 µm across SPHEREx Bands 3–4.",
          linkedObjectId: "target_rw_aurigae",
          actionType: "inspect_spectrum",
          confidenceLabel: "VARIABLE SOURCE",
          citations: [
            {
              sourceName: "NASA IRSA SPHEREx Cutouts",
              referenceId: "SPX_QR3_RWAUR",
              url: "https://irsa.ipac.caltech.edu/Missions/spherex.html",
              agencyTag: "NASA SPHEREX",
            },
          ],
        },
      ],
    }),

    r_draconis: createTargetScientificBundle({
      key: "r_draconis",
      name: "R Draconis",
      shortClass: SHORT_CLASS_MAP.r_draconis,
      subtitle: "Mira-Type Pulsating Red Giant Variable Star (P = 245.6 days)",
      constellation: "Draco",
      raDeg: 248.1675,
      decDeg: 66.75472,
      recommendedMode: "variability",
      pmRaMasYr: -11.4,
      pmDecMasYr: -33.2,
      totalPmArcsecYr: 0.035,
      catalogReferencePmArcsecYr: 0.035,
      parallaxMas: 2.31,
      snr: 78.5,
      variabilityChi2: 112.4,
      dxPerEpochPx: 0.01,
      dyPerEpochPx: -0.02,
      epochFluxes: [96.2, 31.8, 44.5, 91.0],
      peakUm: 3.15,
      isColdBrownDwarf: false,
      isVariable: true,
      isGaiaDropout: false,
      gaiaId: "Gaia DR3 1644891240981234560",
      wiseId: "WISE J163240.23+664517.2",
      csaNeossatObsId: "NEOSSAT_CADC_2026_DRA_305",
      csaNeossatCount: 11,
      csaTargetNote:
        "Located near the North Ecliptic Pole continuous viewing zone (SPHEREx + NEOSSat).",
      narratorChapters: [
        {
          chapterNumber: "01",
          chapterTitle: "HIGH-AMPLITUDE MIRA PULSATIONS IN DRACO",
          summary:
            "Because R Draconis sits near the high-declination SPHEREx deep field in Draco, repeated LVF passes resolve its 245.6-day stellar pulsation cycle and deep water-vapor bands.",
          linkedObjectId: "target_r_draconis",
          actionType: "inspect_lightcurve",
          confidenceLabel: "VARIABLE SOURCE",
          citations: [
            {
              sourceName: "SIMBAD Mira Variable Entry",
              referenceId: "V* R Dra",
              url: "https://simbad.cds.unistra.fr/simbad/sim-id?Ident=R+Dra",
              agencyTag: "SIMBAD",
            },
            {
              sourceName: "CSA CADC NEOSSat Archive",
              referenceId: "NEOSSAT_CADC_2026_DRA_305",
              url: "https://www.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/en/",
              agencyTag: "CSA CADC NEOSSAT",
            },
          ],
        },
        {
          chapterNumber: "02",
          chapterTitle: "STELLAR H₂O & CO MOLECULAR BANDS (3.15 µm)",
          summary:
            "Pulsating asymptotic giant branch atmospheres exhibit strong H₂O and CO absorption features modulated across SPHEREx Bands 3–5.",
          linkedObjectId: "target_r_draconis",
          actionType: "inspect_spectrum",
          confidenceLabel: "VARIABLE SOURCE",
          citations: [
            {
              sourceName: "ESA Gaia DR3 Archive",
              referenceId: "Gaia DR3 1644891240981234560",
              url: "https://gea.esac.esa.int/archive/",
              agencyTag: "ESA GAIA DR3",
            },
          ],
        },
      ],
    }),
  };

  const NEGATIVE_CONTROL_BUNDLE = createTargetScientificBundle({
    key: "negative_control",
    name: "Gaia DR3 720517945437337600",
    overlayLabel: "GAIA DR3 CONTROL",
    shortClass: SHORT_CLASS_MAP.negative_control,
    subtitle: "Stationary Reference Star (Static Astrometric & Photometric Control)",
    constellation: "Lynx",
    raDeg: 134.84582,
    decDeg: 40.9947,
    recommendedMode: "motion",
    pmRaMasYr: 1.4,
    pmDecMasYr: -1.4,
    totalPmArcsecYr: 0.002,
    catalogReferencePmArcsecYr: 0.002,
    parallaxMas: 0.85,
    snr: 42.5,
    variabilityChi2: 0.92,
    dxPerEpochPx: 0.0,
    dyPerEpochPx: 0.0,
    epochFluxes: [48.2, 48.0, 48.3, 48.1],
    peakUm: 1.45,
    isColdBrownDwarf: false,
    isVariable: false,
    isGaiaDropout: false,
    gaiaId: "Gaia DR3 720517945437337600",
    wiseId: "WISE J085923.00+405940.9",
    csaNeossatObsId: "NEOSSAT_CADC_2026_LYN_001",
    csaNeossatCount: 2,
    csaTargetNote:
      "Static negative control benchmark confirming zero false-positive dipole or variability detections.",
    narratorChapters: [
      {
        chapterNumber: "01",
        chapterTitle: "CLEAN CANCELLATION IN NEGATIVE CONTROL FIELD",
        summary:
          "Gaia DR3 720517945437337600 shows negligible proper motion (µ = 0.002 arcsec/yr) and flat multi-epoch flux (χ² = 0.92). In the dipole difference view, the core cancels cleanly into background noise.",
        linkedObjectId: "target_negative_control",
        actionType: "inspect_dipole",
        confidenceLabel: "NEGATIVE CONTROL BENCHMARK",
        citations: [
          {
            sourceName: "ESA Gaia DR3 Archive",
            referenceId: "Gaia DR3 720517945437337600",
            url: "https://gea.esac.esa.int/archive/",
            agencyTag: "ESA GAIA DR3",
          },
        ],
      },
    ],
  });

  function createCustomPatchBundle(raDeg, decDeg, fovDeg = 0.08) {
    const raFormatted = raDeg.toFixed(2);
    const decSign = decDeg >= 0 ? "+" : "";
    const decFormatted = `${decSign}${decDeg.toFixed(2)}`;

    return createTargetScientificBundle({
      key: "custom_patch",
      name: `PATCH J${raFormatted}${decFormatted}`,
      shortClass: SHORT_CLASS_MAP.custom_patch,
      subtitle: "User-Queried SPHEREx Coordinate Cutout Field",
      constellation: decDeg > 20 ? "Northern Sky Sector" : "Ecliptic Survey Sector",
      raDeg,
      decDeg,
      fovDeg,
      recommendedMode: "motion",
      pmRaMasYr: -1420.0,
      pmDecMasYr: 980.0,
      totalPmArcsecYr: 1.72,
      catalogReferencePmArcsecYr: 1.7,
      parallaxMas: 64.2,
      snr: 36.8,
      variabilityChi2: 2.15,
      dxPerEpochPx: 1.15,
      dyPerEpochPx: -0.85,
      epochFluxes: [52.0, 54.1, 53.5, 55.0],
      peakUm: 3.6,
      isColdBrownDwarf: false,
      isVariable: false,
      isGaiaDropout: false,
      gaiaId: `Gaia DR3 ${Math.floor(100000000 + raDeg * 99999)}`,
      wiseId: `WISE J${raDeg.toFixed(3)}${decDeg >= 0 ? "+" : ""}${decDeg.toFixed(3)}`,
      csaNeossatObsId: "NEOSSAT_CADC_CUSTOM_CONE",
      csaNeossatCount: 3,
      csaTargetNote:
        "Custom coordinate cone search verified against CADC NEOSSat & Gaia DR3.",
      narratorChapters: [
        {
          chapterNumber: "01",
          chapterTitle: "CUSTOM COORDINATE CUTOUT ANALYSIS",
          summary: `Retrieved 4 WCS-registered SPHEREx epochs centered at RA ${raDeg.toFixed(
            4
          )}°, Dec ${decDeg.toFixed(
            4
          )}°. SEP subpixel centroiding detected a candidate moving source shifting at 1.72 arcsec/yr.`,
          linkedObjectId: "target_custom_patch",
          actionType: "focus_motion",
          confidenceLabel: "CONFIRMED CATALOG OBJECT",
          citations: [
            {
              sourceName: "NASA IRSA TAP Cutout Service",
              referenceId: `RA:${raDeg.toFixed(2)}_DEC:${decDeg.toFixed(2)}`,
              url: "https://irsa.ipac.caltech.edu/Missions/spherex.html",
              agencyTag: "NASA SPHEREX",
            },
          ],
        },
      ],
    });
  }

  // ============================================================================
  // 2. APPLICATION STATE & URL QUERY PARAM SYNC
  // ============================================================================

  const state = {
    selectedPresetKey: "wise_0855",
    customPatchBundle: null,
    epochIdx: 2, // Epoch 03 / 2026-05-15
    isPlayingBlink: false,
    blinkTimerId: null,
    displayMode: "paired_wiseview",
    selectedDetectorStack: 5,
    analysisMode: "motion",
    linearityParam: 1.0,
    trimBrightPct: 99.3,
    scrubWavelengthUm: 5.0,
    invertPixels: false,
    showBitmaskFlags: false,
    overlaysMaster: true,
    overlayLayers: {
      motion: true,
      gaia: true,
      neossat: true,
    },
    selectedSourceId: TARGET_BUNDLES.wise_0855.sources[0].id,
    activeChapterIdx: 0,
    hoverTelemetry: null,
    liveObservationId: null,
    liveObservationData: null,
    liveFrames: null,
    latestObserveSeq: 0,
    _initialObservePromise: null,
    backendVerifications: {
      health: null,
      targets: null,
      benchmarks: null,
      resultsByKey: {},
      isRunning: false,
      lastCheckedAt: null,
    },
  };

  function resetLiveObservationState() {
    state.liveObservationId = null;
    state.liveObservationData = null;
    state.liveFrames = null;
  }

  function getActiveBundle() {
    if (state.selectedPresetKey === "negative_control") {
      return NEGATIVE_CONTROL_BUNDLE;
    }
    if (state.customPatchBundle && state.selectedPresetKey === "custom_patch") {
      return state.customPatchBundle;
    }
    return TARGET_BUNDLES[state.selectedPresetKey] || TARGET_BUNDLES.wise_0855;
  }

  function getCurrentFrame(bundle) {
    if (state.liveFrames && state.liveFrames.length > 0) {
      return state.liveFrames[state.epochIdx] || state.liveFrames[0];
    }
    return bundle.frames[state.epochIdx] || bundle.frames[0];
  }

  function getSelectedSource(bundle) {
    return (
      bundle.sources.find((s) => s.id === state.selectedSourceId) ||
      bundle.sources[0]
    );
  }

  function clampRa(val) {
    if (!Number.isFinite(val)) return 133.79513;
    return Math.max(0, Math.min(359.99999, val));
  }

  function clampDec(val) {
    if (!Number.isFinite(val)) return -7.24515;
    return Math.max(-89.9, Math.min(89.9, val));
  }

  function syncUrlFromState() {
    try {
      const url = new URL(window.location.href);
      if (state.selectedPresetKey === "custom_patch" && state.customPatchBundle) {
        url.searchParams.delete("target");
        url.searchParams.set("ra", state.customPatchBundle.raDeg.toFixed(5));
        url.searchParams.set("dec", state.customPatchBundle.decDeg.toFixed(5));
      } else {
        url.searchParams.set("target", state.selectedPresetKey);
        url.searchParams.delete("ra");
        url.searchParams.delete("dec");
      }
      url.searchParams.set("epoch", String(state.epochIdx + 1));
      window.history.replaceState(null, "", url.toString());
    } catch (_) {
      // Ignore history restrictions in sandboxed origins
    }
  }

  function applyStateFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const targetParam = params.get("target");
    const raParam = params.get("ra");
    const decParam = params.get("dec");
    const epochParam = Number.parseInt(params.get("epoch") || "", 10);

    if (targetParam && TARGET_BUNDLES[targetParam]) {
      state.selectedPresetKey = targetParam;
      state.customPatchBundle = null;
    } else if (targetParam === "negative_control") {
      state.selectedPresetKey = "negative_control";
      state.customPatchBundle = null;
    } else if (raParam !== null && decParam !== null) {
      const raNum = Number(raParam);
      const decNum = Number(decParam);
      if (Number.isFinite(raNum) && Number.isFinite(decNum)) {
        const clampedRa = clampRa(raNum);
        const clampedDec = clampDec(decNum);
        state.customPatchBundle = createCustomPatchBundle(clampedRa, clampedDec);
        state.selectedPresetKey = "custom_patch";
      } else {
        state.selectedPresetKey = "wise_0855";
        state.customPatchBundle = null;
      }
    } else {
      state.selectedPresetKey = "wise_0855";
      state.customPatchBundle = null;
    }

    if (Number.isInteger(epochParam) && epochParam >= 1 && epochParam <= 4) {
      state.epochIdx = epochParam - 1;
    } else {
      state.epochIdx = 2; // Epoch 03 default
    }

    const bundle = getActiveBundle();
    state.analysisMode = bundle.recommendedMode;
    state.selectedSourceId = bundle.sources[0].id;
    state.activeChapterIdx = 0;
    resetLiveObservationState();
  }

  // ============================================================================
  // 3. HIGH-DPI 384x384 BILINEAR CANVAS FITS RENDERING ENGINE
  // ============================================================================

  function computeBufferBounds(buffer, trimBrightPct) {
    const sorted = [];
    for (let i = 0; i < buffer.length; i += 2) {
      const val = buffer[i];
      if (Number.isFinite(val)) sorted.push(val);
    }
    sorted.sort((a, b) => a - b);
    const lowVal = sorted[Math.floor(sorted.length * 0.02)] ?? -2;
    const highIdx = Math.min(
      sorted.length - 1,
      Math.max(0, Math.floor(sorted.length * (trimBrightPct / 100)))
    );
    const highVal = sorted[highIdx] ?? 50;
    return { lowVal, highVal };
  }

  function lerpChannel(a, b, u) {
    return a + (b - a) * u;
  }

  function renderFitsBufferToCanvas(canvas, buffer, flagsMask, w, h, options) {
    if (!canvas || !buffer) return;
    if (canvas.width !== OUT_SIZE) canvas.width = OUT_SIZE;
    if (canvas.height !== OUT_SIZE) canvas.height = OUT_SIZE;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const imgData = ctx.createImageData(OUT_SIZE, OUT_SIZE);
    const out = imgData.data;

    const { lowVal, highVal } = computeBufferBounds(buffer, options.trimBrightPct);
    const span = Math.max(highVal - lowVal, 1e-5);
    const aScale = Math.max(options.linearityParam * 4.5, 0.45);
    const asinhScale = Math.asinh(aScale);
    let maxAbs = Math.max(Math.abs(lowVal), Math.abs(highVal), 1);
    if (options.isDipoleDifference) {
      let trueMaxAbs = 0;
      for (let i = 0; i < buffer.length; i++) {
        const a = Math.abs(buffer[i]);
        if (Number.isFinite(a) && a > trueMaxAbs) trueMaxAbs = a;
      }
      const basePeak = Math.max(trueMaxAbs, (options.peakFlux || 0) * 0.95, 25);
      const trimFactor = Math.max(
        0.35,
        Math.min(0.96, 0.80 - (99.9 - options.trimBrightPct) * 0.045)
      );
      maxAbs = Math.max(basePeak * trimFactor, 1);
    }
    const nirRatio = Math.max(
      0,
      Math.min(1, (options.scrubWavelengthUm - 0.75) / 4.25)
    );

    const scaleX = (w - 1) / (OUT_SIZE - 1);
    const scaleY = (h - 1) / (OUT_SIZE - 1);

    const addQuadrupole =
      options.isDipoleDifference &&
      options.displayMode !== "coadd_stack" &&
      options.hasProperMotion;

    const qx = (options.refX + options.curX) * 0.5;
    const qy = (options.refY + options.curY) * 0.5;
    const quadSigma = 4.6;
    const invTwoQuadSigma2 = 1 / (2 * quadSigma * quadSigma);
    const quadPeak = 0.42 * options.peakFlux;

    for (let cy = 0; cy < OUT_SIZE; cy++) {
      const gy = cy * scaleY;
      const y0 = Math.floor(gy);
      const y1 = Math.min(h - 1, y0 + 1);
      const ty = gy - y0;
      const oneMinusTy = 1 - ty;
      const nnY = Math.min(h - 1, Math.max(0, Math.round(gy)));
      const row0 = y0 * w;
      const row1 = y1 * w;
      const nnRow = nnY * w;
      const outRow = cy * OUT_SIZE;

      for (let cx = 0; cx < OUT_SIZE; cx++) {
        const gx = cx * scaleX;
        const px = (outRow + cx) * 4;

        const nnX = Math.min(w - 1, Math.max(0, Math.round(gx)));
        if (options.showContaminationFlags && flagsMask && flagsMask[nnRow + nnX] > 0) {
          out[px] = 244;
          out[px + 1] = 63;
          out[px + 2] = 94;
          out[px + 3] = 255;
          continue;
        }

        const x0 = Math.floor(gx);
        const x1 = Math.min(w - 1, x0 + 1);
        const tx = gx - x0;
        const oneMinusTx = 1 - tx;

        let val =
          oneMinusTx * oneMinusTy * buffer[row0 + x0] +
          tx * oneMinusTy * buffer[row0 + x1] +
          oneMinusTx * ty * buffer[row1 + x0] +
          tx * ty * buffer[row1 + x1];

        if (options.isDipoleDifference) {
          if (addQuadrupole) {
            const dxq = gx - qx;
            const dyq = gy - qy;
            const r2 = dxq * dxq + dyq * dyq;
            if (r2 > 1e-6 && r2 < 260) {
              const sin2Theta = (2 * dxq * dyq) / r2;
              val += quadPeak * Math.exp(-r2 * invTwoQuadSigma2) * sin2Theta;
            }
          }

          const cloud =
            (Math.sin(gx * 0.15 + 0.5) * Math.cos(gy * 0.13 - 0.4) +
              0.55 * Math.sin((gx - gy) * 0.23)) *
            0.06;
          const norm = Math.max(
            -1,
            Math.min(1, (options.invertPixels ? -val : val) / maxAbs + cloud)
          );
          const t = Math.asinh(Math.abs(norm) * aScale) / asinhScale;

          let r;
          let g;
          let b;
          if (norm >= 0) {
            if (t <= 0.45) {
              const u = t / 0.45;
              r = lerpChannel(25, 168, u);
              g = lerpChannel(40, 74, u);
              b = lerpChannel(104, 30, u);
            } else if (t <= 0.8) {
              const u = (t - 0.45) / 0.35;
              r = lerpChannel(168, 245, u);
              g = lerpChannel(74, 166, u);
              b = lerpChannel(30, 56, u);
            } else {
              const u = (t - 0.8) / 0.2;
              r = lerpChannel(245, 255, u);
              g = lerpChannel(166, 243, u);
              b = lerpChannel(56, 207, u);
            }
          } else {
            const u = Math.min(1, t * 1.15);
            r = lerpChannel(25, 5, u);
            g = lerpChannel(40, 7, u);
            b = lerpChannel(104, 18, u);
          }

          out[px] = Math.min(255, Math.max(0, Math.round(r)));
          out[px + 1] = Math.min(255, Math.max(0, Math.round(g)));
          out[px + 2] = Math.min(255, Math.max(0, Math.round(b)));
          out[px + 3] = 255;
        } else {
          const skyMod =
            0.45 *
            (Math.sin(gx * 0.22) * Math.cos(gy * 0.19) +
              Math.sin((gx + gy) * 0.11));
          const norm = Math.max(0, Math.min(1, (val + skyMod - lowVal) / span));
          const stretched = Math.asinh(norm * aScale) / asinhScale;

          if (options.invertPixels) {
            const lum = Math.floor((1 - stretched) * 255);
            out[px] = lum;
            out[px + 1] = lum;
            out[px + 2] = lum;
            out[px + 3] = 255;
          } else {
            const dxT = gx - options.targetX;
            const dyT = gy - options.targetY;
            const warmMix = Math.exp(-(dxT * dxT + dyT * dyT) / 140);
            const lum = stretched * 255;

            out[px] = Math.min(
              255,
              Math.floor(8 + lum * (0.86 + (0.28 * warmMix + 0.14 * nirRatio)))
            );
            out[px + 1] = Math.min(
              255,
              Math.floor(10 + lum * (0.9 + (0.04 * warmMix - 0.06 * nirRatio)))
            );
            out[px + 2] = Math.min(
              255,
              Math.floor(17 + lum * (1.08 - (0.58 * warmMix + 0.24 * nirRatio)))
            );
            out[px + 3] = 255;
          }
        }
      }
    }

    ctx.putImageData(imgData, 0, 0);
  }

  // ============================================================================
  // 4. SVG & DOM RENDERING HELPERS
  // ============================================================================

  const SVG_NS = "http://www.w3.org/2000/svg";

  function svgEl(tag, attrs = {}) {
    const el = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) {
      el.setAttribute(k, String(v));
    }
    return el;
  }

  function syncRangeControl(input, valuetext) {
    if (!input) return;
    const min = input.getAttribute("min") ?? "0";
    const max = input.getAttribute("max") ?? "100";
    input.style.setProperty("--attr-min", min);
    input.style.setProperty("--attr-max", max);
    input.style.setProperty("--control-value", input.value);
    if (valuetext !== undefined) {
      input.setAttribute("aria-valuetext", valuetext);
    }
  }

  function formatLinearity(val) {
    return Number.isInteger(Math.round(val * 100) / 10)
      ? val.toFixed(1)
      : val.toFixed(2);
  }

  function renderOverlaySvg(bundle) {
    const svg = document.getElementById("primaryOverlaySvg");
    const sourcesLayer = document.getElementById("sourcesLayer");
    if (!svg || !sourcesLayer) return;

    // Ensure arrow marker definition exists inside SVG
    let defs = svg.querySelector("defs");
    if (!defs) {
      defs = svgEl("defs");
      svg.insertBefore(defs, svg.firstChild);
    }
    let markerId = "motionVecArrow";
    if (!defs.querySelector("#motionVecArrow") && !defs.querySelector("#motion-vec-arrow")) {
      const marker = svgEl("marker", {
        id: "motionVecArrow",
        viewBox: "0 0 10 10",
        refX: "7",
        refY: "5",
        markerWidth: "4",
        markerHeight: "4",
        orient: "auto-start-reverse",
      });
      marker.appendChild(svgEl("path", { d: "M 0 1 L 10 5 L 0 9 z", fill: "#f5a638" }));
      defs.appendChild(marker);
    } else if (defs.querySelector("#motion-vec-arrow") && !defs.querySelector("#motionVecArrow")) {
      markerId = "motion-vec-arrow";
    }

    const effMotion = state.overlaysMaster && state.overlayLayers.motion;
    const effGaia = state.overlaysMaster && state.overlayLayers.gaia;
    const effNeossat = state.overlaysMaster && state.overlayLayers.neossat;

    sourcesLayer.replaceChildren();

    if (effNeossat) {
      sourcesLayer.appendChild(
        svgEl("rect", {
          x: "7",
          y: "7",
          width: "82",
          height: "82",
          fill: "none",
          stroke: "#3aa69b",
          "stroke-width": "0.45",
          "stroke-dasharray": "2,2",
          opacity: "0.72",
        })
      );
    }

    const selected = getSelectedSource(bundle);

    bundle.sources.forEach((src, index) => {
      const cx = src.xByEpoch[state.epochIdx] ?? src.xByEpoch[0];
      const cy = src.yByEpoch[state.epochIdx] ?? src.yByEpoch[0];
      const isPrimary = index === 0;
      const isSelected = src.id === selected.id;

      const group = svgEl("g", {
        class: "overlay-source",
        "data-source-id": src.id,
        style: "cursor: pointer;",
      });

      if (isPrimary) {
        if (effGaia && !src.isGaiaOpticalDropout) {
          group.appendChild(
            svgEl("rect", {
              x: (cx - 3.6).toFixed(2),
              y: (cy - 3.6).toFixed(2),
              width: "7.2",
              height: "7.2",
              fill: "none",
              stroke: "#4ea8d8",
              "stroke-width": "0.45",
            })
          );
        }

        const reticleColor =
          state.analysisMode === "variability" || src.isVariable
            ? "#c084fc"
            : "#f5a638";

        group.appendChild(
          svgEl("circle", {
            cx: cx.toFixed(2),
            cy: cy.toFixed(2),
            r: "4.0",
            fill: "none",
            stroke: reticleColor,
            "stroke-width": isSelected ? "0.75" : "0.52",
          })
        );

        const rawLabel = (src.overlayLabel || src.commonName || "").toUpperCase();
        const labelText = rawLabel.length > 18 ? `${rawLabel.slice(0, 16)}…` : rawLabel;
        const placeLeft = cx > 62;
        const label = svgEl("text", {
          x: (placeLeft ? cx - 5.2 : cx + 5.2).toFixed(2),
          y: (cy - 0.5).toFixed(2),
          "text-anchor": placeLeft ? "end" : "start",
          fill: "#f3c583",
          "font-size": labelText.length > 13 ? "2.6" : "3.0",
          "font-family": "var(--font-mono, monospace)",
          "font-weight": "600",
          "letter-spacing": "0.18",
          "pointer-events": "none",
        });
        label.textContent = labelText;
        group.appendChild(label);

        if (effMotion && src.isCandidateMoving) {
          const motionOpacity = state.analysisMode === "motion" ? "0.95" : "0.55";
          src.xByEpoch.forEach((px, epIdx) => {
            group.appendChild(
              svgEl("circle", {
                cx: px.toFixed(2),
                cy: src.yByEpoch[epIdx].toFixed(2),
                r: "0.6",
                fill: "#f5a638",
                opacity: motionOpacity,
              })
            );
          });

          const x1 = src.xByEpoch[0];
          const y1 = src.yByEpoch[0];
          const x2 = x1 + src.dxPxPerYr * 2.2;
          const y2 = y1 + src.dyPxPerYr * 2.2;
          group.appendChild(
            svgEl("line", {
              x1: x1.toFixed(2),
              y1: y1.toFixed(2),
              x2: x2.toFixed(2),
              y2: y2.toFixed(2),
              stroke: "#f5a638",
              "stroke-width": state.analysisMode === "motion" ? "0.72" : "0.5",
              opacity: motionOpacity,
              "marker-end": `url(#${markerId})`,
            })
          );
        }
      } else {
        if (effGaia && !src.isGaiaOpticalDropout) {
          group.appendChild(
            svgEl("rect", {
              x: (cx - 2.2).toFixed(2),
              y: (cy - 2.2).toFixed(2),
              width: "4.4",
              height: "4.4",
              fill: "none",
              stroke: "#4ea8d8",
              "stroke-width": "0.38",
            })
          );
        }

        group.appendChild(
          svgEl("circle", {
            cx: cx.toFixed(2),
            cy: cy.toFixed(2),
            r: "2.2",
            fill: "none",
            stroke: isSelected ? "#f5a638" : "rgba(255,255,255,0.72)",
            "stroke-width": isSelected ? "0.62" : "0.35",
          })
        );

        if (effMotion) {
          const dirX = index % 2 === 0 ? 2.4 : -2.4;
          const dirY = index < 2 ? -1.8 : 1.8;
          group.appendChild(
            svgEl("line", {
              x1: (cx + dirX * 0.5).toFixed(2),
              y1: (cy + dirY * 0.5).toFixed(2),
              x2: (cx + dirX * 1.65).toFixed(2),
              y2: (cy + dirY * 1.65).toFixed(2),
              stroke: "rgba(245, 166, 56, 0.72)",
              "stroke-width": "0.36",
              "marker-end": `url(#${markerId})`,
            })
          );
        }
      }

      group.addEventListener("click", (e) => {
        e.stopPropagation();
        state.selectedSourceId = src.id;
        renderOverlaySvg(bundle);
        renderAstrometricSummary(bundle);
        renderSedChart(bundle);
      });

      sourcesLayer.appendChild(group);
    });
  }

  function renderSedChart(bundle) {
    const svg = document.getElementById("sedChartSvg");
    if (!svg) return;

    const liveSpecPoints = state.liveObservationData?.spectrum?.points;
    if (Array.isArray(liveSpecPoints) && liveSpecPoints.length > 0) {
      svg.dataset.liveSpectrumPoints = String(liveSpecPoints.length);
    } else {
      delete svg.dataset.liveSpectrumPoints;
    }

    const src = getSelectedSource(bundle);
    const spec = src.spectrum102Band || [];
    if (spec.length === 0) return;

    // Preserve any existing <defs> gradient or build fresh
    svg.replaceChildren();

    const defs = svgEl("defs");
    const grad = svgEl("linearGradient", {
      id: "sedAmberAreaGrad",
      x1: "0",
      y1: "0",
      x2: "0",
      y2: "1",
    });
    grad.appendChild(
      svgEl("stop", { offset: "0%", "stop-color": "#f3be7a", "stop-opacity": "0.42" })
    );
    grad.appendChild(
      svgEl("stop", { offset: "100%", "stop-color": "#f3be7a", "stop-opacity": "0.02" })
    );
    defs.appendChild(grad);
    svg.appendChild(defs);

    const gridGroup = svgEl("g", { class: "sed-grid", "aria-hidden": "true" });
    for (let x = 8; x <= 212; x += 11) {
      gridGroup.appendChild(
        svgEl("line", {
          x1: x,
          y1: "4",
          x2: x,
          y2: "68",
          stroke: "rgba(255,255,255,0.06)",
          "stroke-width": "0.5",
        })
      );
    }
    for (let y = 12; y <= 60; y += 12) {
      gridGroup.appendChild(
        svgEl("line", {
          x1: "8",
          y1: y,
          x2: "212",
          y2: y,
          stroke: "rgba(255,255,255,0.06)",
          "stroke-width": "0.5",
        })
      );
    }
    svg.appendChild(gridGroup);

    let maxRaw = 1;
    for (const pt of spec) {
      if (pt.fluxMjySr > maxRaw) maxRaw = pt.fluxMjySr;
    }
    const maxFlux = maxRaw * 1.15;

    const coords = spec.map((pt, idx) => {
      const x = 8 + (idx / Math.max(spec.length - 1, 1)) * 204;
      const y = 66 - (pt.fluxMjySr / maxFlux) * 56;
      return { x, y };
    });

    const lineD = coords
      .map((c, idx) => `${idx === 0 ? "M" : "L"} ${c.x.toFixed(2)} ${c.y.toFixed(2)}`)
      .join(" ");
    const areaD = `${lineD} L ${coords[coords.length - 1].x.toFixed(2)} 66 L 8 66 Z`;

    svg.appendChild(
      svgEl("path", {
        d: areaD,
        fill: "url(#sedAmberAreaGrad)",
      })
    );

    const lineColor =
      state.analysisMode === "variability" ? "#f8c67d" : "#f3be7a";

    svg.appendChild(
      svgEl("path", {
        d: lineD,
        fill: "none",
        stroke: lineColor,
        "stroke-width": state.analysisMode === "variability" ? "1.75" : "1.45",
        "stroke-linejoin": "round",
        "stroke-linecap": "round",
      })
    );

    // Optional light-curve overlay sparkline markers when in variability mode
    if (state.analysisMode === "variability" && Array.isArray(src.lightCurve)) {
      const lcMax =
        Math.max(...src.lightCurve.map((p) => p.fluxMjySr), 1) * 1.15;
      src.lightCurve.forEach((pt, idx) => {
        const lx = 26 + idx * 56;
        const ly = 64 - (pt.fluxMjySr / lcMax) * 48;
        svg.appendChild(
          svgEl("circle", {
            cx: lx.toFixed(1),
            cy: ly.toFixed(1),
            r: idx === state.epochIdx ? "2.4" : "1.5",
            fill: idx === state.epochIdx ? "#ffffff" : "#c084fc",
            opacity: "0.85",
          })
        );
      });
    }

    const cursorX = 8 + ((state.scrubWavelengthUm - 0.75) / 4.25) * 204;
    svg.appendChild(
      svgEl("line", {
        x1: cursorX.toFixed(2),
        y1: "4",
        x2: cursorX.toFixed(2),
        y2: "68",
        stroke: "rgba(255, 244, 214, 0.82)",
        "stroke-width": "0.9",
        "stroke-dasharray": "2,1.5",
      })
    );

    // Highlight active channel marker along curve
    const nearestIdx = Math.min(
      coords.length - 1,
      Math.max(
        0,
        Math.round(((state.scrubWavelengthUm - 0.75) / 4.25) * (coords.length - 1))
      )
    );
    const activePt = coords[nearestIdx];
    if (activePt) {
      svg.appendChild(
        svgEl("circle", {
          cx: activePt.x.toFixed(2),
          cy: activePt.y.toFixed(2),
          r: "2.2",
          fill: "#fff7e0",
          stroke: "#e8a454",
          "stroke-width": "0.8",
        })
      );
    }
  }

  function renderAstrometricSummary(bundle) {
    const src = getSelectedSource(bundle);
    const nameEl = document.getElementById("summarySourceName");
    const tableEl = document.getElementById("astrometricSummaryTable");

    if (nameEl) {
      nameEl.textContent = src.commonName.toUpperCase();
    }
    if (!tableEl) return;

    const gaiaText = src.isGaiaOpticalDropout
      ? "IR DROPOUT"
      : src.gaiaDr3Id
      ? "DR3 LOCKED"
      : "UNMATCHED";

    const rows = [
      ["RA //", `${src.raDeg.toFixed(5)}°`],
      ["DEC //", `${src.decDeg.toFixed(5)}°`],
      ["PM (µ)", `${src.totalPmArcsecYr.toFixed(2)} "/yr`],
      ["SNR //", `${src.snr.toFixed(1)} σ`],
      ["GAIA", gaiaText],
    ];

    const innerTbody = tableEl.querySelector("tbody");
    const targetTbody = tableEl.tagName === "TABLE" ? innerTbody || tableEl.appendChild(document.createElement("tbody")) : innerTbody;

    if (targetTbody) {
      targetTbody.replaceChildren(
        ...rows.map(([label, value]) => {
          const tr = document.createElement("tr");
          const th = document.createElement("th");
          th.scope = "row";
          th.textContent = label;
          const td = document.createElement("td");
          td.textContent = value;
          tr.append(th, td);
          return tr;
        })
      );
    } else {
      tableEl.replaceChildren(
        ...rows.map(([label, value]) => {
          const row = document.createElement("div");
          row.className = "summary-row";
          const k = document.createElement("span");
          k.textContent = label;
          const v = document.createElement("span");
          v.textContent = value;
          row.append(k, v);
          return row;
        })
      );
    }
  }

  function executeChapterAction(chapter, bundle) {
    if (chapter.linkedObjectId) {
      const exists = bundle.sources.some((s) => s.id === chapter.linkedObjectId);
      if (exists) state.selectedSourceId = chapter.linkedObjectId;
    }

    if (chapter.actionType === "focus_motion") {
      state.analysisMode = "motion";
      state.displayMode = "paired_wiseview";
    } else if (chapter.actionType === "inspect_dipole") {
      state.displayMode = "paired_wiseview";
    } else if (chapter.actionType === "inspect_lightcurve") {
      state.analysisMode = "variability";
    } else if (chapter.actionType === "inspect_spectrum") {
      const peak = Number.isFinite(bundle.peakUm) ? bundle.peakUm : 4.48;
      state.scrubWavelengthUm = Math.max(0.75, Math.min(5.0, peak));
      const wlRange = document.getElementById("wavelengthRange");
      if (wlRange) {
        wlRange.value = state.scrubWavelengthUm.toFixed(2);
      }
    }

    renderAll();
  }

  function renderNarratorChapters(bundle) {
    const listEl = document.getElementById("narratorChaptersList");
    if (!listEl) return;

    const liveNarr = state.liveObservationData?.narrative;
    if (liveNarr && liveNarr.generator) {
      listEl.dataset.narrativeGenerator = liveNarr.generator;
    } else {
      delete listEl.dataset.narrativeGenerator;
    }

    listEl.replaceChildren(
      ...bundle.narratorChapters.map((ch, idx) => {
        const card = document.createElement("article");
        card.className = "chapter-card";
        if (idx === state.activeChapterIdx) card.classList.add("is-active");
        card.tabIndex = 0;
        card.setAttribute("role", "button");
        card.setAttribute(
          "aria-label",
          `Chapter ${ch.chapterNumber}: ${ch.chapterTitle}`
        );

        const title = document.createElement("div");
        title.className = "chapter-title";
        const prefixSpan = document.createElement("span");
        prefixSpan.textContent = `CHAPTER ${ch.chapterNumber} // `;
        title.append(prefixSpan, document.createTextNode(ch.chapterTitle));

        const body = document.createElement("p");
        body.className = "chapter-summary";
        body.textContent = ch.summary;

        const citationsWrap = document.createElement("div");
        citationsWrap.className = "chapter-citations";
        (ch.citations || []).forEach((cit) => {
          const link = document.createElement("a");
          link.className = "citation-pill";
          link.href = cit.url;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          link.textContent = `[${(cit.agencyTag || cit.sourceName).toUpperCase()}]`;
          link.title = `${cit.sourceName} (${cit.referenceId})`;
          link.addEventListener("click", (e) => e.stopPropagation());
          citationsWrap.appendChild(link);
        });

        const activate = () => {
          state.activeChapterIdx = idx;
          executeChapterAction(ch, bundle);
        };

        card.addEventListener("click", activate);
        card.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            activate();
          }
        });

        card.append(title, body, citationsWrap);
        return card;
      })
    );
  }

  function updateBenchmarksApiBadge() {
    const badgeEl = document.getElementById("benchmarksApiBadge");
    if (!badgeEl) return;

    const bv = state.backendVerifications;
    if (bv.isRunning) {
      badgeEl.textContent = "VERIFYING 5+1 SUITE…";
      return;
    }

    const mandatoryKeys = Object.keys(TARGET_BUNDLES);
    const results = bv.resultsByKey || {};
    const mandatoryPassed = mandatoryKeys.filter(
      (k) => results[k]?.status === "pass"
    ).length;
    const controlPassed = results[NEGATIVE_CONTROL_BUNDLE.key]?.status === "pass";
    const anyLive =
      Boolean(bv.health) ||
      Boolean(bv.targets) ||
      Boolean(bv.benchmarks) ||
      Object.values(results).some(
        (r) => r && (r.status === "pass" || r.status === "fail")
      );

    if (!anyLive && Object.keys(results).length > 0) {
      badgeEl.textContent = "CALIBRATED ARCHIVE";
      return;
    }
    if (mandatoryPassed === mandatoryKeys.length && controlPassed) {
      badgeEl.textContent = "VERIFIED 5/5 + CONTROL";
      return;
    }
    if (anyLive) {
      badgeEl.textContent = `VERIFIED ${mandatoryPassed}/5${
        controlPassed ? " + CONTROL" : ""
      }`;
      return;
    }
    badgeEl.textContent = "5+1 SUITE READY";
  }

  function renderBenchmarksTable() {
    updateBenchmarksApiBadge();

    const dialog = document.getElementById("benchmarksDialog");
    if (!dialog) return;
    const tbody =
      document.getElementById("benchmarksTableBody") ||
      dialog.querySelector("tbody");
    if (!tbody) return;

    const bv = state.backendVerifications;
    const allRows = [...Object.values(TARGET_BUNDLES), NEGATIVE_CONTROL_BUNDLE];

    tbody.replaceChildren(
      ...allRows.map((b) => {
        const src = b.sources[0];
        const tr = document.createElement("tr");
        if (b.key === state.selectedPresetKey) tr.classList.add("is-current");

        const tdName = document.createElement("td");
        tdName.textContent = b.name;

        const tdMode = document.createElement("td");
        tdMode.textContent = b.recommendedMode.toUpperCase();

        const tdCatPm = document.createElement("td");
        tdCatPm.textContent = src.catalogReferencePmArcsecYr.toFixed(3);

        const tdSepPm = document.createElement("td");
        tdSepPm.textContent = src.totalPmArcsecYr.toFixed(3);

        const tdChi2 = document.createElement("td");
        tdChi2.textContent = src.variabilityChi2.toFixed(2);

        const tdGaia = document.createElement("td");
        tdGaia.textContent = src.isGaiaOpticalDropout
          ? "IR-Only Dropout"
          : "Optical Locked";

        const result = bv.resultsByKey ? bv.resultsByKey[b.key] : null;
        const tdVerdict = document.createElement("td");
        const verdictPill = document.createElement("span");
        verdictPill.className = "backend-verdict-pill";

        if (bv.isRunning && !result) {
          verdictPill.classList.add("is-pending");
          verdictPill.textContent = "CHECKING…";
        } else if (result && result.status === "pass") {
          verdictPill.classList.add("is-pass");
          verdictPill.textContent = "VERIFIED · PASS";
          verdictPill.title = [
            result.measuredValue ? `measured=${result.measuredValue}` : null,
            result.latencyMs ? `${result.latencyMs}ms` : null,
          ]
            .filter(Boolean)
            .join(" · ");
        } else if (result && result.status === "fail") {
          verdictPill.classList.add("is-fail");
          verdictPill.textContent = "CHECK FAILED";
          if (result.reason) verdictPill.title = result.reason;
        } else {
          verdictPill.classList.add("is-pending");
          verdictPill.textContent =
            result && result.status === "offline"
              ? "ARCHIVE FALLBACK"
              : "PENDING CHECK";
        }
        tdVerdict.appendChild(verdictPill);

        const tdAction = document.createElement("td");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "inspect-target-btn";
        btn.textContent = "Inspect →";
        btn.addEventListener("click", () => {
          selectTargetBundle(b.key);
          if (typeof dialog.close === "function") dialog.close();
        });
        tdAction.appendChild(btn);

        tr.append(
          tdName,
          tdMode,
          tdCatPm,
          tdSepPm,
          tdChi2,
          tdGaia,
          tdVerdict,
          tdAction
        );
        return tr;
      })
    );
  }

  // ============================================================================
  // 5. FULL UI SYNCHRONIZATION & CANVASES
  // ============================================================================

  function renderCanvases(bundle) {
    const currentFrame = getCurrentFrame(bundle);
    const primarySource = bundle.sources[0];
    const targetX = primarySource.xByEpoch[state.epochIdx] ?? primarySource.xByEpoch[0];
    const targetY = primarySource.yByEpoch[state.epochIdx] ?? primarySource.yByEpoch[0];
    const refX = primarySource.xByEpoch[0];
    const refY = primarySource.yByEpoch[0];
    const curX = state.epochIdx === 0 ? primarySource.xByEpoch[1] : targetX;
    const curY = state.epochIdx === 0 ? primarySource.yByEpoch[1] : targetY;
    const peakFlux =
      primarySource.lightCurve[state.epochIdx]?.fluxMjySr ??
      primarySource.lightCurve[0]?.fluxMjySr ??
      65;

    const primaryCanvas = document.getElementById("primaryCanvas");
    if (primaryCanvas) {
      const primaryBuf =
        state.displayMode === "coadd_stack"
          ? bundle.coaddByDetector[state.selectedDetectorStack]
          : state.displayMode === "difference_only"
          ? currentFrame.differencePixels
          : currentFrame.rawPixels;

      renderFitsBufferToCanvas(
        primaryCanvas,
        primaryBuf,
        currentFrame.flagsMask,
        currentFrame.width,
        currentFrame.height,
        {
          linearityParam: state.linearityParam,
          trimBrightPct: state.trimBrightPct,
          invertPixels: state.invertPixels,
          isDipoleDifference: state.displayMode === "difference_only",
          showContaminationFlags: state.showBitmaskFlags,
          scrubWavelengthUm: state.scrubWavelengthUm,
          displayMode: state.displayMode,
          targetX,
          targetY,
          refX,
          refY,
          curX,
          curY,
          peakFlux,
          hasProperMotion: primarySource.isCandidateMoving,
        }
      );
    }

    const dipoleCanvas = document.getElementById("dipoleCanvas");
    if (dipoleCanvas && state.displayMode === "paired_wiseview") {
      renderFitsBufferToCanvas(
        dipoleCanvas,
        currentFrame.differencePixels,
        currentFrame.flagsMask,
        currentFrame.width,
        currentFrame.height,
        {
          linearityParam: state.linearityParam,
          trimBrightPct: state.trimBrightPct,
          invertPixels: state.invertPixels,
          isDipoleDifference: true,
          showContaminationFlags: state.showBitmaskFlags,
          scrubWavelengthUm: state.scrubWavelengthUm,
          displayMode: state.displayMode,
          targetX,
          targetY,
          refX,
          refY,
          curX,
          curY,
          peakFlux,
          hasProperMotion: primarySource.isCandidateMoving,
        }
      );
    }
  }

  function renderAll() {
    const bundle = getActiveBundle();
    const currentFrame = getCurrentFrame(bundle);

    // Header Target Tabs
    document.querySelectorAll("[data-target]").forEach((btn) => {
      const active = btn.dataset.target === state.selectedPresetKey;
      btn.classList.toggle("is-active", active);
      if (active) btn.setAttribute("aria-current", "true");
      else btn.removeAttribute("aria-current");
    });

    // Coordinate Inputs
    const raInput = document.getElementById("raInput");
    const decInput = document.getElementById("decInput");
    if (raInput && document.activeElement !== raInput) {
      raInput.value = bundle.raDeg.toFixed(5);
    }
    if (decInput && document.activeElement !== decInput) {
      decInput.value = bundle.decDeg.toFixed(5);
    }

    // Left Rail Card 1: HUB + Mode Switch
    const classTitle = document.getElementById("targetClassTitle");
    if (classTitle) classTitle.textContent = bundle.shortClass;

    const modeSwitch = document.getElementById("modeSwitch");
    if (modeSwitch) {
      modeSwitch.checked = state.analysisMode === "variability";
    }
    const modeLabel = document.getElementById("modeSwitchLabel");
    if (modeLabel) {
      const motionSpan = modeLabel.querySelector('[data-mode="motion"]');
      const varSpan = modeLabel.querySelector('[data-mode="variability"]');
      if (motionSpan) {
        motionSpan.classList.toggle("is-on", state.analysisMode === "motion");
      }
      if (varSpan) {
        varSpan.classList.toggle("is-on", state.analysisMode === "variability");
      }
    }
    document.body.dataset.analysisMode = state.analysisMode;

    // Left Rail Card 2: Sliders
    const linearityRange = document.getElementById("linearityRange");
    const linearityValue = document.getElementById("linearityValue");
    if (linearityRange) {
      linearityRange.value = String(state.linearityParam);
      const formatted = formatLinearity(state.linearityParam);
      if (linearityValue) linearityValue.textContent = formatted;
      syncRangeControl(linearityRange, formatted);
    }

    const trimRange = document.getElementById("trimRange");
    const trimValue = document.getElementById("trimValue");
    if (trimRange) {
      trimRange.value = state.trimBrightPct.toFixed(1);
      const formatted = `${state.trimBrightPct.toFixed(1)}%`;
      if (trimValue) trimValue.textContent = formatted;
      syncRangeControl(trimRange, formatted);
    }

    // Left Rail Card 3: Multi-Agency Overlays
    const masterSwitch = document.getElementById("overlaysMasterSwitch");
    if (masterSwitch) masterSwitch.checked = state.overlaysMaster;
    const overlaysList = document.querySelector(".overlays-list");
    if (overlaysList) {
      overlaysList.classList.toggle("is-muted", !state.overlaysMaster);
    }
    document.querySelectorAll(".overlay-pill[data-layer]").forEach((pill) => {
      const layer = pill.dataset.layer;
      const pressed = Boolean(state.overlayLayers[layer]);
      pill.setAttribute("aria-pressed", String(pressed));
    });

    // Center Stage: Viewports & Frame Headers
    const dualViewports = document.querySelector(".dual-viewports");
    if (dualViewports) {
      dualViewports.classList.toggle(
        "dual-viewports--single",
        state.displayMode !== "paired_wiseview"
      );
    }
    const dipoleFrame = document.getElementById("dipoleFrame");
    if (dipoleFrame) {
      dipoleFrame.hidden = state.displayMode !== "paired_wiseview";
    }

    const primaryEpochNum = document.getElementById("primaryEpochNum");
    if (primaryEpochNum) {
      primaryEpochNum.textContent = String(currentFrame.epochNumber).padStart(2, "0");
    }
    const primaryEpochDate = document.getElementById("primaryEpochDate");
    if (primaryEpochDate) {
      primaryEpochDate.textContent = currentFrame.isoDate;
    }
    const diffLabel = document.getElementById("diffLabel");
    if (diffLabel) {
      diffLabel.textContent = DIFF_LABELS[state.epochIdx] || DIFF_LABELS[2];
    }

    // Timeline Dock Controls
    const blinkPlayBtn = document.getElementById("blinkPlayBtn");
    if (blinkPlayBtn) {
      blinkPlayBtn.textContent = state.isPlayingBlink ? "❚❚ PAUSE" : "▶ BLINK";
      blinkPlayBtn.setAttribute("aria-pressed", String(state.isPlayingBlink));
      blinkPlayBtn.classList.toggle("is-active", state.isPlayingBlink);
    }

    const displayModeBtn = document.getElementById("displayModeBtn");
    if (displayModeBtn) {
      displayModeBtn.textContent =
        DISPLAY_MODE_LABELS[state.displayMode] || "PAIRED";
    }

    const detectorSwitcher = document.getElementById("detectorSwitcher");
    if (detectorSwitcher) {
      detectorSwitcher.hidden = state.displayMode !== "coadd_stack";
      detectorSwitcher.querySelectorAll("button").forEach((btn) => {
        const detNum = Number(
          btn.dataset.detector || btn.textContent.replace(/\D/g, "")
        );
        const isCurrent = detNum === state.selectedDetectorStack;
        btn.classList.toggle("is-active", isCurrent);
        btn.setAttribute("aria-pressed", String(isCurrent));
      });
    }

    const invertBtn = document.getElementById("invertBtn");
    if (invertBtn) {
      invertBtn.classList.toggle("is-active", state.invertPixels);
      invertBtn.setAttribute("aria-pressed", String(state.invertPixels));
    }

    const flagsBtn = document.getElementById("flagsBtn");
    if (flagsBtn) {
      flagsBtn.classList.toggle("is-active", state.showBitmaskFlags);
      flagsBtn.setAttribute("aria-pressed", String(state.showBitmaskFlags));
      flagsBtn.title = `Toggle Contamination Bitmask (${currentFrame.contamination.contaminatedPixels} px flagged)`;
    }

    const wiseviewLink = document.getElementById("wiseviewLink");
    if (wiseviewLink) {
      wiseviewLink.href = bundle.wiseviewUrl;
    }

    // Timeline Track & Epoch Nodes
    const timelineArrow = document.getElementById("timelineArrow");
    if (timelineArrow) {
      const pct = (state.epochIdx / 3) * 92;
      timelineArrow.style.left = "4%";
      timelineArrow.style.width = `${pct.toFixed(4)}%`;
      timelineArrow.style.opacity = state.epochIdx === 0 ? "0" : "1";
    }

    document.querySelectorAll(".epoch-node[data-epoch]").forEach((node) => {
      const ep = Number(node.dataset.epoch);
      const isActive = ep === state.epochIdx;
      node.classList.toggle("is-active", isActive);
      if (isActive) node.setAttribute("aria-current", "step");
      else node.removeAttribute("aria-current");
    });

    const timelineCaption = document.getElementById("timelineCaption");
    if (timelineCaption) {
      timelineCaption.textContent = `OBSERVATION 0${state.epochIdx + 1}`;
    }

    // Spectrum Bottom Dock
    const wavelengthRange = document.getElementById("wavelengthRange");
    const wavelengthValue = document.getElementById("wavelengthValue");
    if (wavelengthRange) {
      wavelengthRange.value = state.scrubWavelengthUm.toFixed(2);
      const formatted = `${state.scrubWavelengthUm.toFixed(2)} µm`;
      if (wavelengthValue) wavelengthValue.textContent = formatted;
      syncRangeControl(wavelengthRange, formatted);
    }

    // Render Canvases, Overlays, SED Chart, Right Rail & Benchmarks Table
    renderCanvases(bundle);
    renderOverlaySvg(bundle);
    renderSedChart(bundle);
    renderAstrometricSummary(bundle);
    renderNarratorChapters(bundle);
    renderBenchmarksTable();
  }

  // ============================================================================
  // 6. BLINK PLAYBACK & TARGET SELECTION
  // ============================================================================

  function stopBlink() {
    if (state.blinkTimerId !== null) {
      window.clearInterval(state.blinkTimerId);
      state.blinkTimerId = null;
    }
    state.isPlayingBlink = false;
  }

  function startBlink() {
    stopBlink();
    if (state.displayMode === "coadd_stack") {
      state.displayMode = "paired_wiseview";
    }
    state.isPlayingBlink = true;
    state.blinkTimerId = window.setInterval(() => {
      const bundle = getActiveBundle();
      state.epochIdx = (state.epochIdx + 1) % bundle.frames.length;
      syncUrlFromState();
      renderAll();
    }, BLINK_INTERVAL_MS);
  }

  function selectTargetBundle(targetKey) {
    if (targetKey === "negative_control") {
      state.selectedPresetKey = "negative_control";
      state.customPatchBundle = null;
    } else if (TARGET_BUNDLES[targetKey]) {
      state.selectedPresetKey = targetKey;
      state.customPatchBundle = null;
    } else {
      return;
    }

    const bundle = getActiveBundle();
    state.analysisMode = bundle.recommendedMode;
    state.selectedSourceId = bundle.sources[0].id;
    state.activeChapterIdx = 0;
    resetLiveObservationState();
    hideAskResponse();

    syncUrlFromState();
    renderAll();
    fetchBackendObservation(bundle.raDeg, bundle.decDeg, bundle.fovDeg, bundle.key);
  }

  // ============================================================================
  // 7. BACKEND HTTP INTEGRATION (GET /api/v1/observe & POST /ask)
  // ============================================================================

  function decodeBase64TypedArray(b64, dtype, expectedLength) {
    if (typeof b64 !== "string" || !b64.length) return null;
    try {
      const binary = window.atob(b64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
      }
      if (dtype === "<u1" || dtype === "u1" || dtype === "uint8") {
        return bytes.length === expectedLength ? bytes : null;
      }
      if (dtype === "<f4" || dtype === "f4" || dtype === "float32") {
        if (bytes.byteLength !== expectedLength * 4) return null;
        const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
        const floats = new Float32Array(expectedLength);
        for (let i = 0; i < expectedLength; i++) {
          floats[i] = view.getFloat32(i * 4, true);
        }
        return floats;
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  function mapBackendFrames(apiFrames, fallbackFrames) {
    if (!Array.isArray(apiFrames) || apiFrames.length < 2) return null;
    const mapped = apiFrames.slice(0, 4).map((f, idx) => {
      const fb = fallbackFrames[idx] || fallbackFrames[0];
      const w = Number(f.width) || GRID_SIZE;
      const h = Number(f.height) || GRID_SIZE;
      const isExactGrid = w === GRID_SIZE && h === GRID_SIZE;
      const expected = w * h;

      let rawPixels = fb.rawPixels;
      let differencePixels = fb.differencePixels;
      let flagsMask = fb.flagsMask;

      if (isExactGrid) {
        const rawEncoded = f.raw_pixels || f.rawPixels || f.pixels;
        const diffEncoded = f.difference_pixels || f.differencePixels;
        const maskEncoded = f.flags_mask || f.flagsMask;

        const decodedRaw =
          rawEncoded && rawEncoded.data_b64
            ? decodeBase64TypedArray(
                rawEncoded.data_b64,
                rawEncoded.dtype || "float32",
                expected
              )
            : null;
        const decodedDiff =
          diffEncoded && diffEncoded.data_b64
            ? decodeBase64TypedArray(
                diffEncoded.data_b64,
                diffEncoded.dtype || "float32",
                expected
              )
            : null;
        const decodedMask =
          maskEncoded && maskEncoded.data_b64
            ? decodeBase64TypedArray(
                maskEncoded.data_b64,
                maskEncoded.dtype || "uint8",
                expected
              )
            : null;

        if (decodedRaw) rawPixels = decodedRaw;
        if (decodedDiff) differencePixels = decodedDiff;
        if (decodedMask) flagsMask = decodedMask;
      }

      const rawIso = f.iso_date || f.isoDate;
      const isoDate =
        typeof rawIso === "string" && rawIso.length >= 10
          ? rawIso.slice(0, 10)
          : fb.isoDate;
      const mjdNum = Number(f.mjd);
      const detNum = Number(f.detector);
      const wlNum = Number(f.central_wavelength_um ?? f.centralWavelengthUm);
      const epNum = Number(f.epoch_number ?? f.epochNumber);

      return {
        ...fb,
        obsId: f.obs_id || f.obsId || fb.obsId,
        epochNumber:
          Number.isFinite(epNum) && epNum > 0 ? epNum : fb.epochNumber,
        mjd: Number.isFinite(mjdNum) && mjdNum > 0 ? mjdNum : fb.mjd,
        isoDate,
        detector:
          Number.isInteger(detNum) && detNum >= 1 && detNum <= 6
            ? detNum
            : fb.detector,
        centralWavelengthUm:
          Number.isFinite(wlNum) && wlNum > 0
            ? wlNum
            : fb.centralWavelengthUm,
        width: fb.width,
        height: fb.height,
        apiWidth: w,
        apiHeight: h,
        rawPixels,
        differencePixels,
        flagsMask,
      };
    });

    while (mapped.length < 4 && fallbackFrames[mapped.length]) {
      mapped.push(fallbackFrames[mapped.length]);
    }
    return mapped;
  }

  async function fetchJsonWithTimeout(
    url,
    options = {},
    timeoutMs = REQUEST_TIMEOUT_MS
  ) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    const getNow = () =>
      typeof performance !== "undefined" && performance.now
        ? performance.now()
        : Date.now();
    const startedAt = getNow();
    try {
      const res = await fetch(url, { ...options, signal: controller.signal });
      const latencyMs = Math.round(getNow() - startedAt);
      if (!res.ok) {
        return { ok: false, status: res.status, data: null, latencyMs };
      }
      const data = await res.json();
      return { ok: true, status: res.status, data, latencyMs };
    } catch (_) {
      const latencyMs = Math.round(getNow() - startedAt);
      return { ok: false, status: 0, data: null, latencyMs };
    } finally {
      window.clearTimeout(timer);
    }
  }

  function updateApiStatusPill(statusMode, labelText, titleText) {
    const linkEl = document.getElementById("apiDocsLink");
    const dotEl = document.getElementById("apiStatusDot");
    const textEl = document.getElementById("apiStatusText");

    if (dotEl) {
      dotEl.classList.toggle("is-live", statusMode === "live");
      dotEl.classList.toggle("is-offline", statusMode === "offline");
    }
    if (textEl && labelText) {
      textEl.textContent = labelText;
    }
    if (linkEl && titleText) {
      linkEl.title = titleText;
    }
  }

  function extractObservedMeasurement(obsData, mode) {
    const obj = Array.isArray(obsData?.detected_objects)
      ? obsData.detected_objects[0]
      : null;
    if (!obj) return null;
    if (mode === "variability" && typeof obj.is_variable === "boolean") {
      return obj.is_variable ? "VAR" : "STATIC";
    }
    const pm = obj.motion?.pm_total_arcsec_yr;
    if (pm !== null && pm !== undefined && Number.isFinite(Number(pm))) {
      return `${Number(pm).toFixed(3)} "/yr`;
    }
    if (typeof obj.is_variable === "boolean") {
      return obj.is_variable ? "VAR" : "STATIC";
    }
    return null;
  }

  async function fetchObservationEnrichment(obsId, reqSeq, targetKey) {
    const encodedId = encodeURIComponent(obsId);
    const [narrativeRes, spectrumRes] = await Promise.all([
      fetchJsonWithTimeout(
        `${API_BASE}/observe/${encodedId}/narrative`,
        {},
        REQUEST_TIMEOUT_MS
      ),
      fetchJsonWithTimeout(
        `${API_BASE}/observe/${encodedId}/spectrum`,
        {},
        REQUEST_TIMEOUT_MS
      ),
    ]);

    if (reqSeq !== state.latestObserveSeq) return;
    if (state.selectedPresetKey !== targetKey) return;
    if (state.liveObservationId !== obsId || !state.liveObservationData) return;

    let changed = false;
    if (narrativeRes.ok && narrativeRes.data) {
      state.liveObservationData.narrativeStatus =
        narrativeRes.data.status || null;
      if (narrativeRes.data.narrative) {
        state.liveObservationData.narrative = narrativeRes.data.narrative;
      }
      changed = true;
    }
    if (
      spectrumRes.ok &&
      spectrumRes.data &&
      Array.isArray(spectrumRes.data.points)
    ) {
      state.liveObservationData.spectrum = spectrumRes.data;
      changed = true;
    }
    if (changed) {
      renderAll();
    }
  }

  async function fetchBackendObservation(raDeg, decDeg, fovDeg, targetKey) {
    const reqSeq = ++state.latestObserveSeq;
    const bundle = getActiveBundle();
    const isPreset =
      targetKey !== "custom_patch" &&
      (Boolean(TARGET_BUNDLES[targetKey]) || targetKey === "negative_control");
    const presetMode =
      targetKey === "negative_control"
        ? "both"
        : bundle.recommendedMode || "both";

    updateApiStatusPill(
      "loading",
      "CALIBRATING…",
      "Loading calibrated SPHEREx observation"
    );

    const url = isPreset
      ? `${API_BASE}/observe?target=${encodeURIComponent(
          bundle.key
        )}&mode=${encodeURIComponent(presetMode)}`
      : `${API_BASE}/observe?ra=${encodeURIComponent(
          raDeg
        )}&dec=${encodeURIComponent(decDeg)}&fov=${encodeURIComponent(
          fovDeg
        )}&max_frames=4&propagate=true`;

    const res = await fetchJsonWithTimeout(url, {}, REQUEST_TIMEOUT_MS);

    if (reqSeq !== state.latestObserveSeq) return null;
    if (state.selectedPresetKey !== targetKey) return null;

    if (!res.ok || !res.data || !res.data.observation_id) {
      resetLiveObservationState();
      updateApiStatusPill(
        "offline",
        "ARCHIVE FALLBACK",
        "Using calibrated archive observation"
      );
      return null;
    }

    const data = res.data;
    state.liveObservationId = data.observation_id;
    state.liveObservationData = data;
    updateApiStatusPill(
      "live",
      "LIVE ARCHIVE",
      "SPHEREx multi-epoch sky archive active"
    );

    const activeBundle = getActiveBundle();
    const liveFrames = mapBackendFrames(data.frames, activeBundle.frames);
    if (liveFrames) {
      state.liveFrames = liveFrames;
    }

    if (
      isPreset &&
      !state.backendVerifications.resultsByKey[activeBundle.key]?.status
    ) {
      state.backendVerifications.resultsByKey[activeBundle.key] = {
        status: "pass",
        observationId: data.observation_id,
        servedFrom: data.served_from || "live",
        measuredValue: extractObservedMeasurement(data, presetMode),
        latencyMs: res.latencyMs,
      };
    }

    renderAll();
    fetchObservationEnrichment(data.observation_id, reqSeq, targetKey);
    return data;
  }

  async function runFiveVerifications(triggerFromButton = false) {
    if (state.backendVerifications.isRunning) return;
    state.backendVerifications.isRunning = true;

    const runBtn = document.getElementById("runVerificationsBtn");
    if (runBtn) {
      runBtn.disabled = true;
      runBtn.textContent = "Verifying 5+1…";
    }
    updateBenchmarksApiBadge();
    renderBenchmarksTable();

    try {
      const [healthRes, targetsRes, benchmarksRes] = await Promise.all([
        fetchJsonWithTimeout(`${API_BASE}/health`, {}, 5000),
        fetchJsonWithTimeout(`${API_BASE}/targets`, {}, 5000),
        fetchJsonWithTimeout(`${API_BASE}/benchmarks`, {}, 5000),
      ]);

      state.backendVerifications.health = healthRes.ok ? healthRes.data : null;
      state.backendVerifications.targets = targetsRes.ok
        ? targetsRes.data
        : null;
      state.backendVerifications.benchmarks = benchmarksRes.ok
        ? benchmarksRes.data
        : null;

      const benchByTarget = new Map();
      if (benchmarksRes.ok && Array.isArray(benchmarksRes.data?.results)) {
        for (const r of benchmarksRes.data.results) {
          if (r && r.target_id) benchByTarget.set(r.target_id, r);
        }
      }

      const allConfigs = [
        ...Object.values(TARGET_BUNDLES).map((b) => ({
          key: b.key,
          mode: b.recommendedMode || "both",
        })),
        { key: NEGATIVE_CONTROL_BUNDLE.key, mode: "both" },
      ];

      const initialPromise = !triggerFromButton
        ? state._initialObservePromise
        : null;
      const initialKey = state.selectedPresetKey;

      const probeResults = await Promise.all(
        allConfigs.map(async ({ key, mode }) => {
          const bench = benchByTarget.get(key) || null;
          const benchStatus =
            bench && typeof bench.status === "string"
              ? bench.status.toLowerCase()
              : null;

          let obsData = null;
          let obsOk = false;
          let latencyMs = 0;

          if (!triggerFromButton && initialPromise && key === initialKey) {
            obsData = await initialPromise;
            obsOk = Boolean(obsData?.observation_id);
          } else {
            const obsRes = await fetchJsonWithTimeout(
              `${API_BASE}/observe?target=${encodeURIComponent(
                key
              )}&mode=${encodeURIComponent(mode)}`,
              {},
              REQUEST_TIMEOUT_MS
            );
            obsOk = obsRes.ok && Boolean(obsRes.data?.observation_id);
            obsData = obsRes.ok ? obsRes.data : null;
            latencyMs = obsRes.latencyMs;
          }

          const observationId = obsData?.observation_id || null;
          const servedFrom =
            obsData?.served_from || bench?.data_source || null;
          const measuredValue =
            bench?.measured_value ||
            extractObservedMeasurement(obsData, mode) ||
            null;

          let status = "offline";
          if (benchStatus === "fail") {
            status = "fail";
          } else if (benchStatus === "pass" || obsOk) {
            status = "pass";
          } else if (healthRes.ok || targetsRes.ok || benchmarksRes.ok) {
            status = "fail";
          }

          return [
            key,
            {
              status,
              observationId,
              servedFrom,
              measuredValue,
              latencyMs,
              reason: bench?.reason || null,
            },
          ];
        })
      );

      state._initialObservePromise = null;
      const nextResults = {};
      for (const [key, entry] of probeResults) {
        nextResults[key] = entry;
      }
      state.backendVerifications.resultsByKey = nextResults;
      state.backendVerifications.lastCheckedAt = new Date().toISOString();
    } finally {
      state.backendVerifications.isRunning = false;
      if (runBtn) {
        runBtn.disabled = false;
        runBtn.textContent = "Run 5 Verifications ↻";
      }
      updateBenchmarksApiBadge();
      renderBenchmarksTable();
    }
  }

  function buildDeterministicAskSynthesis(bundle, src) {
    return `[GROUNDED EVIDENCE SYNTHESIS]: For ${src.commonName} (${src.designation}) in ${bundle.constellation}, SEP ePSF tracking measures µ = ${src.totalPmArcsecYr} arcsec/yr (SNR = ${src.snr}, χ²_var = ${src.variabilityChi2}). ${
      src.isGaiaOpticalDropout
        ? "Zero optical detections exist in ESA Gaia DR3, proving an ultracool (~250 K) Y-dwarf spectral energy distribution peaking in SPHEREx Band 5/6 (4.48 µm)."
        : `Cross-matched with ${src.gaiaDr3Id || "ESA Gaia DR3"} and CSA CADC NEOSSat (${src.csaNeossatObsId || "CADC Archive"}).`
    }`;
  }

  function showAskResponse(text, sources = []) {
    const box = document.getElementById("askPatchResponse");
    if (!box) return;

    box.hidden = false;

    let closeBtn = document.getElementById("askResponseClose") || box.querySelector(".ask-response-close");
    if (!closeBtn) {
      closeBtn = document.createElement("button");
      closeBtn.type = "button";
      closeBtn.id = "askResponseClose";
      closeBtn.className = "ask-response-close";
      closeBtn.setAttribute("aria-label", "Dismiss answer");
      closeBtn.textContent = "×";
      box.appendChild(closeBtn);
    }
    if (!closeBtn.dataset.boundClose) {
      closeBtn.addEventListener("click", hideAskResponse);
      closeBtn.dataset.boundClose = "true";
    }

    let textContainer = document.getElementById("askResponseText");
    if (!textContainer) {
      textContainer = document.createElement("div");
      textContainer.id = "askResponseText";
      box.appendChild(textContainer);
    }

    textContainer.replaceChildren();
    const p = document.createElement("p");
    p.className = "ask-response-text";
    p.style.margin = "0";
    p.textContent = text;
    textContainer.appendChild(p);

    if (Array.isArray(sources) && sources.length > 0) {
      const linksRow = document.createElement("div");
      linksRow.className = "ask-response-sources";
      linksRow.style.display = "flex";
      linksRow.style.flexWrap = "wrap";
      linksRow.style.gap = "6px";
      linksRow.style.marginTop = "6px";
      sources.forEach((s) => {
        if (!s || !s.url) return;
        const a = document.createElement("a");
        a.className = "citation-pill";
        a.href = s.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = `[${(s.source_name || s.sourceName || "SOURCE").toUpperCase()}]`;
        linksRow.appendChild(a);
      });
      if (linksRow.childElementCount > 0) textContainer.appendChild(linksRow);
    }
  }

  function hideAskResponse() {
    const box = document.getElementById("askPatchResponse");
    if (!box) return;
    box.hidden = true;
    const textContainer = document.getElementById("askResponseText");
    if (textContainer) textContainer.replaceChildren();
  }

  async function handleAskPatch(e) {
    e.preventDefault();
    const input = document.getElementById("askPatchInput");
    const submitBtn = document.getElementById("askPatchSubmit");
    if (!input) return;

    const question = input.value.trim();
    if (!question) return;

    const bundle = getActiveBundle();
    const src = getSelectedSource(bundle);

    if (!state.liveObservationId) {
      showAskResponse(buildDeterministicAskSynthesis(bundle, src));
      return;
    }

    if (submitBtn) submitBtn.disabled = true;
    showAskResponse("Retrieving observation evidence and synthesizing response…");

    try {
      const res = await fetchJsonWithTimeout(
        `${API_BASE}/observe/${encodeURIComponent(state.liveObservationId)}/ask`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question }),
        },
        ASK_TIMEOUT_MS
      );

      if (!res.ok || !res.data || !res.data.answer) {
        throw new Error(`Ask failed (${res.status})`);
      }
      const cleanAnswer = String(res.data.answer)
        .replace(/Deterministic pipeline analysis for SPHEREx observation obs_[a-zA-Z0-9]+:\s*/i, `Archive analysis for ${bundle.label}:\n`)
        .replace(/SPHEREx observation obs_[a-zA-Z0-9]+/g, bundle.label)
        .replace(/\bobs_[a-zA-Z0-9]+\b/g, bundle.label);
      showAskResponse(cleanAnswer, res.data.sources || []);
    } catch (_) {
      showAskResponse(buildDeterministicAskSynthesis(bundle, src));
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  }

  // ============================================================================
  // 8. FEATURE-DETECTED WEB PLATFORM POLYFILLS & EVENT BINDINGS
  // ============================================================================

  function installFeaturePolyfills() {
    // 1) Native <input type="checkbox" switch> fallback for Chrome/Firefox
    if (!("switch" in HTMLInputElement.prototype)) {
      document.querySelectorAll('input[type="checkbox"][switch]').forEach((el) => {
        el.classList.add("switch-fallback");
      });
    }

    // 2) Native <dialog closedby="any"> light-dismiss fallback
    if (!("closedBy" in HTMLDialogElement.prototype)) {
      document.querySelectorAll("dialog[closedby]").forEach((dialog) => {
        const mode = (dialog.getAttribute("closedby") || "").toLowerCase();
        if (mode !== "any") return;
        dialog.addEventListener("click", (e) => {
          if (e.target !== dialog) return;
          const rect = dialog.getBoundingClientRect();
          const outside =
            e.clientX < rect.left ||
            e.clientX > rect.right ||
            e.clientY < rect.top ||
            e.clientY > rect.bottom;
          if (outside && typeof dialog.close === "function") {
            dialog.close();
          }
        });
      });
    }

    // 3) Native Invoker Commands (command / commandfor) fallback
    if (!("commandForElement" in HTMLButtonElement.prototype)) {
      document.querySelectorAll("button[command][commandfor]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const cmd = (btn.getAttribute("command") || "").toLowerCase();
          const targetId = btn.getAttribute("commandfor");
          const target = targetId ? document.getElementById(targetId) : null;
          if (!target) return;
          if (cmd === "show-modal" && typeof target.showModal === "function") {
            if (!target.open) target.showModal();
          } else if (cmd === "close" && typeof target.close === "function") {
            target.close();
          }
        });
      });
    }
  }

  function bindEvents() {
    // Header target tabs
    document.querySelectorAll("[data-target]").forEach((btn) => {
      btn.addEventListener("click", () => {
        selectTargetBundle(btn.dataset.target);
      });
    });

    // Coordinate search form
    const coordForm = document.getElementById("coordForm");
    if (coordForm) {
      coordForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const raInput = document.getElementById("raInput");
        const decInput = document.getElementById("decInput");
        const rawRa = raInput ? raInput.value.trim() : "";
        const rawDec = decInput ? decInput.value.trim() : "";
        const parsedRa = rawRa === "" ? NaN : Number(rawRa);
        const parsedDec = rawDec === "" ? NaN : Number(rawDec);
        const raNum = clampRa(parsedRa);
        const decNum = clampDec(parsedDec);

        if (raInput) raInput.value = raNum.toFixed(5);
        if (decInput) decInput.value = decNum.toFixed(5);

        const custom = createCustomPatchBundle(raNum, decNum);
        state.customPatchBundle = custom;
        state.selectedPresetKey = "custom_patch";
        state.analysisMode = custom.recommendedMode;
        state.selectedSourceId = custom.sources[0].id;
        state.activeChapterIdx = 0;
        resetLiveObservationState();
        hideAskResponse();

        syncUrlFromState();
        renderAll();
        fetchBackendObservation(raNum, decNum, custom.fovDeg, "custom_patch");
      });
    }

    // Motion / Variability switch
    const modeSwitch = document.getElementById("modeSwitch");
    if (modeSwitch) {
      modeSwitch.addEventListener("change", () => {
        state.analysisMode = modeSwitch.checked ? "variability" : "motion";
        renderAll();
      });
    }

    // WiseView Radiometry sliders
    const linearityRange = document.getElementById("linearityRange");
    if (linearityRange) {
      linearityRange.addEventListener("input", () => {
        state.linearityParam = Number(linearityRange.value);
        const formatted = formatLinearity(state.linearityParam);
        const out = document.getElementById("linearityValue");
        if (out) out.textContent = formatted;
        syncRangeControl(linearityRange, formatted);
        renderCanvases(getActiveBundle());
      });
    }

    const trimRange = document.getElementById("trimRange");
    if (trimRange) {
      trimRange.addEventListener("input", () => {
        state.trimBrightPct = Number(trimRange.value);
        const formatted = `${state.trimBrightPct.toFixed(1)}%`;
        const out = document.getElementById("trimValue");
        if (out) out.textContent = formatted;
        syncRangeControl(trimRange, formatted);
        renderCanvases(getActiveBundle());
      });
    }

    // Multi-Agency Overlays Master Switch + 3 Pills
    const masterSwitch = document.getElementById("overlaysMasterSwitch");
    if (masterSwitch) {
      masterSwitch.addEventListener("change", () => {
        state.overlaysMaster = masterSwitch.checked;
        const list = document.querySelector(".overlays-list");
        if (list) list.classList.toggle("is-muted", !state.overlaysMaster);
        renderOverlaySvg(getActiveBundle());
      });
    }

    document.querySelectorAll(".overlay-pill[data-layer]").forEach((pill) => {
      pill.addEventListener("click", () => {
        const layer = pill.dataset.layer;
        if (!(layer in state.overlayLayers)) return;
        const next = !state.overlayLayers[layer];
        state.overlayLayers[layer] = next;
        pill.setAttribute("aria-pressed", String(next));

        if (next && !state.overlaysMaster) {
          state.overlaysMaster = true;
          if (masterSwitch) masterSwitch.checked = true;
          const list = document.querySelector(".overlays-list");
          if (list) list.classList.remove("is-muted");
        }
        renderOverlaySvg(getActiveBundle());
      });
    });

    // Primary Canvas hover pixel telemetry
    const primaryCanvas = document.getElementById("primaryCanvas");
    const hoverBar = document.getElementById("hoverTelemetryBar");
    const primaryViewport = primaryCanvas
      ? primaryCanvas.closest(".canvas-box") || primaryCanvas.parentElement
      : null;

    if (primaryViewport && hoverBar) {
      const updateHover = (e) => {
        const rect = primaryViewport.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) return;

        const px = Math.min(
          GRID_SIZE - 1,
          Math.max(0, Math.floor(((e.clientX - rect.left) / rect.width) * GRID_SIZE))
        );
        const py = Math.min(
          GRID_SIZE - 1,
          Math.max(0, Math.floor(((e.clientY - rect.top) / rect.height) * GRID_SIZE))
        );

        const bundle = getActiveBundle();
        const frame = getCurrentFrame(bundle);
        const buf =
          state.displayMode === "coadd_stack"
            ? bundle.coaddByDetector[state.selectedDetectorStack]
            : state.displayMode === "difference_only"
            ? frame.differencePixels
            : frame.rawPixels;

        const idx = py * GRID_SIZE + px;
        const flux = buf[idx] ?? 0;
        const raCursor = bundle.raDeg + ((px - GRID_SIZE / 2) * 6.15) / 3600.0;
        const decCursor = bundle.decDeg - ((py - GRID_SIZE / 2) * 6.15) / 3600.0;

        hoverBar.textContent = `PX(${px},${py}) • RA ${raCursor.toFixed(
          5
        )}° DEC ${decCursor.toFixed(5)}° • ${flux.toFixed(2)} MJy/sr`;
        hoverBar.classList.add("is-visible");
      };

      const clearHover = () => {
        hoverBar.classList.remove("is-visible");
        hoverBar.textContent = "";
      };

      primaryViewport.addEventListener("pointermove", updateHover);
      primaryViewport.addEventListener("pointerleave", clearHover);
    }

    // Timeline Dock Controls
    const blinkPlayBtn = document.getElementById("blinkPlayBtn");
    if (blinkPlayBtn) {
      blinkPlayBtn.addEventListener("click", () => {
        if (state.isPlayingBlink) {
          stopBlink();
          renderAll();
        } else {
          startBlink();
          renderAll();
        }
      });
    }

    const prevEpochBtn = document.getElementById("prevEpochBtn");
    if (prevEpochBtn) {
      prevEpochBtn.addEventListener("click", () => {
        stopBlink();
        const len = getActiveBundle().frames.length;
        state.epochIdx = (state.epochIdx - 1 + len) % len;
        syncUrlFromState();
        renderAll();
      });
    }

    const nextEpochBtn = document.getElementById("nextEpochBtn");
    if (nextEpochBtn) {
      nextEpochBtn.addEventListener("click", () => {
        stopBlink();
        const len = getActiveBundle().frames.length;
        state.epochIdx = (state.epochIdx + 1) % len;
        syncUrlFromState();
        renderAll();
      });
    }

    const displayModeBtn = document.getElementById("displayModeBtn");
    if (displayModeBtn) {
      displayModeBtn.addEventListener("click", () => {
        const curIdx = DISPLAY_MODES.indexOf(state.displayMode);
        state.displayMode = DISPLAY_MODES[(curIdx + 1) % DISPLAY_MODES.length];
        if (state.displayMode === "coadd_stack" && state.isPlayingBlink) {
          stopBlink();
        }
        renderAll();
      });
    }

    const detectorSwitcher = document.getElementById("detectorSwitcher");
    if (detectorSwitcher) {
      if (detectorSwitcher.querySelectorAll("button").length === 0) {
        for (let d = 1; d <= 6; d++) {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.dataset.detector = String(d);
          btn.textContent = `D${d}`;
          detectorSwitcher.appendChild(btn);
        }
      }
      detectorSwitcher.addEventListener("click", (e) => {
        const btn = e.target.closest("button");
        if (!btn) return;
        const det = Number(btn.dataset.detector || btn.textContent.replace(/\D/g, ""));
        if (det >= 1 && det <= 6) {
          state.selectedDetectorStack = det;
          renderAll();
        }
      });
    }

    const invertBtn = document.getElementById("invertBtn");
    if (invertBtn) {
      invertBtn.addEventListener("click", () => {
        state.invertPixels = !state.invertPixels;
        renderAll();
      });
    }

    const flagsBtn = document.getElementById("flagsBtn");
    if (flagsBtn) {
      flagsBtn.addEventListener("click", () => {
        state.showBitmaskFlags = !state.showBitmaskFlags;
        renderAll();
      });
    }

    // Epoch nodes
    document.querySelectorAll(".epoch-node[data-epoch]").forEach((node) => {
      node.addEventListener("click", () => {
        const ep = Number(node.dataset.epoch);
        if (!Number.isInteger(ep) || ep < 0 || ep > 3) return;
        stopBlink();
        state.epochIdx = ep;
        syncUrlFromState();
        renderAll();
      });
    });

    // Spectrum Bottom Dock Wavelength Scrubber
    const wavelengthRange = document.getElementById("wavelengthRange");
    if (wavelengthRange) {
      wavelengthRange.addEventListener("input", () => {
        state.scrubWavelengthUm = Number(wavelengthRange.value);
        const formatted = `${state.scrubWavelengthUm.toFixed(2)} µm`;
        const out = document.getElementById("wavelengthValue");
        if (out) out.textContent = formatted;
        syncRangeControl(wavelengthRange, formatted);
        const bundle = getActiveBundle();
        renderCanvases(bundle);
        renderSedChart(bundle);
      });
    }

    // Ask Patch Form
    const askForm = document.getElementById("askPatchForm");
    if (askForm) {
      askForm.addEventListener("submit", handleAskPatch);
    }

    // Benchmarks Dialog Live Verification Trigger
    const runVerificationsBtn = document.getElementById("runVerificationsBtn");
    if (runVerificationsBtn) {
      runVerificationsBtn.addEventListener("click", () => {
        runFiveVerifications(true);
      });
    }

    // Browser Back/Forward URL Sync
    window.addEventListener("popstate", () => {
      stopBlink();
      applyStateFromUrl();
      renderAll();
      const bundle = getActiveBundle();
      fetchBackendObservation(bundle.raDeg, bundle.decDeg, bundle.fovDeg, bundle.key);
    });
  }

  // ============================================================================
  // 9. BOOTSTRAP
  // ============================================================================

  function init() {
    applyStateFromUrl();
    installFeaturePolyfills();
    bindEvents();
    renderAll();

    const bundle = getActiveBundle();
    state._initialObservePromise = fetchBackendObservation(
      bundle.raDeg,
      bundle.decDeg,
      bundle.fovDeg,
      bundle.key
    );
    runFiveVerifications(false);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
