#!/usr/bin/env python3
"""W98: convert Simplified-Chinese ingredient glosses to Traditional.

The generator prompt asks for `"<qty> <unit> <english name> (<chinese name>)"`,
and the LLM emits Simplified. The site is English-first with a Chinese gloss,
and 老闆's standing rule is Traditional-only — so every CJK character in every
recipe gets normalised with OpenCC `s2t`.

Only CJK is touched: OpenCC leaves Latin, digits and punctuation untouched, so
the English recipe text is byte-identical afterwards.
"""
from __future__ import annotations

import glob
import os
import re
import sys

from opencc import OpenCC

CJK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
cc = OpenCC("s2t")


def convert_cjk_runs(text: str) -> tuple[str, int]:
    """Convert only the CJK runs, leaving everything else byte-identical."""
    changed = 0

    def repl(m: re.Match) -> str:
        nonlocal changed
        out = cc.convert(m.group(0))
        if out != m.group(0):
            changed += 1
        return out

    # Group consecutive CJK chars so OpenCC sees whole words (it needs context
    # for correct phrase conversion, e.g. 干 -> 乾/幹/干 depends on the word).
    return CJK.sub(lambda m: repl(m), ""), 0  # placeholder, replaced below


def convert_file(path: str) -> tuple[bool, int, int]:
    txt = open(path, encoding="utf-8").read()
    # Split CJK-containing runs (allow CJK + the punctuation that sits between them)
    run = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\u3000-\u303f\uff00-\uffef]+")
    n_runs = 0
    n_changed = 0

    def repl(m: re.Match) -> str:
        nonlocal n_runs, n_changed
        n_runs += 1
        out = cc.convert(m.group(0))
        if out != m.group(0):
            n_changed += 1
        return out

    new = run.sub(repl, txt)
    if new != txt:
        open(path, "w", encoding="utf-8").write(new)
        return True, n_runs, n_changed
    return False, n_runs, n_changed


def main() -> None:
    # NOTE: `--apply` is a flag, not a path — filter flags out before taking argv[0]
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = positional[0] if positional else "/home/hermes/healthy-recipes-site/_recipes"
    dry = "--apply" not in sys.argv
    files = sorted(glob.glob(os.path.join(root, "*.md")))
    touched = 0
    total_runs = 0

    for f in files:
        if dry:
            txt = open(f, encoding="utf-8").read()
            run = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\u3000-\u303f\uff00-\uffef]+")
            runs = run.findall(txt)
            if not runs:
                continue
            changed = [r for r in runs if cc.convert(r) != r]
            if changed:
                touched += 1
                total_runs += len(changed)
                if touched <= 6:
                    ex = changed[:4]
                    print(f"  {os.path.basename(f)[:52]:52s} {len(changed):3d} runs  e.g. {ex}")
        else:
            did, nruns, nch = convert_file(f)
            if did:
                touched += 1
                total_runs += nch

    label = "WOULD CHANGE" if dry else "CHANGED"
    print(f"\n{label}: {touched} / {len(files)} recipes, {total_runs} CJK runs")
    if dry:
        print("(dry run — pass --apply to write)")


if __name__ == "__main__":
    main()
