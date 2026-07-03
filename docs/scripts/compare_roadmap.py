#!/usr/bin/env python3
import re
import sys
import os

md_path = os.path.join("docs", "roadmap.md")
html_path = os.path.join("docs", "roadmap-v1.html")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


md = read(md_path)
html = read(html_path)
md_lines = md.splitlines()

# Parse markdown headings and tasks
phases_md = []
current_phase = None
current_sub = None
md_tasks = []
for i, line in enumerate(md_lines, start=1):
    h2 = re.match(r"^\s*##\s+(.*\S)", line)
    if h2:
        current_phase = h2.group(1).strip()
        current_sub = None
        phases_md.append(("h2", current_phase, i))
        continue
    h3 = re.match(r"^\s*###\s+(.*\S)", line)
    if h3:
        current_sub = h3.group(1).strip()
        phases_md.append(("h3", current_sub, i))
        continue
    m = re.match(r"^\s*-\s*\[([ xX])\]\s*(.*\S)", line)
    if m:
        status = "done" if m.group(1).lower() == "x" else "pending"
        text = m.group(2).strip()
        md_tasks.append(
            {
                "line": i,
                "phase": current_phase,
                "sub": current_sub,
                "status": status,
                "text": text,
            }
        )

# Parse HTML tasks (divs with data-task-id)
pattern = re.compile(
    r'(<div[^>]*data-task-id="(?P<id>[^"]+)"[^>]*>)(?P<body>.*?)</div>', re.DOTALL
)
html_tasks = []
for m in pattern.finditer(html):
    open_tag = m.group(1)
    tid = m.group("id")
    body = m.group("body")
    status = "unknown"
    if (
        "task-done" in open_tag
        or "status-done" in open_tag
        or "status-done" in body
        or "task-done" in body
    ):
        status = "done"
    elif (
        "task-pending" in open_tag
        or "status-pending" in open_tag
        or "status-pending" in body
        or "task-pending" in body
    ):
        status = "pending"
    text = re.sub(r"<[^>]+>", "", body).strip()
    text_clean = re.sub(r"^[\s✅⏳]+", "", text).strip()
    html_tasks.append({"id": tid, "status": status, "text": text_clean, "raw": body})

md_total = len(md_tasks)
md_done = sum(1 for t in md_tasks if t["status"] == "done")
md_pending = md_total - md_done
html_total = len(html_tasks)
html_done = sum(1 for t in html_tasks if t["status"] == "done")
html_pending = html_total - html_done

# Matching: try to find each markdown task in HTML by substring (case-insensitive)
matches = []
missing = []
status_mismatches = []
ambiguous = []


def normalize(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


for t in md_tasks:
    md_text = t["text"]
    found = [h for h in html_tasks if md_text.lower() in h["text"].lower()]
    # Fallback: normalized alphanumeric substring match (removes punctuation/spaces)
    if not found:
        md_norm = normalize(md_text)
        if md_norm:
            found = [h for h in html_tasks if md_norm in normalize(h["text"])]

    if not found:
        missing.append({"md_line": t["line"], "text": md_text})
    elif len(found) > 1:
        ambiguous.append(
            {"md_line": t["line"], "text": md_text, "matches": [h["id"] for h in found]}
        )
    else:
        h = found[0]
        matches.append(
            {
                "md_line": t["line"],
                "text": md_text,
                "html_id": h["id"],
                "md_status": t["status"],
                "html_status": h["status"],
            }
        )
        if t["status"] != h["status"]:
            status_mismatches.append(
                {
                    "md_line": t["line"],
                    "text": md_text,
                    "md_status": t["status"],
                    "html_status": h["status"],
                    "html_id": h["id"],
                }
            )

# Headings check
heading_mismatches = []
for tag, heading, l in phases_md:
    if tag == "h2":
        if f"<h2>{heading}</h2>" not in html and f"<h2>{heading}" not in html:
            heading_mismatches.append({"type": "h2", "text": heading, "line": l})
    else:
        if f"<h3>{heading}</h3>" not in html and f"<h3>{heading}" not in html:
            heading_mismatches.append({"type": "h3", "text": heading, "line": l})

# LLM comment and meta tags
llm_present = "INSTRUCTION FOR LLM" in html
meta_project = all(
    k in html
    for k in [
        'meta property="document:type"',
        'meta property="project:name"',
        'meta property="version"',
        'meta property="project-status"',
    ]
)

ok = (
    (md_total == html_total)
    and (len(missing) == 0)
    and (len(status_mismatches) == 0)
    and llm_present
    and meta_project
    and (len(heading_mismatches) == 0)
)

print("ROADMAP COMPARISON REPORT")
print("=========================")
print(f"Markdown tasks: {md_total} (done: {md_done}, pending: {md_pending})")
print(f"HTML tasks: {html_total} (done: {html_done}, pending: {html_pending})")
print("")
print(f"Matching entries: {len(matches)}")
print(f"Missing in HTML: {len(missing)}")
print(f"Status mismatches: {len(status_mismatches)}")
print(f"Ambiguous matches: {len(ambiguous)}")
print(f"Heading mismatches: {len(heading_mismatches)}")
print(f"LLM comment present: {llm_present}")
print(f"Meta tags present: {meta_project}")
print("")
if missing:
    print("Missing items (present in markdown but not found in HTML):")
    for m in missing:
        print(f' - line {m["md_line"]}: {m["text"]}')
if status_mismatches:
    print("\nStatus mismatches:")
    for s in status_mismatches:
        print(
            f' - line {s["md_line"]}: "{s["text"]}" md={s["md_status"]} html={s["html_status"]} (html id={s["html_id"]})'
        )
if ambiguous:
    print("\nAmbiguous matches (multiple HTML entries matched a single MD task):")
    for a in ambiguous:
        print(f' - line {a["md_line"]}: "{a["text"]}" matches html ids {a["matches"]}')
if heading_mismatches:
    print("\nHeading mismatches:")
    for h in heading_mismatches:
        print(f' - {h["type"]} "{h["text"]}" (md line {h["line"]})')

print("\nOverall consistency check:", "PASS" if ok else "FAIL")
if not ok:
    sys.exit(2)
sys.exit(0)
