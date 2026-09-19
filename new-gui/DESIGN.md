---
name: Audiophile Reference Console
colors:
  surface: '#151311'
  surface-dim: '#151311'
  surface-bright: '#3b3936'
  surface-container-lowest: '#0f0e0c'
  surface-container-low: '#1d1b19'
  surface-container: '#211f1d'
  surface-container-high: '#2c2a27'
  surface-container-highest: '#373432'
  on-surface: '#e7e1de'
  on-surface-variant: '#d0c5af'
  inverse-surface: '#e7e1de'
  inverse-on-surface: '#32302e'
  outline: '#99907c'
  outline-variant: '#4d4635'
  surface-tint: '#e9c349'
  primary: '#f2ca50'
  on-primary: '#3c2f00'
  primary-container: '#d4af37'
  on-primary-container: '#554300'
  inverse-primary: '#735c00'
  secondary: '#43f3a7'
  on-secondary: '#003822'
  secondary-container: '#00d68d'
  on-secondary-container: '#005736'
  tertiary: '#ffbfb2'
  on-tertiary: '#640d00'
  tertiary-container: '#ff9781'
  on-tertiary-container: '#8a1500'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#ffe088'
  primary-fixed-dim: '#e9c349'
  on-primary-fixed: '#241a00'
  on-primary-fixed-variant: '#574500'
  secondary-fixed: '#52ffb1'
  secondary-fixed-dim: '#25e197'
  on-secondary-fixed: '#002112'
  on-secondary-fixed-variant: '#005233'
  tertiary-fixed: '#ffdad3'
  tertiary-fixed-dim: '#ffb4a4'
  on-tertiary-fixed: '#3e0500'
  on-tertiary-fixed-variant: '#8d1600'
  background: '#151311'
  on-background: '#e7e1de'
  surface-variant: '#373432'
typography:
  headline-lg:
    fontFamily: Space Grotesk
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-lg-mobile:
    fontFamily: Space Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Space Grotesk
    fontSize: 22px
    fontWeight: '500'
    lineHeight: 28px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Space Grotesk
    fontSize: 18px
    fontWeight: '500'
    lineHeight: 24px
    letterSpacing: 0em
  body-lg:
    fontFamily: Hanken Grotesk
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: 0em
  body-md:
    fontFamily: Hanken Grotesk
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: 0.01em
  body-sm:
    fontFamily: Hanken Grotesk
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0.01em
  label-lg:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: 0.08em
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.12em
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 9px
    fontWeight: '600'
    lineHeight: 12px
    letterSpacing: 0.16em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1.5rem
  gutter-mobile: 0.75rem
  margin: 2.5rem
  margin-mobile: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
---

## Brand & Style

This design system translates the peerless sensory prestige of 1970s–1980s Japanese and Swiss reference audio equipment into an interactive digital interface. It targets discerning audio engineers, master recordists, and dedicated audiophiles who expect software to embody the weight, intentionality, and mechanical permanence of legendary five-figure studio consoles and integrated amplifiers.

The emotional signature is one of deliberate calibration, precision acoustics, and tactile heft. Interaction evokes cold brushed metals, oiled American dark oak side panels, damped mechanical resistance, and the optical glow of vacuum-fluorescent displays (VFD) and phosphor-lit meter bridges.

The overarching design style fuses **Tactile / Skeuomorphic Realism** with **Modern Industrial Precision**. Components are treated not as transient web layers, but as milled aluminum faceplates, recessed meter enclosures, bevel-cut acrylic viewing windows, and knurled controls built to sub-millimeter tolerances.

## Colors

The chromatic palette mirrors laboratory-grade acoustic machinery:

- **Primary (`#D4AF37` / Champagne Brass & Amber Glow):** Evokes champagne anodized aluminum accents, backlit incandescent meter needles, and warm valve-filament radiation. Used for primary control indicators, master volume highlights, and vacuum tube biasing states.
- **Secondary (`#2EE69B` / Phosphor VFD Green):** Emulates classic Matsushita and Futaba vacuum-fluorescent displays and nominal audio levels (under -3 dB). Used for active stream sample rates, balanced signal health, and nominal meter sweep ranges.
- **Tertiary (`#FF5938` / Peak Red):** The unmistakable warning beacon of clipping, transient overload, and tape saturation (+3 dB to +6 dB). Used strictly for clipping warnings, mute engagements, and thermal alarms.
- **Neutral (`#211F1D` / Aged Bog Oak & Anodized Gunmetal):** A warm, deep obsidian base reflecting oiled solid oak cabinet housings and heavy cast-zinc internal chassis shielding.

### Auxiliary Surface Tones
- **Brushed Silver / Champagne Faceplate:** Linear gradients traversing `#E2DFD8`, `#CBC6B8`, and `#ABA496` with directional linear-gradient highlights simulating 180-grit horizontal satin brushing.
- **VFD / OLED Glass Base:** Deep optical pitch `#0A0D0B` with an illuminated dot-matrix micro-screen door effect.

## Typography

Typography functions as mechanical labeling stamped, milled, and silk-screened directly onto metal alloy panels or etched behind optical acrylic.

- **Display & Section Headers (`Space Grotesk`):** Balanced, clean architectural geometry that mimics Swiss industrial typesetting of late 20th-century monitor systems. Headlines are set in high-contrast silver `#E2DFD8` or silk-screened matte white with deep letter kerning.
- **Parametric Values & Telemetry (`JetBrains Mono`):** Fixed-width clarity for dynamic decibel readings, sample rates (e.g., `192.0 kHz / 32-bit Float`), harmonic distortion ratios, and step attenuation indices. Rendered in full uppercase with expanded tracking for small labels to reflect chassis stamping.
- **Interface Copy & Descriptions (`Hanken Grotesk`):** Modern utilitarian sans-serif offering neutral, effortless readability alongside complex tactile controls.

All milled labels employ a crisp dual-shadow technique: an inner 1px bottom highlight (`rgba(255, 255, 255, 0.25)`) and a 1px top drop shadow (`rgba(0, 0, 0, 0.8)`) creating an authentic stamped-chassis deboss effect.

## Layout & Spacing

The layout model adapts between two dedicated operating postures:
1. **Desktop / Studio Console (12-column rigid rackmount grid):** A horizontal dual-section split console. The left module hosts rack units, input routing matrix, and secondary rotary pots. The right module houses dual backlit ballistic VU meters, OLED waveform visualizer, and master stepped attenuator.
2. **Mobile / Handheld Remote (Single-column vertical stack):** Transforms into an ergonomic remote terminal. Essential meter readouts anchor the top viewport, rotary dials adapt into multi-touch orbital wheels, and secondary switches nest into accessible thumb-driven drawers.

Spacing adheres strictly to an 8px base increment (`0.5rem`), referencing standard 19-inch rack unit (1RU = 44.45mm) modularity. Clear vertical separation prevents accidental finger or cursor trips between critical mechanical controls. Outer container margins simulate real oak side-cheek bezels flanking the aluminum instrument panel.

## Elevation & Depth

Visual depth is achieved through physical material simulation:

- **Level 0 (External Enclosure):** Deep walnut/dark oak wood grain chassis with rich edge vignettes, warm low-angle shadows, and recessed screw hardware.
- **Level 1 (The Milled Aluminum Faceplate):** Raised 3mm above the chassis floor via an inset rim highlight (`1px solid rgba(255, 255, 255, 0.4)`) and heavy drop perimeter shadow (`0 20px 40px -10px rgba(0, 0, 0, 0.85)`).
- **Level 2 (Recessed Meter Bays & VFD Windows):** Sunken apertures with deep inner bevels (`box-shadow: inset 2px 3px 6px rgba(0, 0, 0, 0.95), inset -1px -1px 2px rgba(255, 255, 255, 0.15)`), tinted behind dark smoked polycarbonate sheets.
- **Level 3 (Machined Control Hardware):** Knurled aluminum knobs and bat switches that cast crisp directional drop shadows (`0 8px 16px rgba(0, 0, 0, 0.6)`) and reflect radial highlights corresponding to rotary positions.
- **Light Emissions:** OLED/VFD digits and VU meter lamps cast local diffusion glows (`filter: drop-shadow(0 0 6px rgba(46, 230, 155, 0.65))` for phosphor green and `drop-shadow(0 0 8px rgba(212, 175, 55, 0.5))` for warm incandescent amber).

## Shapes

The design system maintains strict mechanical rectilinearity (`roundedness: 1`). 

- Instrument faceplates, rack housings, and inset screen windows utilize ultra-tight 4px (`0.25rem`) corners, replicating precision CNC waterjet and end-mill aluminum machining.
- Toggle switch batons and rotary knobs break the rectangular language with circular geometry (`rounded-full`), textured with concentric dial grooves and high-density diamond knurling patterns.
- Push buttons feature subtly radiused corners (`2px`) with chamfered, faceted outer frames.

## Components

### 1. Rotary Dials & Knurled Knobs
- **Construction:** Concentric-machined silver-aluminum discs with radial gradient lighting. Circumference finished with high-contrast diamond knurl texture.
- **Indicator:** An engraved, painted indicator line (Champagne `#D4AF37`) running from perimeter to collar.
- **Interaction:** Drag or wheel control with subtle detent stops and optional precision fine-tune mode (Shift + Drag). A subtle mechanical click haptic feedback fires on mobile.

### 2. Dual Ballistic VU Meters & LED Ladders
- **Analog Mode:** Warm amber backlit gauge (`#F8E8C8` dial plate under warm `#D4AF37` bulb glow) with logarithmic dB scale (-20 to +5 dB). Needle moves with authentic ballistic rise time (300ms) and natural overshoot damping.
- **LED Ladder Mode:** Segmented vertical bars of 24 discretely framed rectangles: green from -∞ to -3 dB, amber from -2 dB to 0 dB, and vivid red above +1 dB with decaying peak-hold segment.

### 3. Mechanical Toggle Switches
- **Construction:** Solid nickel-plated toggle bat with spring-loaded physical states.
- **Frame:** Recessed rectangular trench with hex-nut mounting collar.
- **Feedback:** Positive throw animation between On/Off/Bypass states with sharp audible click trigger.

### 4. OLED / VFD Status Displays
- **Window:** High-contrast pitch-black base with 5% scanline overlay and glass reflection gradient.
- **Digits:** Phosphor green (`#2EE69B`) or amber gold (`#D4AF37`) glowing numeric display with soft outer bloom. Displays bit-depth, clock source, and filter profile.

### 5. Stepped Push-Buttons (Illuminated)
- **Construction:** Translucent rectangular buttons seated in satin silver bezels.
- **State:** Unlit state is soft frosted smoke; active state is intensely backlit from within by an amber or green LED accompanied by a 1px physical inward depression.

### 6. Cards & Channel Strips
- **Modular Bays:** Each card represents an independent discrete audio module (Preamp, Parametric EQ, Tube Compressor, Output Attenuator) framed with Allen-head corner screws and silver panel divide seams.