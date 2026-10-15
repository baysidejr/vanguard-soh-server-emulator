"""Generate server/content/ability_names.json: proper spelling for class ability names.

The server names class abilities from the client's internal tags (class_abilities.display_name),
and many tags have no word breaks ("Lightningstrike I"). The crowdsourced archive lists the same
abilities with their real names. A name is taken only when it matches the tag name exactly once
spaces, punctuation and case are ignored, so this can only re-space and re-punctuate, never rename.
Tag names the archive doesn't list get a second pass: each run-together word (one that is not a
known word itself) is split into known words, picking the most likely split by word frequency in
the client's VGClient.int and the archive text ("Formofthespiritdragon" -> "Form of the Spirit
Dragon"). A word is left alone when any piece would be unknown. Those entries have the source
"word split".
Output: {tag name: {"name": proper name, "source": url}}. Run from the repository root:

    python tools/ability_names.py
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))
import class_abilities  # noqa: E402
import races_classes  # noqa: E402

OUT = os.path.join(ROOT, "server", "content", "ability_names.json")
RANK = re.compile(r"\s+([IVX]+)$")


def key(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def split_rank(name):
    m = RANK.search(name.strip())
    return (name[:m.start()].strip(), m.group(1)) if m else (name.strip(), "")


def archive_names():
    """base-name key -> {spelling: source url} from medium/high confidence ability records."""
    found = {}
    for fn in sorted(glob.glob(os.path.join(ROOT, "crowdsourced", "raw", "*", "ability.jsonl"))):
        with open(fn, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                if r.get("confidence") not in ("medium", "high") or not r.get("name"):
                    continue
                base, _ = split_rank(r["name"])
                url = (r.get("sources") or [{}])[0].get("url", "")
                found.setdefault(key(base), {}).setdefault(base, url)
    return found


SPLIT_SOURCE = "word split"
MIN_COUNT = 3                    # a word counts as known at this many occurrences
PIECE_COUNT = 20                 # a split piece must be this common (or a minor word) ...
PIECE_LEN = 3                    # ... and this long: no "Im Pact" or "Cl One"
MINOR = {"of", "the", "and", "a", "an", "to", "in", "on", "for", "with", "from", "at", "by"}


def vocabulary():
    """word -> count from the client's text (VGClient.int) and the archive's records."""
    counts = {}
    texts = []
    for fn in glob.glob(os.path.join(ROOT, "bin", "*.int")):
        b = open(fn, "rb").read()
        texts.append(b.decode("utf-16-le", "ignore") if b[:2] == b"\xff\xfe" else b.decode("latin-1"))
    for t in texts:
        for w in re.findall(r"[A-Za-z]+", t):
            counts[w.lower()] = counts.get(w.lower(), 0) + 1
    for fn in glob.glob(os.path.join(ROOT, "crowdsourced", "raw", "*", "*.jsonl")):
        with open(fn, encoding="utf-8", errors="ignore") as f:
            for line in f:
                for w in re.findall(r"[A-Za-z]+", line):
                    counts[w.lower()] = counts.get(w.lower(), 0) + 1
    return {w: n for w, n in counts.items() if n >= MIN_COUNT and (len(w) > 1 or w == "a")}


def split_word(word, vocab, total):
    """The most likely split of a lower-case run-together word into vocabulary words (fewest
    unlikely pieces), or None when it can't be split entirely into known words."""
    import math
    best = [(0.0, [])] + [None] * len(word)
    for i in range(1, len(word) + 1):
        for j in range(max(0, i - 20), i):
            piece = word[j:i]
            if best[j] is None or piece not in vocab or (piece not in MINOR and (
                    len(piece) < PIECE_LEN or vocab[piece] < PIECE_COUNT)):
                continue
            cost = best[j][0] - math.log(vocab[word[j:i]] / total) + 4.0   # +4: prefer fewer pieces
            if best[i] is None or cost < best[i][0]:
                best[i] = (cost, best[j][1] + [word[j:i]])
    return best[-1][1] if best[-1] and len(best[-1][1]) > 1 else None


def respace(name, vocab, total):
    """Split the run-together words of a tag name; None when nothing changed."""
    base, rank = split_rank(name)
    words, changed = [], False
    for w in base.split():
        low = w.lower()
        parts = None if low in vocab or not low.isalpha() or len(low) < 6 else split_word(low, vocab, total)
        if parts:
            changed = True
            for p in parts:
                words.append(p if (p in MINOR and words) else p.capitalize())
        else:
            words.append(w)
    return f"{' '.join(words)} {rank}".strip() if changed else None


def main():
    archive = archive_names()
    out, ambiguous = {}, []
    tags = set()
    for klass in races_classes.ADVENTURING_CLASSES:
        for _aid, tag in class_abilities.package_abilities(ROOT, class_abilities.CLASS_PREFIX.get(klass, "")) \
                if class_abilities.CLASS_PREFIX.get(klass) else []:
            tags.add(class_abilities.raw_display_name(tag))
    for tag_name in sorted(tags):
        base, rank = split_rank(tag_name)
        spellings = archive.get(key(base), {})
        if len(spellings) > 1:
            ambiguous.append((tag_name, sorted(spellings)))
            continue
        if len(spellings) == 1:
            (proper, url), = spellings.items()
            full = f"{proper} {rank}".strip()
            if full != tag_name:
                out[tag_name] = {"name": full, "source": url}
    vocab = vocabulary()
    total = sum(vocab.values())
    split = 0
    for tag_name in sorted(tags):
        if tag_name in out or len(archive.get(key(split_rank(tag_name)[0]), {})) > 1:
            continue
        full = respace(tag_name, vocab, total)
        if full:
            out[tag_name] = {"name": full, "source": SPLIT_SOURCE}
            split += 1
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"_comment": "Generated by tools/ability_names.py from crowdsourced ability records: "
                               "re-spaced class ability names (tag name -> proper name). Source \"word split\": "
                               "split into known words by the tool, not seen spelled that way. Do not edit by hand."}
                  | dict(sorted(out.items())), f, indent=2, ensure_ascii=False)
    print(f"tag names: {len(tags)}; re-spaced: {len(out)} ({split} by word split); ambiguous: {len(ambiguous)}")
    for t, s in ambiguous[:8]:
        print(f"  ambiguous: {t}: {s}")


if __name__ == "__main__":
    main()
