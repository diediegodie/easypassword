#!/usr/bin/env python3
"""
Compare the original markdown file `docs/product_source_of_truth.md` with the
preserved markdown block inside `docs/product_source_of_truth.html` and run a
set of semantic checks to guarantee coherence for LLM ingestion.

Outputs:
 - scripts/compare_product_source.diff  (unified diff between files)
 - scripts/compare_product_source_report.txt (human-readable report)

Usage: python3 scripts/compare_product_source.py
"""

import os
import re
import sys
import difflib
import html as htmlmodule

BASE = os.path.dirname(os.path.dirname(__file__))
MD_PATH = os.path.join(BASE, "docs", "product_source_of_truth.md")
HTML_PATH = os.path.join(BASE, "docs", "product_source_of_truth.html")
DIFF_OUT = os.path.join(BASE, "scripts", "compare_product_source.diff")
REPORT_OUT = os.path.join(BASE, "scripts", "compare_product_source_report.txt")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def extract_original_markdown(html_text):
    m = re.search(
        r'<pre[^>]*class=["\']original-markdown["\'][^>]*>(.*?)</pre>',
        html_text,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return None
    return htmlmodule.unescape(m.group(1))


def section_block(md_text, heading):
    lines = md_text.splitlines()
    # match either '## Heading' or '### Heading' (some sections use h3)
    pattern = re.compile(r"^\s*#{2,3}\s+" + re.escape(heading) + r"\s*$", re.IGNORECASE)
    start = None
    for i, line in enumerate(lines):
        if pattern.match(line):
            start = i + 1
            break
    if start is None:
        return None
    # find next ## heading
    end = len(lines)
    for j in range(start, len(lines)):
        if re.match(r"^\s*##\s+", lines[j]):
            end = j
            break
    return "\n".join(lines[start:end]).strip()


def parse_table_rows(block):
    rows = []
    if not block:
        return rows
    lines = block.splitlines()
    # find table header (line with | --- |) then parse following rows
    header_idx = None
    for i, l in enumerate(lines):
        if (
            re.match(r"^\s*\|.*\|\s*$", l)
            and i + 1 < len(lines)
            and re.match(r"^\s*\|\s*-+", lines[i + 1])
        ):
            header_idx = i
            break
    if header_idx is None:
        return rows
    for l in lines[header_idx + 2 :]:
        if not re.match(r"^\s*\|", l):
            break
        m = re.match(r"^\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|", l)
        if m:
            rows.append((m.group(1).strip(), m.group(2).strip()))
    return rows


def write_report(text):
    with open(REPORT_OUT, "w", encoding="utf-8") as f:
        f.write(text)


def write_diff(diff_lines):
    with open(DIFF_OUT, "w", encoding="utf-8") as f:
        for line in diff_lines:
            f.write(line + "\n")


def main():
    md = read(MD_PATH)
    html = read(HTML_PATH)
    orig = extract_original_markdown(html)
    report_lines = []

    if orig is None:
        report_lines.append(
            'ERROR: could not find <pre class="original-markdown"> block in HTML'
        )
        write_report("\n".join(report_lines))
        print("\n".join(report_lines))
        sys.exit(2)

    # Normalize line endings
    md_lines = md.replace("\r\n", "\n").splitlines()
    orig_lines = orig.replace("\r\n", "\n").splitlines()

    diff = list(
        difflib.unified_diff(
            md_lines,
            orig_lines,
            fromfile=MD_PATH,
            tofile=HTML_PATH + ":original-markdown",
            lineterm="",
        )
    )
    identical = len(diff) == 0

    report_lines.append("PRODUCT SOURCE COMPARISON REPORT")
    report_lines.append("=" * 40)
    report_lines.append(f"Markdown file: {MD_PATH}")
    report_lines.append(f"HTML original block: {HTML_PATH} (pre.original-markdown)")
    report_lines.append("")
    report_lines.append(
        "Exact match between markdown and preserved original block: "
        + ("YES" if identical else "NO")
    )
    report_lines.append("")

    if not identical:
        report_lines.append("Unified diff (first 200 lines):")
        for i, line in enumerate(diff[:200]):
            report_lines.append(line)
        report_lines.append("...")
        write_diff(diff)
        report_lines.append(f"Full diff written to: {DIFF_OUT}")
    else:
        write_diff(["No differences"])

    # Heading checks
    heading_re = re.compile(r"^(#{1,3})\s+(.*\S)", re.MULTILINE)
    md_headings = [
        (len(m.group(1)), m.group(2).strip()) for m in heading_re.finditer(md)
    ]
    missing_headings = []
    for lvl, title in md_headings:
        # look for a matching <hN> that contains the title text (allow nested tags)
        h_pattern = re.compile(
            r"<h"
            + str(lvl)
            + r"[^>]*>.*?"
            + re.escape(title)
            + r".*?</h"
            + str(lvl)
            + r">",
            re.IGNORECASE | re.DOTALL,
        )
        if not h_pattern.search(html):
            # fallback: any h1-3 containing title
            any_h = re.compile(
                r"<h[1-3][^>]*>.*?" + re.escape(title) + r".*?</h[1-3]>",
                re.IGNORECASE | re.DOTALL,
            )
            if not any_h.search(html):
                missing_headings.append((lvl, title))

    report_lines.append("Heading checks:")
    report_lines.append(f" - total headings in markdown: {len(md_headings)}")
    report_lines.append(f" - missing headings in HTML: {len(missing_headings)}")
    for lvl, t in missing_headings:
        report_lines.append(f"   * H{lvl}: {t}")
    report_lines.append("")

    # Meta and LLM instruction checks
    meta_checks = {
        "meta:document:type": 'meta property="document:type"' in html,
        "meta:project:name": 'meta property="project:name"' in html,
        "meta:version": 'meta property="version"' in html,
        "meta:status": 'meta property="status"' in html,
        "llm-instruction": "INSTRUCTION FOR LLM" in html,
    }
    report_lines.append("Meta / LLM instruction checks:")
    for k, v in meta_checks.items():
        report_lines.append(f' - {k}: {"OK" if v else "MISSING"}')
    report_lines.append("")

    # Scope list items check
    scope_block = section_block(md, "V1 Scope and Direction")
    scope_items = re.findall(r"^\s*-\s*(.*\S)", scope_block or "", re.MULTILINE)
    missing_scope = []
    for item in scope_items:
        if item not in html:
            missing_scope.append(item)
    report_lines.append("Scope items check:")
    report_lines.append(f" - items in markdown: {len(scope_items)}")
    report_lines.append(f" - missing in HTML: {len(missing_scope)}")
    for s in missing_scope:
        report_lines.append(f"   * {s}")
    report_lines.append("")

    # Stack table checks (Frontend, Backend, Infrastructure)
    layer_map = [
        ("Frontend", "frontend"),
        ("Backend", "backend"),
        ("Infrastructure", "infrastructure"),
    ]
    table_issues = []
    for md_heading, layer in layer_map:
        block = section_block(md, md_heading)
        rows = parse_table_rows(block)
        report_lines.append(f"{md_heading} table rows: {len(rows)}")
        for tech, func in rows:
            # look for a tr with data-stack-layer and the tech name nearby
            pattern = re.compile(
                r'<tr[^>]*data-stack-layer=["\']'
                + re.escape(layer)
                + r'["\'][^>]*>.*?<td[^>]*>\s*'
                + re.escape(tech)
                + r"\s*</td>",
                re.DOTALL | re.IGNORECASE,
            )
            if not pattern.search(html):
                table_issues.append((layer, tech))
    report_lines.append(f"Stack table issues found: {len(table_issues)}")
    for l, t in table_issues:
        report_lines.append(f' - layer {l}: missing tech row for "{t}"')
    report_lines.append("")

    # Final decision
    ok = (
        identical
        and (len(missing_headings) == 0)
        and all(meta_checks.values())
        and (len(missing_scope) == 0)
        and (len(table_issues) == 0)
    )
    report_lines.append("Overall consistency check: " + ("PASS" if ok else "FAIL"))

    report_text = "\n".join(report_lines)
    print(report_text)
    write_report(report_text)

    if not ok:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
