/**
 * DRISHYAM: turning a stored confidence into something an officer can weigh.
 *
 * A bare 0.92 on screen asks the reader to invent a scale. Is that high? Higher than 0.85 by how
 * much that matters? The number is not a probability that the relationship is true — it ranks how
 * much interpretation was needed to read it off the page — and shown alone it invites exactly the
 * reading it is not.
 *
 * So the workspace shows the phrase and keeps the number beside it on hover. The record is
 * unchanged; only what a reader meets first is different. The report keeps its numeric columns
 * untouched: a court document should carry the figure, and a judge reading a filed exhibit is a
 * different reader with different needs from an officer scanning a screen.
 *
 * The mapping is deliberately coarse. Four bands, each a phrase somebody could repeat in evidence
 * without it sounding like a measurement — because it is not one.
 */

/** What the extraction layer recorded about how this was read. */
export type ObservationBasis = "direct" | "direct_visual" | "inferred" | "unknown" | null | undefined;

export type Confidence = { phrase: string; detail: string; tone: "green" | "blue" | "amber" | "neutral" };

/**
 * How firmly a source states something, in words.
 *
 * The basis is used where the record carries one, because how something was read is a better guide
 * than a score derived from it. Where there is none, the bands fall back to the number.
 */
export function readConfidence(value: number | null | undefined, basis?: ObservationBasis): Confidence {
  if (basis === "direct") {
    return {
      phrase: "stated directly",
      detail: "A source states this in words. No interpretation was needed to read it.",
      tone: "green",
    };
  }
  if (basis === "direct_visual") {
    return {
      phrase: "read from an image",
      detail: "Read off a screenshot or photograph. What the image shows is clear; what it means is not established here.",
      tone: "blue",
    };
  }
  if (basis === "inferred") {
    return {
      phrase: "inferred from context",
      detail: "No source says this outright. It was read from how the surrounding record is laid out, so check it first.",
      tone: "amber",
    };
  }

  const score = typeof value === "number" ? value : null;
  if (score === null) {
    return {
      phrase: "basis not recorded",
      detail: "Nothing was recorded about how firmly this was read. Treat it as unverified.",
      tone: "neutral",
    };
  }
  if (score >= 0.85) {
    return {
      phrase: "stated directly",
      detail: "A source states this plainly; little was interpreted in reading it.",
      tone: "green",
    };
  }
  if (score >= 0.7) {
    return {
      phrase: "stated, with some reading",
      detail: "A source supports this, but reading it required some interpretation of the record.",
      tone: "blue",
    };
  }
  if (score >= 0.5) {
    return {
      phrase: "inferred from context",
      detail: "No source says this outright. It was read from how the record is laid out.",
      tone: "amber",
    };
  }
  return {
    phrase: "weakly supported",
    detail: "Little in the record supports this. It is shown so it can be checked or dismissed, not relied on.",
    tone: "neutral",
  };
}

/** The number, for the tooltip. The record is unchanged; it is just not what the reader meets first. */
export function confidenceTitle(value: number | null | undefined, basis?: ObservationBasis): string {
  const read = readConfidence(value, basis);
  const figure = typeof value === "number" ? ` Recorded confidence ${value.toFixed(2)}.` : "";
  return `${read.detail}${figure}`;
}

export const CONFIDENCE_TONES: Record<Confidence["tone"], string> = {
  green: "border-[#c9dfcf] bg-[#f2faf3] text-[#34734b]",
  blue: "border-[#d6e2ea] bg-[#f3f8fb] text-[#365c70]",
  amber: "border-[#ead9b8] bg-[#fff8e8] text-[#97651e]",
  neutral: "border-[#dcd4ca] bg-[#f6f3ee] text-[#6f6258]",
};
