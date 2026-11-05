---
name: Pressmark
description: A quiet desktop reading room for finding every mention of a person or body in a corpus of primary sources, with the original passage behind every claim.
colors:
  paper: "#f7f6f2"
  surface: "#ffffff"
  ink: "#1f1f1c"
  muted-ink: "#66655f"
  rule: "#d9d6cc"
  field-rule: "#8a877d"
  shelf: "#efede6"
  bubble: "#e9e6dc"
  rust: "#8a3b12"
  on-rust: "#ffffff"
  verified: "#2f7d32"
  fault: "#b3261e"
  pending: "#8a6800"
  highlight: "#fff4d6"
  doubt: "#fbe9e7"
  scan-paper: "#ffffff"
  scrollbar: "#c9c5b8"
  scrollbar-hover: "#a9a597"
  paper-dark: "#1b1b19"
  surface-dark: "#252522"
  ink-dark: "#ecebe6"
  muted-ink-dark: "#a8a69e"
  rule-dark: "#3c3b36"
  field-rule-dark: "#77756d"
  shelf-dark: "#161614"
  bubble-dark: "#2e2d29"
  rust-dark: "#e08a5a"
  on-rust-dark: "#1b1b19"
  verified-dark: "#7cc47f"
  fault-dark: "#f2867e"
  pending-dark: "#e0c060"
  highlight-dark: "#3b3220"
  doubt-dark: "#402a26"
  scrollbar-dark: "#57554e"
  scrollbar-hover-dark: "#6f6d65"
typography:
  display:
    fontFamily: "Georgia, 'Noto Serif', serif"
    fontSize: "1.8rem"
    fontWeight: 400
    lineHeight: 1.25
  headline:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 700
    lineHeight: 1.25
  headline-settings:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "1.35rem"
    fontWeight: 700
    lineHeight: 1.25
  title:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "1rem"
    fontWeight: 700
    lineHeight: 1.3
  body:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.45
  document:
    fontFamily: "Georgia, 'Noto Serif', 'Songti SC', 'SimSun', serif"
    fontSize: "1.04rem"
    fontWeight: 400
    lineHeight: 1.62
  document-heading:
    fontFamily: "Georgia, 'Noto Serif', 'Songti SC', 'SimSun', serif"
    fontSize: "1.15rem"
    fontWeight: 700
    lineHeight: 1.3
  note:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
    fontSize: "0.9rem"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "0.02em"
  mono:
    fontFamily: "Consolas, 'Courier New', monospace"
    fontSize: "0.85em"
    fontWeight: 400
rounded:
  hairline: "3px"
  xs: "4px"
  sm: "6px"
  md: "8px"
  lg: "10px"
  xl: "12px"
  bubble: "16px"
  pill: "999px"
spacing:
  hair: "0.15rem"
  xs: "0.35rem"
  sm: "0.5rem"
  md: "0.8rem"
  lg: "1rem"
  xl: "1.5rem"
  reading-column: "46rem"
  sidebar: "15.5rem"
  sidebar-collapsed: "3.25rem"
components:
  button:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0.35rem 0.8rem"
  button-primary:
    backgroundColor: "{colors.rust}"
    textColor: "{colors.on-rust}"
    rounded: "{rounded.sm}"
    padding: "0.35rem 0.8rem"
  button-quiet:
    textColor: "{colors.rust}"
    padding: "0.2rem 0"
  button-icon:
    textColor: "{colors.muted-ink}"
    rounded: "{rounded.sm}"
    size: "2rem"
  button-send:
    backgroundColor: "{colors.rust}"
    textColor: "{colors.on-rust}"
    rounded: "{rounded.pill}"
    size: "2rem"
  button-send-stop:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.pill}"
    size: "2rem"
  chip:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "0.25rem 0.75rem"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0.35rem 0.5rem"
  composer:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.bubble}"
    padding: "0.65rem 0.7rem 0.45rem 0.95rem"
  sidebar-row:
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0.45rem 0.5rem"
  card-thread:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.xl}"
    padding: "0.9rem 1rem"
  card-settings:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "1rem 1.2rem"
  user-message:
    backgroundColor: "{colors.bubble}"
    textColor: "{colors.ink}"
    rounded: "{rounded.bubble}"
    padding: "0.55rem 0.95rem"
  tab:
    textColor: "{colors.muted-ink}"
    padding: "0.6rem 0 0.5rem"
  tab-active:
    textColor: "{colors.ink}"
    padding: "0.6rem 0 0.5rem"
  toggle:
    backgroundColor: "{colors.rule}"
    rounded: "{rounded.pill}"
    width: "2.3rem"
    height: "1.3rem"
  toggle-on:
    backgroundColor: "{colors.rust}"
    rounded: "{rounded.pill}"
    width: "2.3rem"
    height: "1.3rem"
  dialog:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    width: "min(32rem, 92vw)"
---

# Design System: Pressmark

> **Read this before touching anything in `scripts/interfaccia/`.** It records the decisions already made so later sessions extend the system instead of drifting from it. The normative values live in `scripts/interfaccia/app.css` (`:root` custom properties); this file names them, explains them and states the rules. If the two disagree, fix whichever one is wrong and keep them in step.

## Overview

**Creative North Star: "The Reading Room"**

Pressmark is a reading room in an archive. The researcher comes with a question, the sources and the answer sit on the table in front of them, and the room itself stays quiet: warm paper, dark ink, a single rust-coloured mark where something can be acted on. The interface is furniture. It arrives, holds the material steady, and gets out of the way. Every claim in an answer points back to the passage it came from, so the visual system's real job is to make *provenance* legible: what was found, what was verified, what is still in doubt.

The app is a desktop tool (a local Python server shown in a pywebview / WebView2 window, or a browser tab) used for long sessions of close reading. Density is moderate and calm: a conversational thread in a 46rem column, a sidebar of projects and recent searches, and a side panel for sources, passages and the glossary. Two voices of type share the room: a serif for what is *read* (answers, transcriptions, the empty-state question) and the system sans for everything that is *operated*. Light and dark themes follow the operating system and are equal citizens.

Motion is functional and short. Things that arrive say where you are or what is new; nothing loops for decoration except progress that must show it is alive. Keyboard navigation arrives without motion at all.

**Key Characteristics:**
- Warm paper neutrals, never pure grey; one accent (rust) used sparingly.
- Serif for reading, system sans for operating; the split is semantic, not decorative.
- Flat surfaces separated by hairline rules and one-step tonal shifts, not shadows.
- Status is always carried by shape or text as well as colour (checkmarks, hollow dots, dashed underlines).
- Short, purposeful motion with custom ease-out curves; none from the keyboard, none that moves under reduced motion.
- Accessibility is a design constraint, not a pass: 4.5:1 text, 3:1 control outlines, visible focus.

## Colors

A warm, low-chroma paper-and-ink palette with one rust accent and three status hues; every value has a dark-theme twin (the `-dark` keys above), switched by `prefers-color-scheme`.

### Primary
- **Rust Ink** (`rust` / `rust-dark`): the only accent. Primary buttons, the send button, the active tab underline, the focus ring, links and citation references, progress fill, the selected toggle, the hover outline on ordinary buttons, the resize-handle glow. Text on it uses **On Rust** (`on-rust`: white in light, near-black paper in dark, because the dark-theme rust is a light terracotta).

### Neutral
- **Reading Paper** (`paper`): the page background behind the thread and views.
- **Card Stock** (`surface`): raised material: cards, inputs, the composer, dialogs, the side panel, tooltips.
- **Shelf** (`shelf`): the sidebar, one tone *below* paper in both themes, so the column of furniture recedes.
- **Bubble Linen** (`bubble`): the researcher's own messages in the thread.
- **Ink** (`ink`): body text and headings.
- **Faded Ink** (`muted-ink`): secondary text, notes, labels, placeholders, inactive tabs, icon buttons at rest. Still 4.5:1 on paper and surface.
- **Hairline** (`rule`): borders of cards and panels, table rules, dividers between rows.
- **Field Rule** (`field-rule`): outlines of inputs, chips that are buttons, the composer box, keyboard keys. Chosen to reach 3:1 against paper (WCAG 1.4.11); use it whenever an outline is the only thing that says "this is a control".
- **Scan Paper** (`scan-paper`): always-white backing behind scanned page images, which may have transparency.
- **Scrollbar / Scrollbar Hover**: thin themed scrollbar thumbs on a transparent track.
- **Hover wash** (`--sopra`, `rgba(31,31,28,.06)` / `rgba(236,235,230,.07)`): the translucent fill for borderless rows and icon buttons on hover or when current. Not in the frontmatter because it is an alpha overlay, not a colour.

### Status
- **Verified Green** (`verified`): a citation found in its source, a completed step, a ready provider, a working connection.
- **Fault Red** (`fault`): errors, a citation *not* found, destructive actions on hover, a stopped step.
- **Pending Ochre** (`pending`): in progress, optional, or advisory (a hint, not an error). Also used as text: 4.5:1 on paper and surface.
- **Highlight Wash** (`highlight`): the highlighted source line, citation hover, text selection, the top notice bar.
- **Doubt Wash** (`doubt`): rows flagged for review in the revision table.

### Named Rules
**The One Rust Rule.** Rust is the only accent. It marks what can be acted on or what currently holds focus. Never introduce a second accent hue, and never use rust for decoration, headings or large fills beyond a primary button or the send button.

**The Not-Only-Colour Rule.** Every status colour travels with a second signal: a checkmark or exclamation icon after a citation, a dashed underline for a citation not found, a hollow ring (not a filled dot) for a failed connection, a numbered or ticked step marker. A colour-blind reader must lose nothing.

**The Twin Rule.** Every colour token is defined in both themes in the same `:root` block pair. Never hard-code a hex in a component rule; add or reuse a custom property, and give it a dark value at the same time.

## Typography

**Reading Font:** Georgia (with Noto Serif, then Songti SC / SimSun so Chinese sources render in a serif)
**Operating Font:** system-ui (with -apple-system, Segoe UI, Roboto, sans-serif)
**Mono Font:** Consolas (with Courier New), only for codes, identifiers and inline `code`

**Character:** A bookish serif for the material and the operating system's own sans for the tool around it. The pairing says "this is a document" versus "this is a control" at a glance, and the system sans keeps the app native inside its desktop window.

### Hierarchy
- **Display** (Georgia 400, 1.8rem, 1.25): only the empty-state question ("Che cosa cerchi nelle fonti?"). One per screen, centred.
- **Headline** (system 700, 1.25rem, 1.25): panel and view titles (`h2`). In Settings sections, 1.35rem. More space above a heading than below (1.6rem above when not first).
- **Title** (system 700, 1rem, 1.3): sub-sections (`h3`), card titles, setting names (600 weight).
- **Body** (system 400, 15px, 1.45): all interface text. The root size is 15px, not 16px: the app is dense desktop furniture.
- **Document** (Georgia 400, 1.04rem, 1.62): the answer in the thread, source transcriptions, extracts. Its `h2` is 1.15rem with a hairline rule beneath; its tables drop to 0.9rem.
- **Note** (system 400, 0.9rem, muted ink): explanations, captions, details under a row. Smaller details step down to 0.85, 0.82 and 0.78rem; never below 0.72rem.
- **Label** (system 600, 0.75rem, letter-spacing 0.02em, muted ink, sentence case): small section headers in the sidebar ("Recenti") and settings nav, metadata labels.
- **Mono** (Consolas, 0.85em): language codes, file names, identifiers.

### Named Rules
**The Two Voices Rule.** Serif means "read me", sans means "use me". Answers, transcriptions, quoted passages and the empty-state question are serif; buttons, menus, labels, tables of settings and status are sans. Do not set controls in Georgia or answers in system-ui.

**The Tabular Count Rule.** Any number that updates in place (counters, step numbers, progress, timings) uses `font-variant-numeric: tabular-nums` so it does not jitter.

**The No Uppercase Rule.** Labels are sentence case with a slight letter-spacing; there are no all-caps eyebrows in the interface.

## Layout

The window is a three-column grid filling the viewport (`body` does not scroll; each column scrolls on its own):

1. **Sidebar** (`fianco`, 15.5rem by default, resizable by dragging its edge; 3.25rem when collapsed with Ctrl+B): logotype, project selector, "Nuova ricerca", filtered list of recent searches grouped by entity, and a footer (Glossary, Import sources, Settings).
2. **Centre** (`centro`): the conversational thread and the composer. Content is held to a **46rem reading column**, centred, with 1.5rem side padding. The empty state sits ~22vh from the top, centred.
3. **Side panel** (`laterale`, `clamp(24rem, 36vw, 42rem)`, resizable): opens on demand for sources, passages, glossary; tabs on top, its own scroll below. Inner views cap at 60rem.

Settings replace the centre with a two-column grid: a 15.5rem navigation column and a content column whose sections also cap at 46rem.

Spacing is rem-based and tuned per component rather than drawn from a strict scale; the recurring steps are 0.15, 0.35, 0.5, 0.8, 1 and 1.5rem (frontmatter `spacing`). Gaps between thread messages are 1.4rem; between settings cards, 1rem; between rows inside a card, hairline rules with ~0.6rem padding.

Responsive behaviour is minimal because the target is a desktop window: the only breakpoint is **800px**, where multi-column step lists and environment rows collapse to two columns. Resizing the panels is the user's primary responsive tool, and their widths are persisted.

**The Reading Column Rule.** Any long-form content (thread, settings sections, answers) is capped at 46rem and centred. Never let prose run the full width of a wide window.

## Elevation & Depth

Pressmark is flat. Depth comes from **tonal layering** (shelf below paper, surface above paper) and **hairline rules**, not from shadows. A card is a surface-coloured box with a 1px hairline; the sidebar and side panel are separated from the centre by a single 1px rule.

### Shadow Vocabulary
- **Tooltip lift** (`box-shadow: 0 6px 20px rgba(0,0,0,.12), 0 1px 4px rgba(0,0,0,.08)`): only the floating citation preview (`anteprima`), because it hovers over text and must separate from it.
- **Toggle knob** (`box-shadow: 0 1px 2px rgba(0,0,0,.25)`): the sliding knob of a switch, to read as a physical lever.
- **Modal dim** (`::backdrop`, `rgba(0,0,0,.35)`): dialogs dim the room behind them instead of casting a shadow.
- **Inset marks** (`inset 3px 0 0 rust` on a highlighted source line; `inset 0 0 0 2px rust` on a focused revision cell; `inset 0 0 0 2px fault` for a failed status dot): used as drawn marks, not as elevation.

**The Flat Table Rule.** Surfaces are flat at rest and stay flat on hover. A new component gets a hairline and a tonal step, never a drop shadow, unless it genuinely floats above content like the tooltip.

## Shapes

Gently rounded, never pill-shaped by default, with a clear ladder by size and role:

- **3–4px** (`hairline`, `xs`): tiny inline things: citation hit areas, keyboard keys, "open source" mini-buttons, progress bar track.
- **6px** (`sm`): the workhorse: buttons, inputs, selects, sidebar rows, icon buttons, the revision table frame.
- **8px** (`md`): inline containers inside content: blockquotes, summary boxes, model lists.
- **10px** (`lg`): settings cards, dialogs, the citation tooltip.
- **12px** (`xl`): cards in the thread, the filter box.
- **16px** (`bubble`): the composer box and the user's message bubble, the two softest shapes, because they are the conversational surfaces.
- **999px** (`pill`): chips, the "Fonti" answer action, provider status badges, toggles, scrollbar thumbs; and the circular send button.

Disclosure arrows are drawn with CSS borders (a rotated corner) and rotate 90° on open; there is no icon font. Icons are inline SVG on a 24px grid, stroked at 1.75 with round caps and joins, sized 1.1rem, coloured by `currentColor`.

## Components

### Buttons
Quiet and tactile: they respond instantly to a press and change colour gently on hover.
- **Shape:** gently rounded (6px), 1px hairline border, surface background.
- **Default hover:** border turns rust; nothing else moves.
- **Press:** `scale(.97)` over 160ms with the custom ease-out (wide sidebar rows use `.98`, the round send button `.94`).
- **Primary:** rust fill, on-rust text, rust border. Use for the single main action of a card or dialog.
- **Quiet (`discreto`):** text-only rust link-button, underline on hover. For secondary actions inside text ("change", "show all").
- **Danger (`pericolo`):** ordinary button with fault-red text and fault border on hover. Never a red-filled button.
- **Icon:** 2rem square, borderless, muted ink at rest; hover adds the hover wash and full ink colour.
- **Send / Stop:** a 2rem circle. Send is rust; while a search runs it becomes Stop in ink with paper-coloured icon. The swap cross-fades with a slight 2px blur so it reads as one control changing state.
- **Disabled:** 50% opacity, default cursor.

### Chips
- **Style:** pill, hairline border, surface background, 0.9rem. Suggestion chips in the empty state use the field-rule outline so they read as buttons in both themes.
- **Static chips:** transparent background (information, not action).

### Cards / Containers
- **Thread card (`msg.scheda`):** surface, hairline, 12px, 0.9rem × 1rem padding. Once decided it collapses to a single muted line with no box (**The Trace Rule**: a past decision stays as a trace without weight).
- **Settings card (`riquadro`):** surface, hairline, 10px, 1rem × 1.2rem padding; its first and last children lose their outer margins.
- **Setting row (`impostazione`):** title and description on the left, control on the right; consecutive rows separated by a hairline.
- **User message:** bubble linen, 16px, right-aligned, max 85% width, preserves line breaks.

### Inputs / Fields
- **Style:** surface background, 1px field-rule outline (3:1), 6px radius, 0.35 × 0.5rem padding. Placeholders in muted ink at full opacity.
- **Composer:** a 16px surface box with field-rule outline; on `:focus-within` the outline turns rust. The textarea inside is borderless and grows to 200px.
- **Uncommitted choice:** a select changed by arrow keys but not yet confirmed shows a dashed rust outline.
- **Model picker:** a borderless select sized to its content (`field-sizing: content`), muted until hover/focus, when it gains the hover wash and a hairline, so it reads as a control and not a caption.

### Navigation
- **Sidebar rows:** full-width borderless buttons, 6px radius, icon + label with 0.55rem gap; hover and current (`aria-current`) both use the hover wash; current also goes semibold.
- **Recent searches:** title on top, a muted 0.78rem detail line below (status, time), both ellipsised. A per-row "more" button appears only on hover or focus. Multiple searches on the same entity group under a disclosure with an indented hairline.
- **Tabs (side panel):** text-only, muted; active tab is ink, semibold, with a 2px rust underline that sits on the panel header's rule.
- **Settings nav:** same row style as the sidebar, with section labels and provider rows (logo, name, cost line); providers not yet ready are shown in muted ink.

### Status signals
- **Connection dot (`pallino`):** 0.7rem circle. Pending pulses (opacity 1 ↔ .35, 1s); success fills green, failure is a hollow red ring; on arrival of a result it sends one ripple outward in its own colour.
- **Search steps (`tappe-ricerca`):** numbered circles with tabular figures; the current step fills rust and goes semibold; done steps become green circles with a white tick; a stopped step turns fault red.
- **Progress bar:** 0.5rem track in paper with a hairline; rust fill driven by `transform: scaleX()` (never `width`); while mid-way a soft highlight sweeps across it so it looks alive even when the number stalls.
- **Notice bar (`avviso`):** highlight wash strip at the top of the centre column; error variant colours the text fault red. Slides down 6px on arrival.

### Citations (signature component)
The heart of the product: every claim links to its source.
- **Reference (`a.rimando`):** rust, dotted underline (so it is distinguishable without colour, also in dark), a hit area larger than the number without shifting text; hover/focus fills it with the highlight wash.
- **Preview (`anteprima`):** a floating card (surface, hairline, 10px, tooltip lift) showing the reference and the start of the translation; grows from the reference with `scale(.97)` over 125ms; chained previews appear without motion.
- **Verified quote (`citazione`):** 2px green underline plus a small tick icon. **Not found:** dashed red underline, red text, and an exclamation-circle icon.
- **Highlighted source line:** highlight wash plus a 3px rust bar on the left edge.

### Dialogs
- Surface, hairline, 10px, `min(32rem, 92vw)` (wide variant `min(44rem, 94vw)`). Open from centre with fade + `scale(.96)` in 200ms; close faster (150ms). Backdrop fades to 35% black. Actions sit right-aligned in a `menu` row.

### Toggle
- A 2.3 × 1.3rem pill; off is hairline-grey with a field-rule outline; on is rust; the white knob slides 1rem. Hover turns the outline rust.

### Reading tools
Components that help the researcher follow, filter and correct the evidence. They share one grammar: hairline rows, muted ink at rest, rust only for what is selected or actionable, and a second signal beside every status colour.
- **Live readings (`letture-vive`):** inside the running-search message, the last six decisions, newest on top. A ✓ (green), ? (ochre) or – (muted) mark leads each row, then the source (ellipsised), the date (tabular) and, for relevant passages, two lines of translation in Georgia. New rows drop 4px into place over 240ms; still under the keyboard and reduced motion. A click opens the source.
- **Quota wait (`attesa-quota`):** an ochre countdown in tabular figures ("riprovo tra 12:04") with a quiet "Riprova ora" button beside it. Ochre, because waiting is not an error.
- **Passage timeline (`linea-tempo`):** one column per year (per month when the span is under three years), height = passages read; the lower, filled part is the relevant share in muted ink, the rest in hairline. A two-tone hard stop, not a gradient. A selected period gets a 2px rust inset and its filled part turns rust. Each column is a real `button` with `aria-pressed` and a full-sentence label.
- **Facet chips (`faccetta`):** series and language as pill buttons with a field-rule outline and a tabular count; pressed = hover wash, rust border, semibold.
- **Relevance pill (`pertinenza`):** in the passages table, the yes/no value is itself a small pill button; one click flips it and records a manual correction ("a mano" in the Read-by column, italic).
- **Name-form chips (`chip-forma`):** the forms found for a new name. The real checkbox stays inside, invisible but focusable; on = rust fill with a ✓ and semibold, off = surface with field-rule outline. "Ambiguous" adds a dashed underline under the form. The focused chip's detail (example in Georgia, series and years, the ambiguous box) shows below in one fixed area so the layout does not jump. Forms rejected last time sit in a closed disclosure.
- **Command palette (`dialog.comandi`):** Ctrl+K. A dialog without padding anchored 14vh from the top, a borderless 1rem input with a rust underline on focus, results grouped under label-style headings; the active row gets the hover wash and a 2px rust inset on the left. Keys shown as `kbd`.
- **Popover menus (`menu-esporta`, `consumo`):** a `details` whose panel is a surface card with a hairline and 10px radius (no shadow: they sit over quiet areas). Export drops below its link; the usage meter rises above the composer. Both grow from their anchor with `scale(.97)` over 160ms and close on Escape or a click elsewhere.
- **Answer comparison (`confronto`):** above a re-run answer, one muted line, or a bordered disclosure with "cited now / cited before" lists and the two short answers side by side in Georgia. New references in the text carry a small green "nuovo" label (text, not just colour).
- **OCR health list (`elenco-ocr`):** suspect documents as hairline rows: title as a quiet rust link, the reason in ochre after a "!", then a language select and "Rifai l'OCR".

### Interface language
The interface is written in Italian. `i18n.js` translates it into English in place, as the page renders, from a catalogue of exact phrases and patterns; it never touches what is read (answers, transcriptions, quotations, the researcher's own words), which stay inside `NON_TRADURRE`. New interface text is written in Italian as before and gets its English line in `i18n.js`. Dates use the interface locale (`LOCALE` in app.js).

## Motion

(Not a canonical DESIGN.md section; kept here because motion is a durable part of this system.)

- **Curves:** `--ease-out: cubic-bezier(0.23, 1, 0.32, 1)` for almost everything; `--ease-in-out: cubic-bezier(0.77, 0, 0.175, 1)` for symmetric moves; `--ease-drawer: cubic-bezier(0.32, 0.72, 0, 1)` for panels arriving from the side. Browser default `ease` only for plain colour changes.
- **Durations:** 120–160ms for hover colour and press; 200–280ms for arrivals of views, sections, messages and answer blocks; 260ms for the side panel; 320ms for the empty-state cascade. Exits are faster than entrances.
- **Entrances use `@starting-style`:** views rise 6px and fade in; the side panel slides 24px from the right; messages rise 8px; answer blocks cascade 40ms apart up to 240ms; disclosure content fades in.
- **Only `opacity` and `transform` animate** (plus colours and the occasional `filter: blur(2px)` on the send/stop swap). Never animate `width`, `height`, `top` or `left`.

**The Keyboard Is Still Rule.** When the last input was a key press (`html[data-tastiera]`, set by app.js), views, panels, tabs and sections appear instantly. Motion is for the pointer user's sense of place, never a delay for the keyboard user.

**The Reduced Motion Rule.** Under `prefers-reduced-motion: reduce`, nothing translates or scales and decorative loops (ripple, sweep) stop; fades and colour changes may remain.

**The Legible Start Rule.** Text that fades in starts at no less than 55% opacity so it never passes through a grey below the contrast minimum.

## Do's and Don'ts

### Do:
- **Do** read `scripts/interfaccia/app.css` `:root` before styling anything, and use its custom properties (`--sfondo`, `--superficie`, `--testo`, `--tenue`, `--bordo`, `--bordo-campo`, `--barra`, `--bolla`, `--accento`, `--accento-testo`, `--ok`, `--male`, `--attesa`, `--avviso`, `--dubbio`, `--sopra`).
- **Do** add every new colour to both the light `:root` and the dark `@media (prefers-color-scheme: dark)` block, and check text at 4.5:1 and control outlines at 3:1 in both.
- **Do** put long-form content in the 46rem centred column.
- **Do** use Georgia for read content and system-ui for controls (The Two Voices Rule).
- **Do** pair every status colour with an icon, line style or shape (The Not-Only-Colour Rule).
- **Do** give every interactive element a visible `:focus-visible` state; the global rust 2px outline with 2px offset is the default.
- **Do** keep class names and CSS comments in Italian, matching the existing code (`voce-barra`, `riquadro`, `tenue`), and write short comments that explain *why* a value was chosen.
- **Do** use inline SVG icons on the 24px grid, stroke 1.75, round caps, `currentColor`, with `aria-hidden="true"` and a label on the button.
- **Do** respect `[hidden]`, `prefers-reduced-motion` and `html[data-tastiera]` in any new animated element.
- **Do** verify visual changes in the running app (`.claude/launch.json` → `pressmark`, then open the tokenised link printed in the server log) in both light and dark.

### Don't:
- **Don't** introduce a second accent colour, gradients on surfaces, or saturated fills; rust is the only accent and it marks action.
- **Don't** use drop shadows for cards, panels or buttons; use a hairline and a tonal step (The Flat Table Rule).
- **Don't** hard-code hex values in component rules, or use pure greys (`#888`, `#ccc`); neutrals are warm.
- **Don't** use web fonts or icon fonts; the app runs offline in a desktop window and relies on system and installed fonts.
- **Don't** set UI controls in serif or answers in sans.
- **Don't** use all-caps labels, oversized hero type, or marketing-style decoration; this is a working reading room.
- **Don't** signal state with colour alone, or let a field outline drop below 3:1 contrast.
- **Don't** animate layout properties, add looping motion that isn't progress, or animate anything opened from the keyboard.
- **Don't** let content run full width on wide windows, or let the page body scroll (each column scrolls itself).
- **Don't** alter the logotype or favicon files in `assets/`; use the `-chiaro` variant on light and `-scuro` on dark via `<picture>` / `media`.
