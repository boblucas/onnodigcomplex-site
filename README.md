# onnodigcomplex-site

## [Read the live interactive essay: De canonische ruimte](https://boblucas.github.io/onnodigcomplex-site/)

Personal website and interactive archive of work by Bob Lucassen. The site brings
together software, constraint-solving projects, language experiments, puzzles,
visual art, and music that previously lived across MuseScore, Reddit, GitHub,
and older blogs.

The repository is deliberately simple: it is a static website with no framework,
package manager, bundler, or server-side runtime. Most pages are standalone HTML
documents. The main exception is the interactive canon essay, whose player loads
generated score data and synchronized audio stems in the browser.

## Highlights

- A compact personal homepage and browsable archive.
- Long-form posts imported from earlier publications.
- Custom typography and locally hosted visual assets.
- Responsive layouts for desktop and mobile.
- An interactive essay, **De canonische ruimte**, about musical canons.
- Diatonic piano-roll visualizations that preserve chromatic movement.
- Playback highlighting for dux, comes, free bass, double canons, inversions,
  retrogrades, augmentations, and modulating canons.
- Eight-way interval selectors for both sets of canons over a shared bass.
- MuseSounds performance stems with per-line mute controls.
- Shepard-tone-inspired animation for the continuously modulating construction
  in *Vitam et Mortem*.
- Reduced-motion support for the subtle parallax star field.

## Repository layout

```text
.
├── index.html                  Personal homepage
├── posts/
│   ├── index.html              Archive index
│   ├── onnodig.css             Shared post styling
│   ├── de-ruimte-van-canons.html
│   ├── canon.css               Canon essay and player styling
│   ├── canon-player.js         Canvas rendering and playback engine
│   ├── canon-data.json         Generated score and visualization data
│   ├── audio/                  Committed MP3 performance stems
│   └── *.html                  Individual archived posts
├── tools/
│   ├── build_canon_data.py     Extracts browser data from MuseScore files
│   └── export_musesounds_stems.py
├── img/                        General image assets
├── svg/                        Existing vector artwork
├── book-img/                   Images used by book-related posts
├── Ubuntu/                     Locally hosted Ubuntu fonts
└── Ubuntu_Mono/                Locally hosted Ubuntu Mono fonts
```

Generated Python bytecode, local port state, and similar machine-local files are
excluded through `.gitignore`.

## Run locally

No installation step is required for the website itself. Start any static HTTP
server in the repository root:

```bash
cd /path/to/onnodigcomplex-site
python3 -m http.server 8000
```

Then open:

- Homepage: <http://localhost:8000/>
- Post archive: <http://localhost:8000/posts/>
- Canon essay:
  <http://localhost:8000/posts/de-ruimte-van-canons.html>

Opening the canon essay directly as a `file://` URL is not sufficient in most
browsers. Its JavaScript uses `fetch()` to load `posts/canon-data.json`, so it
must be served over HTTP.

## The canon essay

The essay presents canon as a space of transformations rather than a list of
isolated compositional tricks. Its sequence moves from familiar imitation to
increasingly complex combinations:

1. Short time distances and syncopated entries.
2. Transposition and chromatic motion.
3. Inversion, augmentation, and retrograde.
4. Multiple readings of the same musical square.
5. Two simultaneous canons with independent themes.
6. Modulating canons with different cycle lengths.
7. A single theme projected across multiple transformations and time scales.

The page currently includes visualizations for:

- *Fly me to the moon*
- *Little chromatic canon at the major 2nd*
- *Canon based on Autumn leaves*
- *Canons in inversion on shared harmony*
- *On a slow boat to China*
- *8 more canons on a shared harmony*
- *Canon à 4, retrograde inversion & directus*
- *8 canons at each interval on the same harmony*
- *Fugue in G minor*
- *Double canon*
- *Double Modulating Canons*
- *Double phasing modulation canon*
- *Vitam et Mortem*
- *Double modulation canon №2*
- *Infinite inverted augmented multi-modulation multi-canon*
- *Infinite modulation canon à 3*

### Player behavior

Each player has a timeline, play/pause control, visualization canvas, and one
toggle per logical musical line. A logical line may contain several MuseScore
staves when those staves double the same material for timbre. Disabling a line
also silences its synthesized notes or performance stem.

The visualization draws the source melody, or **dux**, as a diatonic piano roll.
Follower voices illuminate the corresponding source events rather than drawing
unrelated copies. Transformations change that projection:

- **Inversion** reflects the source into a dedicated mirrored space.
- **Augmentation** advances through the same source at a slower rate.
- **Retrograde** traverses the source from its final event backwards.
- **Repeats** wrap the playback position onto the displayed source cycle.
- **Modulation** stacks pitch-shifted cycles vertically.
- **Shepard constructions** move a bounded, fading window over a conceptually
  endless transposed melody.
- **Free basses** receive a secondary compressed source visualization.
- **Double canons** receive independent dux sources and mappings.

Ties are merged into logical note events during extraction. Selected sources can
split those merged notes at bar boundaries where a traversal makes the notated
tie musically irrelevant. Rests participate in event indexing after a voice has
entered, preventing the next note from being highlighted during silence.

## Canon data pipeline

`tools/build_canon_data.py` reads `.mscz` archives directly with Python's
standard library. It extracts the main `.mscx` document, parses its XML, and
writes a compact JSON representation to `posts/canon-data.json`.

The generated note records contain:

- onset and duration in quarter-note beats;
- MIDI pitch;
- diatonic display position;
- voice number;
- logical event index.

The script also attaches hand-authored visualization metadata for material that
cannot be inferred reliably from notation alone. This includes:

- pickups, meters, swing, and row lengths;
- dux and follower track groupings;
- repeats and short ending tails;
- source-to-follower offsets and time scaling;
- inversions and retrograde traversals;
- free-bass mappings;
- independent cycles in double canons;
- modulation layers and Shepard directions;
- interval-variation boundaries and tempi;
- synchronized performance-stem metadata.

### Prerequisites

- Python 3.10 or newer.
- A local directory containing the referenced MuseScore source files.

The current source directory is intentionally explicit near the top of
`tools/build_canon_data.py`:

```python
SOURCE = Path("/home/bob/programming/musescore_backup")
```

Change `SOURCE` when running the generator on another machine. The filenames in
`SCORES` must match files in that directory.

### Regenerate the data

```bash
python3 tools/build_canon_data.py
```

The command reports the number of scores and notes written. Review the generated
diff rather than treating the JSON as disposable: the file is committed so the
deployed website has no build step.

Basic validation:

```bash
python3 -m py_compile tools/build_canon_data.py
python3 -m json.tool posts/canon-data.json >/dev/null
node --check posts/canon-player.js
git diff --check
```

## MuseSounds audio stems

`tools/export_musesounds_stems.py` renders individual musical lines while
preserving the mixer and MuseSounds settings saved inside each MuseScore
archive. It does this by:

1. Opening the `.mscz` ZIP archive.
2. Muting all unrelated parts in `audiosettings.json`.
3. Applying any score-specific structural edit in a temporary copy.
4. Calling MuseScore Studio in command-line mode.
5. Optionally trimming the result with FFmpeg.
6. Writing the final MP3 to `posts/audio/`.

The source scores are never modified.

Available presets:

| Preset | Output |
| --- | --- |
| `fly` | Dux, comes, and bass |
| `chromatic` | Dux, comes, and bass |
| `autumn` | Dux, comes, and bass |
| `slowboat` | Dux, comes, and bass; first eight measures |
| `derectus` | Four traversing voices; introductory square removed |
| `double` | Four independent lines; repeated section plus final chord |

### Prerequisites

- MuseScore Studio with the required MuseSounds libraries installed.
- An AppImage or executable that can render the saved score from the command
  line.
- FFmpeg for presets that require trimming.
- The original `.mscz` files in the configured backup directory.

The checked-in defaults reflect the author's workstation:

```text
/home/bob/programming/musescore_backup
/home/bob/Downloads/MuseScore-Studio-4.7.4.260706075-x86_64.AppImage
```

Both can be overridden without editing the script:

```bash
python3 tools/export_musesounds_stems.py fly \
  --musescore /path/to/MuseScore-Studio.AppImage \
  --output posts/audio
```

Render every configured preset:

```bash
python3 tools/export_musesounds_stems.py all \
  --musescore /path/to/MuseScore-Studio.AppImage \
  --ffmpeg ffmpeg
```

MuseScore Studio must already know where its MuseSounds libraries are located.
The command-line exporter uses the settings saved in the score; it does not
install sound libraries or recreate mixer choices.

The MP3 files are committed because the production site is static. After
re-rendering, verify playback synchronization in the browser before committing.
In particular, check pickups, deliberately delayed first entries, repeat
boundaries, tempo changes, and final chords.

## Adding or updating a canon

The complete workflow is:

1. Save the authoritative score in the MuseScore source directory.
2. Add or update its entry in `SCORES` in `tools/build_canon_data.py`.
3. Define its logical sources and lines in `VISUALS`.
4. Add structural mappings that notation alone cannot express.
5. Regenerate `posts/canon-data.json`.
6. Add a `.canon-player` element with the matching `data-score` identifier to
   `posts/de-ruimte-van-canons.html`.
7. If using MuseSounds audio, add an export preset, render the stems, and attach
   the stem metadata to the visualization configuration.
8. Test seeking, muting, repeats, rests, ties, and the final playback position.
9. Test at desktop and narrow mobile widths.

Prefer representing musical structure in the generator metadata instead of
special-casing a score inside the canvas renderer. This keeps
`canon-player.js` focused on reusable mappings and drawing behavior.

## Editing the static site

There is no template layer. Edit the relevant HTML and CSS files directly.

- Global homepage changes belong in `index.html`.
- Archive-wide post styling belongs in `posts/onnodig.css`.
- Canon-specific layout and responsive rules belong in `posts/canon.css`.
- Player behavior belongs in `posts/canon-player.js`.
- Extracted score content belongs in `posts/canon-data.json` via the generator.

Use relative asset paths so pages continue to work when deployed under the
repository root. Keep source images and audio in their existing asset
directories rather than embedding large data URLs in HTML.

## Deployment

The repository can be deployed to any static host. Publish the repository root
as-is; there is no build command and no generated distribution directory.

For GitHub Pages, select the `main` branch and `/ (root)` as the publishing
source in the repository's Pages settings. Other static hosts only need an
equivalent root-directory configuration.

## Browser and accessibility notes

- Playback starts only after a user gesture, as required by browser audio
  policies.
- The player uses the Web Audio API for synthesized fragments and HTML audio
  elements for recorded performance stems.
- Canvas dimensions are recalculated responsively.
- Controls include accessible labels and titles.
- The star field respects `prefers-reduced-motion`.
- Current evergreen versions of Firefox, Chromium, and Safari are the intended
  targets.

## Content and licensing

The music, writing, generated data, recordings, and visual assets in this
repository are original portfolio content unless a page explicitly credits
another source. Third-party names and referenced songs remain the property of
their respective owners.

No open-source or content license has been granted by this repository. The code
and content therefore remain under their default copyright protection until a
license is added explicitly.
