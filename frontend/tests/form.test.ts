import { describe, expect, it } from "vitest";
import {
  normalizePreferenceNotes,
  preferenceNoteCodePointCount,
} from "@/lib/form";

describe("preference note normalization", () => {
  it("matches the backend normalization order and Unicode counting", () => {
    expect(normalizePreferenceNotes("  Cafe\u0301\n\tvisit  ")).toBe(
      "Café visit",
    );
    expect(normalizePreferenceNotes("\u2003calm\u2003\u2003trip\u2003")).toBe(
      "calm trip",
    );
    expect(preferenceNoteCodePointCount("e\u0301".repeat(300))).toBe(300);
    expect(normalizePreferenceNotes("😀".repeat(300))).toBe("😀".repeat(300));
  });

  it("rejects forbidden characters and over-limit values", () => {
    expect(() => normalizePreferenceNotes("safe\u202etext")).toThrow(
      "unsupported characters",
    );
    expect(() => normalizePreferenceNotes("safe\ud800text")).toThrow(
      "unsupported characters",
    );
    expect(() => normalizePreferenceNotes("x".repeat(301))).toThrow(
      "300 characters or fewer",
    );
  });

  it("does not treat the non-whitespace byte-order mark as whitespace", () => {
    expect(normalizePreferenceNotes("calm\ufefftrip")).toBe("calm\ufefftrip");
    expect(normalizePreferenceNotes("\ufeffcalm\ufeff")).toBe(
      "\ufeffcalm\ufeff",
    );
  });
});
