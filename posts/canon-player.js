const VOICE_COLORS = ["#f3a712", "#45a6e5", "#ef6351", "#49c889", "#a978d4", "#f4f0df"];
let activePlayer = null;

function initStarfield() {
  const canvas = document.createElement("canvas");
  canvas.className = "canon-starfield";
  canvas.setAttribute("aria-hidden", "true");
  document.body.prepend(canvas);
  const ctx = canvas.getContext("2d");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let width = 0;
  let height = 0;
  let stars = [];
  let frame = 0;

  const random = index => {
    const value = Math.sin(index * 127.1 + 311.7) * 43758.5453;
    return value - Math.floor(value);
  };

  const draw = () => {
    frame = 0;
    ctx.clearRect(0, 0, width, height);
    const scroll = reducedMotion.matches ? 0 : window.scrollY;
    for (const star of stars) {
      const y = ((star.y - scroll * star.speed) % height + height) % height;
      ctx.globalAlpha = star.alpha;
      ctx.fillStyle = star.color;
      ctx.beginPath();
      ctx.arc(star.x, y, star.radius, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  };

  const resize = () => {
    width = window.innerWidth;
    height = window.innerHeight;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.floor(width * ratio);
    canvas.height = Math.floor(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    const count = Math.max(48, Math.min(140, Math.round(width * height / 9000)));
    const colors = ["#f4f0df", "#b8d9ef", "#f3cf83"];
    stars = Array.from({ length: count }, (_, index) => ({
      x: random(index * 5 + 1) * width,
      y: random(index * 5 + 2) * height,
      radius: .35 + random(index * 5 + 3) * .75,
      alpha: .13 + random(index * 5 + 4) * .32,
      speed: .035 + random(index * 5 + 5) * .05,
      color: colors[index % colors.length]
    }));
    draw();
  };

  const requestDraw = () => {
    if (!frame) frame = requestAnimationFrame(draw);
  };
  window.addEventListener("scroll", requestDraw, { passive: true });
  window.addEventListener("resize", resize);
  reducedMotion.addEventListener("change", requestDraw);
  resize();
}

initStarfield();

const audio = {
  context: null,
  ensure() {
    if (!this.context) this.context = new (window.AudioContext || window.webkitAudioContext)();
    return this.context.resume().then(() => this.context);
  }
};

class CanonPlayer {
  constructor(element, score) {
    this.element = element;
    this.baseScore = score;
    this.variantIndex = 0;
    this.canvas = element.querySelector("canvas");
    this.context2d = this.canvas.getContext("2d");
    this.button = element.querySelector(".play-button");
    this.range = element.querySelector("input[type=range]");
    this.timeLabel = element.querySelector(".player-time");
    this.bpmLabel = element.querySelector(".player-bpm");
    this.voiceControl = element.querySelector(".voice-control");
    this.variationControl = element.querySelector(".variation-control");
    this.position = 0;
    this.playing = false;
    this.startedAt = 0;
    this.nodes = [];
    this.configureScore();
    this.bind();
    this.buildVariationControl();
    this.buildVoiceControl();
    this.resize();
  }

  configureScore() {
    const variant = this.baseScore.variations?.[this.variantIndex];
    this.score = variant
      ? { ...this.baseScore, ...variant, visual: this.baseScore.visual }
      : this.baseScore;
    this.displayBeats = this.score.visual.display_beats || this.score.beats;
    this.displayOffset = this.score.visual.display_offset || 0;
    this.rowBeats = this.score.visual.row_beats || null;
    this.pickup = this.score.visual.pickup || 0;
    this.swing = this.score.visual.swing || 0.5;
    this.meter = variant?.meter || this.score.visual.meter || 4;
    this.wrapBeats = variant
      ? this.meter * 8
      : this.score.visual.wrap || (this.displayBeats > 40 ? 12 : 8);
    this.performance = this.score.visual.performance || null;
    this.playbackBpm = this.performance ? this.performance.bpm : this.score.bpm;
    this.totalBeats = this.performance
      ? this.scoreBeat(this.performanceBeat(this.performance.duration)) + this.performance.offset_beats
      : this.score.beats;
    this.performanceAudio = this.performance ? this.performance.stems.map(stem => {
      const element = new Audio(stem.src);
      element.preload = "auto";
      return { ...stem, element };
    }) : [];
    const groundMap = variant ? {
      scale: 1,
      offset: -variant.bass_offset,
      modulo: this.meter * 8,
      start: variant.bass_offset,
    } : null;
    this.lines = this.score.visual.lines.map((line, lineIndex) => {
      const configured = { ...line, map: line.map ? { ...line.map } : undefined };
      if (variant?.line_maps?.[lineIndex]) configured.map = { ...variant.line_maps[lineIndex] };
      if (variant?.line_transforms?.[lineIndex]) configured.transform = variant.line_transforms[lineIndex];
      if (variant?.line_directions?.[lineIndex]) configured.direction = variant.line_directions[lineIndex];
      if (configured.ground_bass && groundMap) configured.map = { ...groundMap };
      return configured;
    });
    this.sources = this.score.visual.sources.map((sourceDefinition, sourceIndex) => {
      const source = { ...sourceDefinition, map: sourceDefinition.map ? { ...sourceDefinition.map } : undefined };
      if (variant?.source_beats?.[sourceIndex]) source.beats = variant.source_beats[sourceIndex];
      if (variant?.source_maps?.[sourceIndex]) source.map = { ...variant.source_maps[sourceIndex] };
      if (source.ground_bass && groundMap) {
        source.map = { ...groundMap };
        source.beats = this.meter * 8;
        source.notes = source.notes.map(note => ({
          ...note,
          t: note.t * this.meter / 4,
          d: note.d * this.meter / 4,
        }));
      }
      let notes = this.extractSourceNotes(source);
      if (source.repeat_head) {
        const heads = this.score.staffs[source.track]
          .filter(note => note.v === 0 && Math.abs(note.t - source.repeat_head.at) < .0001)
          .map(note => ({ ...note, t: 0, p: note.p + source.repeat_head.semitones, y: note.y + source.repeat_head.y }));
        notes = [...heads, ...notes];
      }
      if (source.split_bars) notes = this.splitAtBars(notes, source.split_bars);
      const eventCount = Math.max(...notes.map(note => note.i)) + 1;
      return { ...source, notes, eventCount };
    });
    this.prepareInversions();
    this.muted = this.lines.map(() => false);
    this.position = 0;
    this.range.value = 0;
    this.range.max = this.totalBeats;
    const kind = this.performance ? "uitvoering" : "fragment";
    const variationLabel = variant ? " · " + variant.short + " · " + variant.label : "";
    this.bpmLabel.textContent = this.playbackBpm + " bpm · " + this.lines.length + " muzikale lijnen · " + kind + variationLabel;
  }

  buildVariationControl() {
    const variants = this.baseScore.variations;
    if (!variants?.length) {
      this.variationControl.hidden = true;
      return;
    }
    this.variationControl.hidden = false;
    const tabs = variants.map((variant, index) =>
      '<button type="button" role="tab" data-variant="' + index + '" aria-selected="' + (index === this.variantIndex) + '" title="' + variant.label + '">' + variant.short + '</button>'
    ).join("");
    this.variationControl.innerHTML = '<button class="variation-step" type="button" data-step="-1" title="Vorig interval" aria-label="Vorig interval">←</button>'
      + '<div class="variation-tabs" role="tablist" aria-label="Canoninterval">' + tabs + '</div>'
      + '<button class="variation-step" type="button" data-step="1" title="Volgend interval" aria-label="Volgend interval">→</button>'
      + '<strong class="variation-name">' + variants[this.variantIndex].label + '</strong>';
    this.variationControl.querySelectorAll("[data-variant]").forEach(button => {
      button.addEventListener("click", () => this.setVariant(Number(button.dataset.variant)));
    });
    this.variationControl.querySelectorAll("[data-step]").forEach(button => {
      button.addEventListener("click", () => this.setVariant(this.variantIndex + Number(button.dataset.step)));
    });
  }

  setVariant(index) {
    const variants = this.baseScore.variations;
    const next = (index + variants.length) % variants.length;
    if (next === this.variantIndex) return;
    this.stop();
    this.variantIndex = next;
    this.configureScore();
    this.buildVariationControl();
    this.buildVoiceControl();
    this.resize();
    this.updateTime();
  }

  splitAtBars(notes, barBeats) {
    return notes.flatMap(note => {
      const pieces = [];
      const end = note.t + note.d;
      let start = note.t;
      while (start < end - 0.0001) {
        const nextBoundary = (Math.floor(start / barBeats) + 1) * barBeats;
        const pieceEnd = Math.min(end, nextBoundary);
        pieces.push({ ...note, t: start, d: Math.round((pieceEnd - start) * 10000) / 10000 });
        start = pieceEnd;
      }
      return pieces;
    });
  }

  uniqueChords(notes) {
    const seen = new Set();
    return notes.filter(note => {
      const key = note.i + ":" + note.t;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  extractSourceNotes(source) {
    if (source.notes) return source.notes.map(note => ({ ...note }));
    const sourceStart = source.start || 0;
    const sourceBeats = source.beats || this.displayBeats;
    let staff = this.score.staffs[source.track].filter(note => note.v === 0);
    if (!staff.length) staff = this.score.staffs[source.track];
    if (!source.sections) {
      return this.uniqueChords(staff
        .filter(note => sourceStart <= note.t && note.t < sourceStart + sourceBeats)
        .map(note => ({ ...note, t: note.t - sourceStart, d: Math.min(note.d, sourceStart + sourceBeats - note.t) })));
    }
    let cursor = 0;
    const notes = [];
    for (const section of source.sections) {
      for (const note of staff) {
        const start = Math.max(note.t, section.start);
        const end = Math.min(note.t + note.d, section.end);
        if (end <= start) continue;
        notes.push({ ...note, t: cursor + start - section.start, d: end - start });
      }
      cursor += section.end - section.start;
    }
    return this.uniqueChords(notes);
  }

  prepareInversions() {
    this.sources.forEach((source, sourceIndex) => {
      if (source.role === "bass") return;
      const lineIndexes = this.lines
        .map((line, index) => line.source === sourceIndex && this.lineUsesInversion(line) ? index : -1)
        .filter(index => index >= 0);
      if (!lineIndexes.length) return;
      const pitches = source.notes.map(note => note.y);
      const axis = (Math.min(...pitches) + Math.max(...pitches)) / 2;
      source.inversion = { axis, lineIndexes };
    });
  }

  bind() {
    this.button.addEventListener("click", () => this.playing ? this.stop() : this.play());
    this.range.max = this.totalBeats;
    this.range.addEventListener("input", () => {
      const resume = this.playing;
      this.stop(false);
      this.position = Number(this.range.value);
      this.draw();
      this.updateTime();
      if (resume) this.play();
    });
    new ResizeObserver(() => this.resize()).observe(this.element);
  }

  buildVoiceControl() {
    this.voiceControl.innerHTML = this.lines.map((line, index) =>
      `<button type="button" class="voice-swatch" style="--voice:${VOICE_COLORS[index % VOICE_COLORS.length]}" aria-pressed="true" title="Lijn ${line.label}${line.transform === "inversion" ? " (inversie)" : line.transform === "retrograde" ? " (retrograde)" : ""} aan- of uitzetten">${line.label}</button>`
    ).join("");
    [...this.voiceControl.children].forEach((button, index) => button.addEventListener("click", () => {
      const resume = this.playing;
      this.muted[index] = !this.muted[index];
      button.setAttribute("aria-pressed", String(!this.muted[index]));
      button.classList.toggle("muted", this.muted[index]);
      if (resume && this.performance) {
        this.syncPerformanceMute();
      } else if (resume) {
        this.stop(false);
        this.play();
      } else {
        this.draw();
      }
    }));
  }

  layoutSources(width) {
    let cursor = 12;
    this.sources.forEach(source => {
      const bass = source.role === "bass";
      const sourceBeats = source.beats || this.displayBeats;
      const wrap = source.wrap || (bass ? sourceBeats : this.wrapBeats);
      const rowBeats = !bass && this.rowBeats ? this.rowBeats : null;
      const rows = rowBeats ? rowBeats.length : Math.ceil(sourceBeats / wrap);
      const voicePitchArea = bass ? 22 : 54;
      const mirrorGap = source.inversion ? 14 : 0;
      const mirrorOffset = source.inversion ? voicePitchArea + 14 + mirrorGap : 0;
      const rowHeight = bass ? 42 : source.inversion ? 164 : 82;
      const pitchArea = bass ? 22 : source.inversion ? 136 : 54;
      source.geometry = { bass, wrap, sourceBeats, rowBeats, rows, rowHeight, pitchArea, voicePitchArea, mirrorGap, mirrorOffset, labelY: cursor + 10, top: cursor + 28, height: 28 + rows * rowHeight };
      cursor += source.geometry.height + 8;
    });
    return cursor + 4;
  }

  resize() {
    const width = this.element.clientWidth;
    const cssHeight = this.layoutSources(width);
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = Math.floor(width * ratio);
    this.canvas.height = Math.floor(cssHeight * ratio);
    this.canvas.style.height = cssHeight + "px";
    this.context2d.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.width = width;
    this.height = cssHeight;
    this.draw();
  }

  rowAt(beat, geometry) {
    if (!geometry.rowBeats) {
      const row = Math.min(geometry.rows - 1, Math.floor(beat / geometry.wrap));
      return { row, start: row * geometry.wrap, beats: geometry.wrap };
    }
    let start = 0;
    for (let row = 0; row < geometry.rowBeats.length; row++) {
      const beats = geometry.rowBeats[row];
      if (beat < start + beats || row === geometry.rowBeats.length - 1) return { row, start, beats };
      start += beats;
    }
  }

  noteBoxes(note, sourceIndex, inverted = false) {
    const source = this.sources[sourceIndex];
    const geometry = source.geometry;
    const padX = 18;
    const usable = this.width - padX * 2;
    const offsets = [0];
    if (source.modulation) offsets.push(...source.modulation.layers.map(layer => layer.y));
    for (const line of this.lines.filter(line => line.source === sourceIndex && line.modulation)) {
      offsets.push(...line.modulation.layers.map(layer => layer.y));
      if (line.shepard) offsets.push(-line.shepard.octave_y, line.shepard.octave_y);
    }
    const pitches = source.notes.flatMap(item => offsets.map(offset => item.y + offset));
    const low = Math.min(...pitches) - 1;
    const high = Math.max(...pitches) + 1;
    const pitchHeight = geometry.voicePitchArea / Math.max(7, high - low);
    const boxes = [];
    const noteEnd = note.t + note.d;
    let segmentStart = note.t;
    while (segmentStart < noteEnd - 0.0001) {
      const position = this.rowAt(segmentStart, geometry);
      const segmentEnd = Math.min(noteEnd, position.start + position.beats);
      const rowTop = geometry.top + position.row * geometry.rowHeight;
      const laneTop = rowTop + (inverted ? geometry.mirrorOffset : 0);
      boxes.push({
        x: padX + (segmentStart - position.start) / position.beats * usable,
        y: laneTop + geometry.voicePitchArea + 9 - (note.y - low) * pitchHeight,
        width: Math.max(2, (segmentEnd - segmentStart) / position.beats * usable - 1),
        height: Math.max(geometry.bass ? 2 : 4, pitchHeight * .72),
        row: position.row
      });
      segmentStart = segmentEnd;
    }
    return boxes;
  }

  invertedPitch(pitch, source) {
    return source.inversion.axis * 2 - pitch;
  }

  invertedNote(note, sourceIndex) {
    const source = this.sources[sourceIndex];
    return { ...note, y: this.invertedPitch(note.y, source) };
  }

  activeOrdinal(tracks, beat) {
    for (const track of tracks) {
      const sounding = this.score.staffs[track].find(note => note.t <= beat && note.t + note.d > beat);
      if (sounding) return sounding.i;
    }
    return null;
  }

  activeSourceNote(line, beat) {
    if (this.performance?.music_beats != null && beat >= this.performance.music_beats) return null;
    const scoreBeat = this.performance ? beat % this.score.beats : beat;
    const ordinal = this.activeOrdinal(line.tracks, scoreBeat);
    const source = this.sources[line.source];
    if (line.traversal) {
      const targetBar = Math.floor(beat / this.meter);
      const sourceBar = line.traversal.bars[targetBar];
      if (sourceBar === undefined) return null;
      const withinBar = beat - targetBar * this.meter;
      const sourceWithin = line.traversal.reverse ? this.meter - withinBar - 0.0001 : withinBar;
      const sourceTime = sourceBar * this.meter + sourceWithin;
      return source.notes.find(note => note.t <= sourceTime && note.t + note.d > sourceTime) || null;
    }
    if (line.map) {
      if (beat < this.score.beats && ordinal === null) return null;
      const sourceTime = this.mappedSourceTime(line.map, beat);
      if (sourceTime === null) return null;
      return source.notes.find(note => note.t <= sourceTime && note.t + note.d > sourceTime) || null;
    }
    if (ordinal === null) return null;
    const sourceOrdinal = ordinal % source.eventCount;
    return source.notes.find(note => note.i === sourceOrdinal) || null;
  }

  mappedSegment(map, beat) {
    return map?.segments?.find(item => item.start <= beat && beat < item.end) || null;
  }

  lineUsesInversion(line) {
    return line.transform === "inversion"
      || Boolean(line.map?.segments?.some(segment => segment.transform === "inversion"));
  }

  lineInvertedAt(line, beat) {
    const base = line.transform === "inversion";
    const segment = this.mappedSegment(line.map, beat);
    return segment?.transform === "inversion" ? !base : base;
  }

  mappedSourceTime(map, beat) {
    if (map.start != null && beat < map.start) return null;
    if (map.end != null && beat >= map.end) return null;
    if (map.segments) {
      const segment = map.segments.find(item => item.start <= beat && beat < item.end);
      if (!segment) return null;
      return segment.source + (beat - segment.start) * (segment.scale || 1);
    }
    let sourceTime = beat * map.scale + map.offset;
    if (map.modulo) sourceTime = ((sourceTime % map.modulo) + map.modulo) % map.modulo;
    return sourceTime;
  }

  modulationLayer(line, beat) {
    const source = this.sources[line.source];
    const modulation = line.modulation || source.modulation;
    if (!modulation || !line.map || line.map.segments) return null;
    const unwrapped = beat * line.map.scale + line.map.offset;
    if (unwrapped < 0) return null;
    const cycle = Math.floor(unwrapped / modulation.period);
    return modulation.layers[cycle % modulation.layers.length];
  }

  displayNote(note, line, beat) {
    const transformed = this.lineInvertedAt(line, beat)
      ? this.invertedNote(note, line.source)
      : note;
    const layer = this.modulationLayer(line, beat);
    return layer ? { ...transformed, y: transformed.y + layer.y } : transformed;
  }

  shepardGenerationY(line, generation) {
    const modulation = line.modulation;
    const shepard = line.shepard;
    const cycles = shepard.cycles || modulation.layers.length;
    const positionAt = index => {
      const octave = Math.floor(index / cycles);
      const layerIndex = ((index % cycles) + cycles) % cycles;
      return octave * shepard.direction * shepard.octave_y + modulation.layers[layerIndex].y;
    };
    const start = Math.floor(generation);
    const phase = generation - start;
    const from = positionAt(start);
    return from + (positionAt(start + 1) - from) * phase;
  }

  shepardCopies(line, beat) {
    const modulation = line.modulation;
    const shepard = line.shepard;
    if (!modulation || !shepard || !line.map) return [];
    const unwrapped = beat * line.map.scale + line.map.offset;
    if (unwrapped < 0) return [];
    const progress = unwrapped / modulation.period;
    const currentGeneration = Math.floor(progress);
    const travel = this.shepardGenerationY(line, progress);
    const copies = [];
    for (let generation = currentGeneration - shepard.cycles - 1; generation <= currentGeneration + shepard.cycles + 1; generation++) {
      const y = this.shepardGenerationY(line, generation) - travel;
      const alpha = Math.max(0, 1 - Math.abs(y) / shepard.octave_y);
      if (alpha > .001) copies.push({ generation, y, alpha });
    }
    return copies;
  }

  activeShepardCopy(line, beat) {
    const modulation = line.modulation;
    if (!modulation || !line.map) return null;
    const unwrapped = beat * line.map.scale + line.map.offset;
    if (unwrapped < 0) return null;
    const currentGeneration = Math.floor(unwrapped / modulation.period);
    return this.shepardCopies(line, beat).find(copy => copy.generation === currentGeneration) || null;
  }

  shepardNoteAlpha(line, beat, generation, note) {
    const modulation = line.modulation;
    const shepard = line.shepard;
    const unwrapped = beat * line.map.scale + line.map.offset;
    const start = generation * modulation.period + note.t;
    const end = start + note.d;
    const distance = unwrapped < start
      ? start - unwrapped
      : unwrapped > end ? unwrapped - end : 0;
    const window = modulation.period * (shepard.time_window_cycles || 1);
    return Math.max(0, 1 - distance / window);
  }

  drawShepardLine(line, lineIndex, sourceIndex, beat) {
    const source = this.sources[sourceIndex];
    const inverted = line.transform === "inversion";
    const copies = this.shepardCopies(line, beat);
    if (!copies.length) return;
    const ctx = this.context2d;
    ctx.save();
    ctx.fillStyle = VOICE_COLORS[lineIndex % VOICE_COLORS.length];
    ctx.strokeStyle = VOICE_COLORS[lineIndex % VOICE_COLORS.length];
    for (const copy of copies) {
      for (const note of source.notes) {
        const transformed = inverted ? this.invertedNote(note, sourceIndex) : note;
        const timeAlpha = this.shepardNoteAlpha(line, beat, copy.generation, note);
        if (timeAlpha <= .001) continue;
        for (const box of this.noteBoxes({ ...transformed, y: transformed.y + copy.y }, sourceIndex, inverted)) {
          ctx.globalAlpha = timeAlpha * .38;
          ctx.fillRect(box.x, box.y, box.width, box.height);
          ctx.globalAlpha = timeAlpha * .72;
          ctx.strokeRect(box.x + .5, box.y + .5, Math.max(0, box.width - 1), Math.max(0, box.height - 1));
        }
      }
    }
    ctx.restore();
  }

  trackMuted(trackIndex) {
    const lineIndex = this.lines.findIndex(line => line.tracks.includes(trackIndex));
    return lineIndex >= 0 && this.muted[lineIndex];
  }

  draw() {
    if (!this.width) return;
    const ctx = this.context2d;
    ctx.clearRect(0, 0, this.width, this.height);
    ctx.fillStyle = "#0b0b14";
    ctx.fillRect(0, 0, this.width, this.height);
    const padX = 18;
    const usable = this.width - padX * 2;
    const visualBeat = this.performance?.music_beats != null && this.position >= this.performance.music_beats
      ? this.performance.music_beats - .0001
      : this.position % this.score.beats;
    ctx.textBaseline = "middle";

    this.sources.forEach((source, sourceIndex) => {
      const geometry = source.geometry;
      ctx.fillStyle = geometry.bass ? "#77778a" : "#f3a712";
      ctx.font = geometry.bass ? "9px UbuntuMono, monospace" : "10px UbuntuMono, monospace";
      const annotations = [];
      if (source.inversion) annotations.push("INVERSIE ↕");
      if (source.modulation) annotations.push(`MOD ${source.modulation.label}`);
      const suffix = annotations.length ? " · " + annotations.join(" · ") : "";
      ctx.fillText((source.label + suffix).toUpperCase(), padX, geometry.labelY);
      for (let row = 0; row < geometry.rows; row++) {
        const rowPosition = geometry.rowBeats
          ? { start: geometry.rowBeats.slice(0, row).reduce((sum, beats) => sum + beats, 0), beats: geometry.rowBeats[row] }
          : { start: row * geometry.wrap, beats: geometry.wrap };
        const y = geometry.top + row * geometry.rowHeight;
        ctx.fillStyle = "#69697c";
        ctx.font = "9px UbuntuMono, monospace";
        const measure = rowPosition.start < this.pickup
          ? "OPM."
          : String(Math.floor((rowPosition.start - this.pickup) / this.meter) + 1).padStart(2, "0");
        ctx.fillText(measure, padX, y - 8);
        const gridBeats = [];
        if (geometry.bass) {
          gridBeats.push(0);
          let boundary = this.pickup || this.meter;
          while (boundary < rowPosition.start) boundary += this.meter;
          while (boundary <= rowPosition.start + rowPosition.beats) {
            gridBeats.push(boundary - rowPosition.start);
            boundary += this.meter;
          }
          gridBeats.push(rowPosition.beats);
        } else {
          for (let beat = 0; beat <= rowPosition.beats; beat++) gridBeats.push(beat);
        }
        for (const beat of [...new Set(gridBeats)]) {
          const absoluteBeat = rowPosition.start + beat;
          const x = padX + beat / rowPosition.beats * usable;
          const measureLine = geometry.bass || absoluteBeat === 0 || absoluteBeat === this.pickup || (absoluteBeat > this.pickup && (absoluteBeat - this.pickup) % this.meter === 0);
          ctx.strokeStyle = measureLine ? "#303044" : "#20202e";
          ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x, y + geometry.pitchArea + 14); ctx.stroke();
        }
        if (!geometry.bass) {
          const laneTops = source.inversion ? [y, y + geometry.mirrorOffset] : [y];
          for (const laneTop of laneTops) {
            for (let lane = 0; lane < 7; lane++) {
              ctx.strokeStyle = "#171724";
              ctx.beginPath(); ctx.moveTo(padX, laneTop + lane * 9); ctx.lineTo(this.width - padX, laneTop + lane * 9); ctx.stroke();
            }
          }
        }
        if (source.inversion) {
          const axisY = y + geometry.voicePitchArea + 14 + geometry.mirrorGap / 2;
          ctx.save();
          ctx.globalAlpha = .58;
          ctx.strokeStyle = "#8a8a9b";
          ctx.setLineDash([4, 5]);
          ctx.beginPath(); ctx.moveTo(padX, axisY); ctx.lineTo(this.width - padX, axisY); ctx.stroke();
          ctx.restore();
        }
      }
      const directShepard = this.lines.some(line =>
        line.source === sourceIndex && line.shepard && line.transform !== "inversion"
      );
      const inverseShepard = this.lines.some(line =>
        line.source === sourceIndex && line.shepard && line.transform === "inversion"
      );
      if (source.modulation && !directShepard) {
        const colorIndex = this.lines.findIndex(line => line.source === sourceIndex);
        ctx.save();
        ctx.fillStyle = VOICE_COLORS[colorIndex % VOICE_COLORS.length];
        ctx.strokeStyle = VOICE_COLORS[colorIndex % VOICE_COLORS.length];
        for (const layer of source.modulation.layers.slice(1)) {
          for (const note of source.notes) {
            for (const box of this.noteBoxes({ ...note, y: note.y + layer.y }, sourceIndex)) {
              ctx.globalAlpha = .07;
              ctx.fillRect(box.x, box.y, box.width, box.height);
              ctx.globalAlpha = .28;
              ctx.strokeRect(box.x + .5, box.y + .5, Math.max(0, box.width - 1), Math.max(0, box.height - 1));
            }
          }
        }
        ctx.restore();
      }
      if (source.inversion) {
        const colorIndex = source.inversion.lineIndexes.find(index => !this.muted[index]);
        if (colorIndex !== undefined && !inverseShepard) {
          ctx.save();
          ctx.fillStyle = VOICE_COLORS[colorIndex % VOICE_COLORS.length];
          ctx.strokeStyle = VOICE_COLORS[colorIndex % VOICE_COLORS.length];
          ctx.globalAlpha = .2;
          for (const note of source.notes) {
            for (const box of this.noteBoxes(this.invertedNote(note, sourceIndex), sourceIndex, true)) {
              ctx.fillRect(box.x, box.y, box.width, box.height);
              ctx.strokeRect(box.x + .5, box.y + .5, Math.max(0, box.width - 1), Math.max(0, box.height - 1));
            }
          }
          ctx.restore();
        }
        for (const lineIndex of source.inversion.lineIndexes) {
          const line = this.lines[lineIndex];
          const modulation = line.modulation || source.modulation;
          if (!modulation || this.muted[lineIndex] || line.shepard) continue;
          ctx.save();
          ctx.fillStyle = VOICE_COLORS[lineIndex % VOICE_COLORS.length];
          ctx.strokeStyle = VOICE_COLORS[lineIndex % VOICE_COLORS.length];
          for (const layer of modulation.layers.slice(1)) {
            for (const note of source.notes) {
              const reflected = this.invertedNote(note, sourceIndex);
              for (const box of this.noteBoxes({ ...reflected, y: reflected.y + layer.y }, sourceIndex, true)) {
                ctx.globalAlpha = .07;
                ctx.fillRect(box.x, box.y, box.width, box.height);
                ctx.globalAlpha = .28;
                ctx.strokeRect(box.x + .5, box.y + .5, Math.max(0, box.width - 1), Math.max(0, box.height - 1));
              }
            }
          }
          ctx.restore();
        }
      }
      this.lines.forEach((line, lineIndex) => {
        if (line.source === sourceIndex && line.shepard && !this.muted[lineIndex]) {
          this.drawShepardLine(line, lineIndex, sourceIndex, this.position);
        }
      });
      if (!directShepard) {
        for (const note of source.notes) {
          for (const box of this.noteBoxes(note, sourceIndex)) {
            ctx.fillStyle = geometry.bass ? "#77778a" : "#d9d5c5";
            ctx.globalAlpha = geometry.bass ? .62 : 1;
            ctx.fillRect(box.x, box.y, box.width, box.height);
          }
        }
      }
      ctx.globalAlpha = 1;
      const sourceDisplayBeats = geometry.sourceBeats;
      const mappedPosition = source.map ? this.mappedSourceTime(source.map, visualBeat) : visualBeat + this.displayOffset;
      if (mappedPosition != null) {
        const displayPosition = ((mappedPosition % sourceDisplayBeats) + sourceDisplayBeats) % sourceDisplayBeats;
        const playPosition = this.rowAt(displayPosition, geometry);
        const playX = padX + (displayPosition - playPosition.start) / playPosition.beats * usable;
        const playTop = geometry.top + playPosition.row * geometry.rowHeight;
        ctx.strokeStyle = geometry.bass ? "#77778a" : "#f4f0df";
        ctx.beginPath(); ctx.moveTo(playX, playTop); ctx.lineTo(playX, playTop + geometry.pitchArea + 14); ctx.stroke();
      }
    });

    const directionArrows = [];
    this.lines.forEach((line, lineIndex) => {
      if (this.muted[lineIndex]) return;
      const note = this.activeSourceNote(line, this.position);
      if (!note) return;
      const inverted = this.lineInvertedAt(line, this.position);
      if (line.shepard) {
        const transformed = inverted ? this.invertedNote(note, line.source) : note;
        const copy = this.activeShepardCopy(line, this.position);
        if (!copy) return;
        ctx.save();
        ctx.fillStyle = VOICE_COLORS[lineIndex % VOICE_COLORS.length];
        for (const box of this.noteBoxes({ ...transformed, y: transformed.y + copy.y }, line.source, inverted)) {
          ctx.globalAlpha = .95;
          ctx.fillRect(box.x - 2, box.y - 2 - lineIndex, box.width + 4, box.height + 4);
        }
        ctx.restore();
        return;
      }
      const boxes = this.noteBoxes(this.displayNote(note, line, this.position), line.source, inverted);
      if (inverted) {
        ctx.save();
        ctx.globalAlpha = .78;
        for (const box of boxes) {
          ctx.fillStyle = VOICE_COLORS[lineIndex % VOICE_COLORS.length];
          ctx.fillRect(box.x - 2, box.y - 2 - lineIndex, box.width + 4, box.height + 4);
        }
        ctx.restore();
      } else {
        for (const box of boxes) {
          const highlightX = box.x - 2;
          const highlightY = box.y - 2 - lineIndex;
          const highlightWidth = box.width + 4;
          const highlightHeight = box.height + 4;
          ctx.fillStyle = VOICE_COLORS[lineIndex % VOICE_COLORS.length];
          ctx.fillRect(highlightX, highlightY, highlightWidth, highlightHeight);
          if (line.direction) {
            const arrows = { right: "→", left: "←", down: "↓", up: "↑" };
            directionArrows.push({ glyph: arrows[line.direction], x: highlightX + highlightWidth / 2, y: highlightY + highlightHeight / 2 });
          }
        }
      }
    });
    ctx.save();
    ctx.fillStyle = "#ffffff";
    ctx.font = "700 11px UbuntuMono, monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    directionArrows.forEach(arrow => ctx.fillText(arrow.glyph, arrow.x, arrow.y));
    ctx.restore();
  }

  audioBeat(beat) {
    if (this.swing === 0.5) return beat;
    const whole = Math.floor(beat);
    const fraction = beat - whole;
    if (fraction <= 0.5) return whole + fraction * this.swing / 0.5;
    return whole + this.swing + (fraction - 0.5) * (1 - this.swing) / 0.5;
  }

  scoreBeat(beat) {
    if (this.swing === 0.5) return beat;
    const whole = Math.floor(beat);
    const fraction = beat - whole;
    if (fraction <= this.swing) return whole + fraction * 0.5 / this.swing;
    return whole + 0.5 + (fraction - this.swing) * 0.5 / (1 - this.swing);
  }

  performanceSeconds(beat) {
    const target = Math.max(0, beat);
    const map = this.performance.tempo_map || [{ beat: 0, bpm: this.playbackBpm }];
    let seconds = 0;
    for (let index = 0; index < map.length; index++) {
      const entry = map[index];
      const nextBeat = map[index + 1]?.beat;
      if (nextBeat == null || target <= nextBeat) {
        return seconds + (target - entry.beat) * 60 / entry.bpm;
      }
      seconds += (nextBeat - entry.beat) * 60 / entry.bpm;
    }
    return seconds;
  }

  performanceBeat(seconds) {
    const target = Math.max(0, seconds);
    const map = this.performance.tempo_map || [{ beat: 0, bpm: this.playbackBpm }];
    let elapsed = 0;
    for (let index = 0; index < map.length; index++) {
      const entry = map[index];
      const nextBeat = map[index + 1]?.beat;
      if (nextBeat == null) return entry.beat + (target - elapsed) * entry.bpm / 60;
      const segmentSeconds = (nextBeat - entry.beat) * 60 / entry.bpm;
      if (target <= elapsed + segmentSeconds) {
        return entry.beat + (target - elapsed) * entry.bpm / 60;
      }
      elapsed += segmentSeconds;
    }
    return 0;
  }

  performancePosition() {
    const scorePosition = Math.max(0, this.position - this.performance.offset_beats);
    return Math.min(this.performance.duration, this.performanceSeconds(this.audioBeat(scorePosition)));
  }

  syncPerformanceMute() {
    this.performanceAudio.forEach(stem => {
      stem.element.muted = stem.tracks.every(track => this.trackMuted(track));
    });
  }

  async preparePerformanceAudio(start) {
    const elements = this.performanceAudio.map(stem => stem.element);
    elements.forEach(element => {
      element.pause();
      element.playbackRate = 1;
    });
    await Promise.all(elements.map(element => element.readyState >= 1
      ? Promise.resolve()
      : new Promise(resolve => element.addEventListener("loadedmetadata", resolve, { once: true }))));
    elements.forEach(element => { element.currentTime = start; });
    await Promise.all(elements.map(element => element.seeking
      ? new Promise(resolve => element.addEventListener("seeked", resolve, { once: true }))
      : Promise.resolve()));
    await Promise.all(elements.map(element => element.readyState >= 3
      ? Promise.resolve()
      : new Promise(resolve => element.addEventListener("canplay", resolve, { once: true }))));
  }

  async playPerformance() {
    const start = this.performancePosition();
    const waitBeats = Math.max(0, this.performance.offset_beats - this.position);
    const waitMs = waitBeats * 60000 / this.playbackBpm;
    this.syncPerformanceMute();
    await this.preparePerformanceAudio(start);
    this.playing = true;
    this.performanceWaiting = waitMs > 0;
    this.performanceStartedAt = performance.now() / 1000 - this.position * 60 / this.playbackBpm;
    this.button.textContent = "■";
    this.button.title = "Stop";
    if (this.performanceWaiting) {
      this.performanceTimer = setTimeout(async () => {
        if (!this.playing) return;
        await Promise.all(this.performanceAudio.map(stem => stem.element.play()));
        this.performanceWaiting = false;
      }, waitMs);
    } else {
      await Promise.all(this.performanceAudio.map(stem => stem.element.play()));
    }
    this.tick();
  }

  async play() {
    if (activePlayer && activePlayer !== this) activePlayer.stop();
    activePlayer = this;
    if (this.performance) {
      await this.playPerformance();
      return;
    }
    const context = await audio.ensure();
    this.playing = true;
    this.button.textContent = "■";
    this.button.title = "Stop";
    const secondsPerBeat = 60 / this.playbackBpm;
    this.startedAt = context.currentTime - this.audioBeat(this.position) * secondsPerBeat;
    const startAt = context.currentTime + .035;
    this.score.staffs.forEach((staff, voice) => {
      if (this.trackMuted(voice)) return;
      for (const note of staff) {
        if (note.t + note.d <= this.position) continue;
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        oscillator.type = voice % 2 ? "sine" : "triangle";
        oscillator.frequency.value = 440 * Math.pow(2, (note.p - 69) / 12);
        const soundingFrom = Math.max(note.t, this.position);
        const offset = Math.max(0, (this.audioBeat(note.t) - this.audioBeat(this.position)) * secondsPerBeat);
        const remaining = (this.audioBeat(note.t + note.d) - this.audioBeat(soundingFrom)) * secondsPerBeat;
        const begin = startAt + offset;
        const end = begin + Math.max(.04, remaining * .94);
        const volume = .07 / Math.sqrt(this.score.staffs.length);
        gain.gain.setValueAtTime(.0001, begin);
        gain.gain.exponentialRampToValueAtTime(volume, begin + Math.min(.025, remaining / 3));
        gain.gain.setValueAtTime(volume * .75, Math.max(begin + .03, end - .04));
        gain.gain.exponentialRampToValueAtTime(.0001, end);
        oscillator.connect(gain).connect(context.destination);
        oscillator.start(begin); oscillator.stop(end + .01);
        this.nodes.push(oscillator);
      }
    });
    this.tick();
  }

  tick() {
    if (!this.playing) return;
    const secondsPerBeat = 60 / this.playbackBpm;
    const audioPosition = this.performance
      ? this.performanceWaiting
        ? (performance.now() / 1000 - this.performanceStartedAt) / secondsPerBeat
        : this.performance.offset_beats + this.performanceBeat(this.performanceAudio[0].element.currentTime)
      : (audio.context.currentTime - this.startedAt) / secondsPerBeat;
    this.position = this.scoreBeat(audioPosition);
    if (this.position >= this.totalBeats) {
      this.position = 0;
      this.range.value = 0;
      this.stop(false);
      this.draw(); this.updateTime();
      return;
    }
    this.range.value = this.position;
    this.draw(); this.updateTime();
    this.frame = requestAnimationFrame(() => this.tick());
  }

  stop(reset = true) {
    this.playing = false;
    clearTimeout(this.performanceTimer);
    cancelAnimationFrame(this.frame);
    this.nodes.forEach(node => { try { node.stop(); } catch (_) {} });
    this.nodes = [];
    this.performanceAudio.forEach(stem => stem.element.pause());
    this.button.textContent = "▶";
    this.button.title = "Afspelen";
    if (reset) {
      this.position = 0;
      this.range.value = 0;
      this.performanceAudio.forEach(stem => { stem.element.currentTime = 0; });
      this.draw(); this.updateTime();
    }
  }

  updateTime() {
    let total = this.totalBeats * 60 / this.playbackBpm;
    let current = this.position * 60 / this.playbackBpm;
    if (this.performance) {
      const offsetSeconds = this.performance.offset_beats * 60 / this.playbackBpm;
      total = offsetSeconds + this.performance.duration;
      current = this.position < this.performance.offset_beats
        ? this.position * 60 / this.playbackBpm
        : offsetSeconds + this.performanceSeconds(this.audioBeat(this.position - this.performance.offset_beats));
    }
    this.timeLabel.textContent = `${this.clock(current)} / ${this.clock(total)}`;
  }

  clock(seconds) {
    return Math.floor(seconds / 60) + ":" + String(Math.floor(seconds % 60)).padStart(2, "0");
  }
}

fetch("canon-data.json")
  .then(response => {
    if (!response.ok) throw new Error(`Canondata kon niet worden geladen (${response.status})`);
    return response.json();
  })
  .then(scores => {
    const byId = new Map(scores.map(score => [score.id, score]));
    document.querySelectorAll(".canon-player").forEach(element => {
      const score = byId.get(element.dataset.score);
      if (!score) return;
      element.innerHTML = `<div class="variation-control" hidden></div><div class="player-toolbar">
        <button class="play-button" type="button" title="Afspelen" aria-label="Afspelen">▶</button>
        <input type="range" min="0" value="0" step="0.02" aria-label="Afspeelpositie">
        <span class="player-time">0:00</span>
      </div><canvas aria-label="Diatonische pianorolls van de dux-bronnen"></canvas>
      <div class="player-footer"><span class="player-bpm">Partituur laden…</span><div class="voice-control" aria-label="Muzikale lijnen"></div></div>`;
      const playerKind = score.visual.performance ? "uitvoering" : "fragment";
      const playerBpm = score.visual.performance ? score.visual.performance.bpm : score.bpm;
      element.querySelector(".player-bpm").textContent = `${playerBpm} bpm · ${score.visual.lines.length} muzikale lijnen · ${playerKind}`;
      const player = new CanonPlayer(element, score);
      player.updateTime();
    });
  })
  .catch(error => document.querySelectorAll(".canon-player").forEach(element => {
    element.classList.add("player-error");
    element.querySelector(".player-bpm").textContent = error.message;
  }));
