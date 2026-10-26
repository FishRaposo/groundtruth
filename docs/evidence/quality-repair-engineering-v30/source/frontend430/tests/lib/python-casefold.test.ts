import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";
import { pythonCasefold, pythonCasefoldProfile } from "@/lib/python-casefold";

describe("pinned Python 3.12.14 Unicode 15.0.0 full casefold", () => {
  // Catches missing mapping entries, expansions, astral handling and accidental JS casing.
  // Expected hash comes independently from delivery Python over every Unicode scalar.
  it("matches the independent Python oracle across every Unicode scalar", () => {
    const digest = createHash("sha256");
    for (let start = 0; start <= 0x10ffff; start += 4096) {
      const points: string[] = [];
      for (let cp = start; cp < start + 4096 && cp <= 0x10ffff; cp++) {
        if (cp < 0xd800 || cp > 0xdfff) points.push(String.fromCodePoint(cp), "\0");
      }
      digest.update(pythonCasefold(points.join("")), "utf8");
    }
    expect(digest.digest("hex")).toBe("2af944b6cb24e3be0307122af2e8a2b9396941bc32d0e82fdb3fac4f96327a83");
    expect(pythonCasefoldProfile.unicode).toBe("15.0.0");
  });

  it.each([
    ["Straße ẞ", "strasse ss"], ["Σσς", "σσσ"], ["ﬃﬀﬅ", "ffiffst"],
    ["Iİıi", "ii\u0307ıi"], ["𐐀𐐨", "𐐨𐐨"], ["ꭰᎠ", "ᎠᎠ"],
    ["Ａ K", "ａ k"], ["é e\u0301", "é e\u0301"],
    ["\u0000\ud7ff\ue000\uffff\u{10000}\u{10ffff}", "\u0000\ud7ff\ue000\uffff\u{10000}\u{10ffff}"],
    ["\ud800A\udfff", "\ud800a\udfff"], ["\u0085\u001c\ufeff\u200b", "\u0085\u001c\ufeff\u200b"],
  ])("folds %j with Python literals and no normalization", (source, expected) => {
    expect(pythonCasefold(source)).toBe(expected);
  });
});
