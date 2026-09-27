"""Programmatic task synthesis: generate (start, target) pairs from transform
templates, with programmatically-built reference solutions. Every generated
task is verified by construction — the reference is replayed through the real
harness and only exact matches are kept. This makes the task pool
contamination-proof and effectively infinite.
"""
import json
import random

from harness import run_vim
from tasksets import DEFAULT_SYNTH_TASKS

WORDS = ("apple banana cherry date elderberry fig grape honeydew kiwi lemon mango "
         "nectarine orange papaya quince raspberry strawberry tangerine ugli "
         "vanilla melon peach plum pear apricot coconut lime olive").split()
MARKER = "ZZZ"
SEED = 20260926


def _lines(rng, n, words=True):
    if words:
        return [rng.choice(WORDS) for _ in range(n)]
    return [" ".join(rng.sample(WORDS, 3)) for _ in range(n)]


def t_delete_line(rng, i):
    n = rng.randint(4, 8)
    k = rng.randint(1, n)
    start = _lines(rng, n)
    target = start[:k - 1] + start[k:]
    return dict(tier=1, title=f"Delete line {k}",
                instruction=f"Delete line {k} of the file.",
                start="\n".join(start) + "\n", target="\n".join(target) + "\n",
                reference=f"{k}Gdd:wq<CR>")


def t_delete_range(rng, i):
    n = rng.randint(5, 9)
    a = rng.randint(1, n - 2)
    b = rng.randint(a + 1, min(a + 3, n))
    start = _lines(rng, n)
    target = start[:a - 1] + start[b:]
    return dict(tier=1, title=f"Delete lines {a}-{b}",
                instruction=f"Delete lines {a} through {b} of the file.",
                start="\n".join(start) + "\n", target="\n".join(target) + "\n",
                reference=f"{a}G{b - a + 1}dd:wq<CR>")


def t_swap_adjacent(rng, i):
    n = rng.randint(3, 7)
    k = rng.randint(1, n - 1)
    start = _lines(rng, n)
    target = start[:]
    target[k - 1], target[k] = target[k], target[k - 1]
    return dict(tier=1, title=f"Swap lines {k} and {k + 1}",
                instruction=f"Swap lines {k} and {k + 1}.",
                start="\n".join(start) + "\n", target="\n".join(target) + "\n",
                reference=f"{k}Gddp:wq<CR>")


def t_reverse(rng, i):
    n = rng.randint(3, 7)
    start = _lines(rng, n)
    target = start[::-1]
    return dict(tier=1, title="Reverse all lines",
                instruction="Reverse the order of all lines in the file.",
                start="\n".join(start) + "\n", target="\n".join(target) + "\n",
                reference=":g/^/m0<CR>:wq<CR>")


def t_yank_to_end(rng, i):
    n = rng.randint(3, 6)
    k = rng.randint(1, n)
    start = _lines(rng, n)
    target = start + [start[k - 1]]
    return dict(tier=1, title=f"Copy line {k} to the end",
                instruction=f"Copy line {k} and paste the copy after the last line.",
                start="\n".join(start) + "\n", target="\n".join(target) + "\n",
                reference=f"{k}GyyGp:wq<CR>")


def t_change_word(rng, i):
    n = rng.randint(3, 6)
    k = rng.randint(1, n)
    start = _lines(rng, n)
    new = rng.choice([w for w in WORDS if w != start[k - 1]])
    target = start[:]
    target[k - 1] = new
    return dict(tier=1, title=f"Change the word on line {k}",
                instruction=f"On line {k}, replace the word with {new}.",
                start="\n".join(start) + "\n", target="\n".join(target) + "\n",
                reference=f"{k}Gcw{new}<Esc>:wq<CR>")


def t_join_all(rng, i):
    n = rng.randint(3, 5)
    start = _lines(rng, n)
    target = [" ".join(start)]
    return dict(tier=1, title="Join all lines",
                instruction="Join all lines into a single line, separated by single spaces.",
                start="\n".join(start) + "\n", target="\n".join(target) + "\n",
                reference=":%j<CR>:wq<CR>")


def t_uppercase_line(rng, i):
    n = rng.randint(3, 6)
    k = rng.randint(1, n)
    start = _lines(rng, n)
    target = start[:]
    target[k - 1] = target[k - 1].upper()
    return dict(tier=2, title=f"Uppercase line {k}",
                instruction=f"Convert line {k} to uppercase.",
                start="\n".join(start) + "\n", target="\n".join(target) + "\n",
                reference=f"{k}GgUU:wq<CR>")


def t_append_semi(rng, i):
    n = rng.randint(3, 6)
    start = _lines(rng, n)
    target = [s + ";" for s in start]
    return dict(tier=2, title="Append semicolon to each line",
                instruction="Append a semicolon to the end of every line.",
                start="\n".join(start) + "\n", target="\n".join(target) + "\n",
                reference=":%s/$/;/<CR>:wq<CR>")


def t_comment(rng, i):
    n = rng.randint(3, 6)
    start = _lines(rng, n)
    target = ["# " + s for s in start]
    return dict(tier=2, title="Comment every line",
                instruction="Prefix every line with '# ' (hash + space).",
                start="\n".join(start) + "\n", target="\n".join(target) + "\n",
                reference=":%s/^/# /<CR>:wq<CR>")


def t_sort(rng, i):
    n = rng.randint(4, 8)
    start = rng.sample(WORDS, n)
    target = sorted(start)
    return dict(tier=3, title="Sort lines alphabetically",
                instruction="Sort all lines alphabetically.",
                start="\n".join(start) + "\n", target="\n".join(target) + "\n",
                reference=":sort<CR>:wq<CR>")


def t_sort_unique(rng, i):
    n = rng.randint(5, 8)
    pool = rng.sample(WORDS, n - 2)
    start = pool + rng.sample(pool, 2)
    rng.shuffle(start)
    target = sorted(set(start))
    return dict(tier=3, title="Sort lines, removing duplicates",
                instruction="Sort all lines alphabetically and remove duplicate lines.",
                start="\n".join(start) + "\n", target="\n".join(target) + "\n",
                reference=":sort u<CR>:wq<CR>")


def t_substitute(rng, i):
    n = rng.randint(3, 6)
    w1, w2 = rng.sample(WORDS, 2)
    start = []
    for _ in range(n):
        words = _lines(rng, rng.randint(2, 4))
        if rng.random() < 0.7:
            words[rng.randrange(len(words))] = w1
        start.append(" ".join(words))
    if not any(w1 in s.split() for s in start):
        start[0] = w1 + " " + start[0]
    target = [s.replace(w1, w2) for s in start]
    return dict(tier=3, title=f"Replace '{w1}' with '{w2}'",
                instruction=f"Replace every occurrence of '{w1}' with '{w2}' in the whole file.",
                start="\n".join(start) + "\n", target="\n".join(target) + "\n",
                reference=f":%s/{w1}/{w2}/g<CR>:wq<CR>")


def t_strip_tws(rng, i):
    n = rng.randint(3, 6)
    start, target = [], []
    for _ in range(n):
        w = rng.choice(WORDS)
        pad = "".join(rng.choice([" ", " ", "\t"]) for _ in range(rng.randint(0, 3)))
        start.append(w + pad)
        target.append(w)
    if all(s == t for s, t in zip(start, target)):
        start[0] += "  "
    return dict(tier=3, title="Strip trailing whitespace",
                instruction="Remove all trailing whitespace (spaces and tabs) from every line.",
                start="\n".join(start) + "\n", target="\n".join(target) + "\n",
                reference=r":%s/\s\+$//<CR>:wq<CR>")


def t_delete_matching(rng, i):
    n = rng.randint(4, 7)
    start, target = [], []
    for _ in range(n):
        w = rng.choice(WORDS)
        if rng.random() < 0.5:
            start.append(f"{w} {MARKER} {rng.choice(WORDS)}")
        else:
            start.append(w)
            target.append(w)
    if not target or len(target) == len(start):
        start.append(MARKER + " hit")
    target = [s for s in start if MARKER not in s]
    return dict(tier=3, title=f"Delete lines containing '{MARKER}'",
                instruction=f"Delete every line that contains '{MARKER}'.",
                start="\n".join(start) + "\n", target="\n".join(target) + "\n",
                reference=f":%s/.*{MARKER}.*//<CR>:g/^$/d<CR>:wq<CR>")


def t_delete_blanks(rng, i):
    n = rng.randint(4, 7)
    start = []
    for _ in range(n):
        start.append(rng.choice(WORDS) if rng.random() < 0.7 else "")
    if not any(s == "" for s in start):
        start.insert(rng.randrange(len(start)), "")
    target = [s for s in start if s != ""]
    return dict(tier=3, title="Delete blank lines",
                instruction="Delete all blank lines.",
                start="\n".join(start) + "\n", target="\n".join(target) + "\n",
                reference=":g/^$/d<CR>:wq<CR>")


def t_move_range_top(rng, i):
    n = rng.randint(5, 8)
    a = rng.randint(2, n - 2)
    b = rng.randint(a + 1, min(a + 2, n))
    start = _lines(rng, n)
    target = start[a - 1:b] + start[:a - 1] + start[b:]
    return dict(tier=3, title=f"Move lines {a}-{b} to the top",
                instruction=f"Move lines {a} through {b} to the top of the file, preserving order.",
                start="\n".join(start) + "\n", target="\n".join(target) + "\n",
                reference=f":{a},{b}m0<CR>:wq<CR>")


def t_comment_strip(rng, i):
    n = rng.randint(3, 5)
    start, target = [], []
    for _ in range(n):
        w = rng.choice(WORDS)
        pad = " " * rng.randint(0, 2)
        start.append(w + pad)
        target.append("# " + w)
    return dict(tier=4, title="Strip trailing whitespace and comment",
                instruction="Remove trailing whitespace from every line AND prefix every line with '# '.",
                start="\n".join(start) + "\n", target="\n".join(target) + "\n",
                reference=r":%s/\s\+$//<CR>:%s/^/# /<CR>:wq<CR>")


TEMPLATES = [
    t_delete_line, t_delete_range, t_swap_adjacent, t_reverse, t_yank_to_end,
    t_change_word, t_join_all, t_uppercase_line, t_append_semi, t_comment,
    t_sort, t_sort_unique, t_substitute, t_strip_tws, t_delete_matching,
    t_delete_blanks, t_move_range_top, t_comment_strip,
]


def generate(count_per_template=4, seed=SEED):
    rng = random.Random(seed)
    tasks, seen = [], set()
    idx = 0
    for tmpl in TEMPLATES:
        made = 0
        attempts = 0
        while made < count_per_template and attempts < count_per_template * 10:
            attempts += 1
            t = tmpl(rng, idx)
            key = (t["start"], t["target"])
            if key in seen or t["start"] == t["target"]:
                continue
            final, err = run_vim(t["start"], t["reference"])
            if err is not None or final != t["target"]:
                continue
            seen.add(key)
            t["id"] = f"syn-{tmpl.__name__[2:]}-{idx:03d}"
            idx += 1
            tasks.append(t)
            made += 1
    return tasks


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=4)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out", default=str(DEFAULT_SYNTH_TASKS),
                    help="output JSON (default: tasks_synth.json next to this script)")
    args = ap.parse_args()
    tasks = generate(count_per_template=args.count, seed=args.seed)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=1)
    tiers = {}
    for t in tasks:
        tiers[t["tier"]] = tiers.get(t["tier"], 0) + 1
    print(f"generated {len(tasks)} verified tasks -> {args.out}  tiers={tiers}")


if __name__ == "__main__":
    main()
