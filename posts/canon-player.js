const VOICE_COLORS = ["#f3a712", "#45a6e5", "#ef6351", "#49c889", "#a978d4", "#f4f0df"];
let activePlayer = null;

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
    this.score = score;
    this.canvas = element.querySelector("canvas");
    this.context2d = this.canvas.getContext("2d");
    this.button = element.querySelector(".play-button");
    this.range = element.querySelector("input[type=range]");
    this.timeLabel = element.querySelector(".player-time");
    this.voiceControl = element.querySelector(".voice-control");
    this.displayBeats = score.visual.display_beats || score.beats;
    this.displayOffset = score.visual.display_offset || 0;
    this.wrapBeats = score.visual.wrap || (this.displayBeats > 40 ? 12 : 8);
    this.rowBeats = score.visual.row_beats || null;
    this.pickup = score.visual.pickup || 0;
    this.swing = score.visual.swing || 0.5;
    this.meter = score.visual.meter || 4;
    this.position = 0;
    this.playing = false;
    this.startedAt = 0;
    this.nodes = [];
    this.lines = score.visual.lines;
    this.sources = score.visual.sources.map(source => {
      const sourceStart = source.start || 0;
      const sourceBeats = source.beats || this.displayBeats;
      const inDisplay = note => sourceStart <= note.t && note.t < sourceStart + sourceBeats;
      const normalize = note => ({ ...note, t: note.t - sourceStart, d: Math.min(note.d, sourceStart + sourceBeats - note.t) });
      let notes = this.uniqueChords(score.staffs[source.track].filter(note => note.v === 0 && inDisplay(note)).map(normalize));
      if (!notes.length) notes = this.uniqueChords(score.staffs[source.track].filter(inDisplay).map(normalize));
      if (source.split_bars) notes = this.splitAtBars(notes, source.split_bars);
      const eventCount = Math.max(...notes.map(note => note.i)) + 1;
      return { ...source, notes, eventCount };
    });
    this.muted = this.lines.map(() => false);
    this.bind();
    this.buildVoiceControl();
    this.resize();
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

  bind() {
    this.button.addEventListener("click", () => this.playing ? this.stop() : this.play());
    this.range.max = this.score.beats;
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
      `<button type="button" class="voice-swatch" style="--voice:${VOICE_COLORS[index % VOICE_COLORS.length]}" aria-pressed="true" title="Lijn ${line.label} aan- of uitzetten">${line.label}</button>`
    ).join("");
    [...this.voiceControl.children].forEach((button, index) => button.addEventListener("click", () => {
      const resume = this.playing;
      this.muted[index] = !this.muted[index];
      button.setAttribute("aria-pressed", String(!this.muted[index]));
      button.classList.toggle("muted", this.muted[index]);
      if (resume) {
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
      const rowHeight = bass ? 42 : 82;
      const pitchArea = bass ? 22 : 54;
      source.geometry = { bass, wrap, sourceBeats, rowBeats, rows, rowHeight, pitchArea, labelY: cursor + 10, top: cursor + 28, height: 28 + rows * rowHeight };
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

  noteBoxes(note, sourceIndex) {
    const source = this.sources[sourceIndex];
    const geometry = source.geometry;
    const padX = 18;
    const usable = this.width - padX * 2;
    const pitches = source.notes.map(item => item.y);
    const low = Math.min(...pitches) - 1;
    const high = Math.max(...pitches) + 1;
    const pitchHeight = geometry.pitchArea / Math.max(7, high - low);
    const boxes = [];
    const noteEnd = note.t + note.d;
    let segmentStart = note.t;
    while (segmentStart < noteEnd - 0.0001) {
      const position = this.rowAt(segmentStart, geometry);
      const segmentEnd = Math.min(noteEnd, position.start + position.beats);
      const rowTop = geometry.top + position.row * geometry.rowHeight;
      boxes.push({
        x: padX + (segmentStart - position.start) / position.beats * usable,
        y: rowTop + geometry.pitchArea + 9 - (note.y - low) * pitchHeight,
        width: Math.max(2, (segmentEnd - segmentStart) / position.beats * usable - 1),
        height: Math.max(geometry.bass ? 2 : 4, pitchHeight * .72),
        row: position.row
      });
      segmentStart = segmentEnd;
    }
    return boxes;
  }

  activeOrdinal(tracks, beat) {
    for (const track of tracks) {
      const sounding = this.score.staffs[track].find(note => note.t <= beat && note.t + note.d > beat);
      if (sounding) return sounding.i;
    }
    return null;
  }

  activeSourceNote(line, beat) {
    const ordinal = this.activeOrdinal(line.tracks, beat);
    if (ordinal === null) return null;
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
      let sourceTime = beat * line.map.scale + line.map.offset;
      if (line.map.modulo) sourceTime = ((sourceTime % line.map.modulo) + line.map.modulo) % line.map.modulo;
      return source.notes.find(note => note.t <= sourceTime && note.t + note.d > sourceTime) || null;
    }
    const sourceOrdinal = ordinal % source.eventCount;
    return source.notes.find(note => note.i === sourceOrdinal) || null;
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
    ctx.textBaseline = "middle";

    this.sources.forEach((source, sourceIndex) => {
      const geometry = source.geometry;
      ctx.fillStyle = geometry.bass ? "#77778a" : "#f3a712";
      ctx.font = geometry.bass ? "9px UbuntuMono, monospace" : "10px UbuntuMono, monospace";
      const suffix = "";
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
          for (let lane = 0; lane < 7; lane++) {
            ctx.strokeStyle = "#171724";
            ctx.beginPath(); ctx.moveTo(padX, y + lane * 9); ctx.lineTo(this.width - padX, y + lane * 9); ctx.stroke();
          }
        }
      }
      for (const note of source.notes) {
        for (const box of this.noteBoxes(note, sourceIndex)) {
          ctx.fillStyle = geometry.bass ? "#77778a" : "#d9d5c5";
          ctx.globalAlpha = geometry.bass ? .62 : 1;
          ctx.fillRect(box.x, box.y, box.width, box.height);
        }
      }
      ctx.globalAlpha = 1;
      const sourceDisplayBeats = geometry.sourceBeats;
      const displayPosition = ((this.position + this.displayOffset) % sourceDisplayBeats + sourceDisplayBeats) % sourceDisplayBeats;
      const playPosition = this.rowAt(displayPosition, geometry);
      const playX = padX + (displayPosition - playPosition.start) / playPosition.beats * usable;
      const playTop = geometry.top + playPosition.row * geometry.rowHeight;
      ctx.strokeStyle = geometry.bass ? "#77778a" : "#f4f0df";
      ctx.beginPath(); ctx.moveTo(playX, playTop); ctx.lineTo(playX, playTop + geometry.pitchArea + 14); ctx.stroke();
    });

    const directionArrows = [];
    this.lines.forEach((line, lineIndex) => {
      if (this.muted[lineIndex]) return;
      const note = this.activeSourceNote(line, this.position);
      if (!note) return;
      for (const box of this.noteBoxes(note, line.source)) {
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

  async play() {
    if (activePlayer && activePlayer !== this) activePlayer.stop();
    activePlayer = this;
    const context = await audio.ensure();
    this.playing = true;
    this.button.textContent = "■";
    this.button.title = "Stop";
    const secondsPerBeat = 60 / this.score.bpm;
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
    const secondsPerBeat = 60 / this.score.bpm;
    const audioPosition = (audio.context.currentTime - this.startedAt) / secondsPerBeat;
    this.position = this.scoreBeat(audioPosition);
    if (this.position >= this.score.beats) {
      this.position = 0;
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
    cancelAnimationFrame(this.frame);
    this.nodes.forEach(node => { try { node.stop(); } catch (_) {} });
    this.nodes = [];
    this.button.textContent = "▶";
    this.button.title = "Afspelen";
    if (reset) {
      this.position = 0;
      this.range.value = 0;
      this.draw(); this.updateTime();
    }
  }

  updateTime() {
    const total = this.score.beats * 60 / this.score.bpm;
    const current = this.position * 60 / this.score.bpm;
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
      element.innerHTML = `<div class="player-toolbar">
        <button class="play-button" type="button" title="Afspelen" aria-label="Afspelen">▶</button>
        <input type="range" min="0" value="0" step="0.02" aria-label="Afspeelpositie">
        <span class="player-time">0:00</span>
      </div><canvas aria-label="Diatonische pianorolls van de dux-bronnen"></canvas>
      <div class="player-footer"><span class="player-bpm">Partituur laden…</span><div class="voice-control" aria-label="Muzikale lijnen"></div></div>`;
      element.querySelector(".player-bpm").textContent = `${score.bpm} bpm · ${score.visual.lines.length} muzikale lijnen · fragment`;
      const player = new CanonPlayer(element, score);
      player.updateTime();
    });
  })
  .catch(error => document.querySelectorAll(".canon-player").forEach(element => {
    element.classList.add("player-error");
    element.querySelector(".player-bpm").textContent = error.message;
  }));
