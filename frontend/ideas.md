# DRISHYAM — Reference-Led Design Direction

## Ground-Truth Reference

This implementation follows the supplied Drishyam reference screens as the ground-truth visual specification. The experience is a premium digital investigation and cybercrime evidence intelligence platform whose central promise is converting fragmented digital artefacts into an auditable story. The supplied physical-evidence imagery is used as an art-directed asset library: objects remain peripheral and compositional while the product interface and content hold priority.

## Chosen Design Philosophy — The Evidence Archive

### Design Movement

Editorial legal-tech realism: an investigative desk translated into a precise, contemporary digital platform. It blends Indian judicial cues, physical evidence archive materiality, and calm intelligence-software patterns.

### Core Principles

1. **Evidence before spectacle.** Content and interface signals remain immediately legible; decorative artefacts enrich context but never obscure action.
2. **Physical-to-digital continuity.** Paper, case-file, red-string, stamp, and forensic references frame clean data cards, timelines, and graph surfaces.
3. **Editorial asymmetry.** Spacious off-centre compositions, clipped paper fragments, and anchored side objects replace generic centred SaaS sections.
4. **Auditable calm.** Warm light space, deliberate hierarchy, restrained animation, and sober data treatment communicate care, security, and authority.

### Color Philosophy

An **ivory archive** foundation evokes preserved legal records and makes the experience feel human rather than sterile. **Graphite-black** typography creates the authority of an official case file. A single ownable **case-file burgundy (#7F1D1D)** carries legal emphasis, evidence paths, active states, and confidence signals. Muted brass and parchment tones add a physical archive depth without weakening clarity.

### Layout Paradigm

The page is a sequence of editorial case sheets. Each section uses an asymmetric content field with a supporting evidence rail or corner composition. Product UI is rendered as layered working surfaces—timelines, extraction cards, entity nodes, and report papers—rather than a repeated centred-grid pattern.

### Signature Elements

1. **Burgundy evidence threads:** fine connector lines and pins that visually bridge otherwise separate data artefacts.
2. **Case-file annotations:** miniature labels, hashes, dates, and status stamps that add forensic texture.
3. **Peripheral physical evidence:** selectively cropped case files, court architecture, payments, locks, maps, and reports that appear at section edges.

### Interaction Philosophy

Every interaction should feel like opening, inspecting, or pinning a case artefact. The workspace preview reveals focused panels rather than producing disorienting app-like navigation. Calls to action move the visitor toward the workspace or scroll to a relevant proof section.

### Animation

Use a short, intentional reveal vocabulary: evidence cards rise 10px and fade in, connector lines appear with a contained draw effect, and graph nodes sharpen on hover. Motion stays under 300ms, uses a crisp ease-out, and yields to `prefers-reduced-motion`. Decorative evidence objects stay still, conveying archival weight.

### Typography System

**DM Serif Display** is used for high-stakes headlines, narrative case statements, and legal-report titles. **Manrope** provides the compact, dependable interface voice for navigation, metadata, cards, and controls. Headlines are high-contrast and editorial; metadata is tracked in all-caps, with compact mono-styled hashes and identifiers.

### Brand Essence

**DRISHYAM is the evidence intelligence workspace for Indian cybercrime teams who need every lead to become a traceable, court-ready investigation.**

Personality: **authoritative, meticulous, composed.**

### Brand Voice

Headlines are firm and evidence-led; CTAs are specific, operational, and concise. Avoid vague software claims, casual slang, and generic welcome copy.

Example lines:

> “The evidence exists. The story doesn’t—until you trace it.”

> “Open the case workspace.”

### Wordmark & Logo

The mark is a monogram built from two vertical evidence rails and a central red pin: a structured abstract **D** that also suggests a case-file clasp and a connected investigation path. It is paired with a sharply letter-spaced DRISHYAM wordmark.

### Signature Brand Color

**Case-file Burgundy — #7F1D1D.**

## Product Vocabulary

The visible platform content uses the NyayTrace blueprint as source of truth: secure case creation, evidence validation and SHA-256 hashing, OCR and extraction, entity normalization, timeline reconstruction, entity graphs, transaction trails, reviewable alerts, evidence vault records, and court-ready report generation. The demo narrative revolves around a fake job offer, a phishing link, and UPI payments—presented strictly as investigation leads for human review, not automated accusation.

## Style Decisions

Desktop and mobile QA confirmed that the chosen Evidence Archive system maintains hierarchy in both contexts: the editorial narrative and interface cards stay dominant, while the physical evidence objects remain secondary and peripheral. The mobile composition intentionally collapses long sections into a readable single-column case-file sequence without hiding the primary actions or workspace controls.

The separate workspace extends the Evidence Archive rather than becoming a generic dark SOC interface. Its dominant foundation is ivory/parchment archive material, while graphite surfaces remain focused analytical insets. Every key workspace context has a DRISHYAM brand anchor, and **Case-file Burgundy** functions as an evidence-path system through pins, active states, threads, trace links, and stamps.

Workspace metrics are never anonymous dashboard tiles. They are presented as compact investigation artefacts—such as a vault receipt, hash manifest, timeline strip, graph board, money ledger, alert docket, or review receipt—connected through restrained burgundy pins and threads. This preserves a dense command-center working surface without losing the archival chain-of-custody character.
