"""Turn your y/n labels into quality numbers. Usage: python -m scripts.score_review

Tolerant of how Excel saves CSVs: comma/semicolon/tab separators, UTF-8/UTF-16/Windows encodings,
edited or duplicated headers (columns are read by POSITION), and a missing label heading
(the label column is then found by its contents: a column holding only y/n values).
"""
import csv
import io
import sys

YES, NO = ("y", "yes"), ("n", "no")


def read_table(path: str) -> tuple[list[str], list[list[str]]]:
    raw = open(path, "rb").read()
    text = None
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeError, ValueError):
            continue
    if text is None:
        raise SystemExit(f"Cannot read {path}: unknown text encoding. Re-save it as 'CSV UTF-8'.")
    first_line = text.splitlines()[0] if text.strip() else ""
    delim = max((",", ";", "\t"), key=first_line.count)
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
    if not rows:
        raise SystemExit(f"{path} is empty.")
    return rows[0], rows[1:]


def cell(row: list[str], i: int) -> str:
    return row[i] if i < len(row) else ""


def norm(value) -> str:
    return (value or "").strip().strip(".!,;:").strip().lower()


def yn(value) -> bool | None:
    v = norm(value)
    return True if v in YES else False if v in NO else None


def rate(values: list) -> tuple[float, int] | None:
    vals = [v for v in values if v is not None]
    return (sum(vals) / len(vals), len(vals)) if vals else None


def find_index(headers: list[str], *keywords: str) -> int | None:
    for i, h in enumerate(headers):
        low = (h or "").lower()
        if all(k in low for k in keywords):
            return i
    return None


def label_columns(rows: list[list[str]], ncols: int) -> list[int]:
    """Columns whose non-empty cells are ALL y/n/yes/no, and that have at least one such cell."""
    found = []
    for i in range(ncols):
        vals = [norm(cell(r, i)) for r in rows if cell(r, i).strip()]
        if vals and all(v in YES + NO for v in vals):
            found.append(i)
    return found


def diagnose(headers: list[str], rows: list[list[str]]) -> str:
    """Describe every column that contains at least one y/n-looking cell."""
    lines = []
    for i in range(len(headers)):
        cells = [cell(r, i).strip() for r in rows if cell(r, i).strip()]
        yn_cells = [c for c in cells if norm(c) in YES + NO]
        if yn_cells:
            other = [c for c in cells if norm(c) not in YES + NO]
            extra = f"; other values such as {other[:3]}" if other else ""
            lines.append(f"  column {i + 1} (heading {headers[i]!r}): {len(yn_cells)} y/n cells{extra}")
    if not lines:
        return ("  No column contains any y/n values. Your labels are probably not in the saved file "
                "(re-open the CSV and check; save with Ctrl+S and choose 'Keep current format').")
    return "Columns that contain y/n values:\n" + "\n".join(lines[:10])


def fail_columns(path: str, headers: list[str], what: str, rows=None):
    shown = headers[:12] + (["..."] if len(headers) > 12 else [])
    raise SystemExit(
        f"\nCould not find the {what} in {path}.\n"
        f"Header row starts with: {shown}  ({len(headers)} columns)\n"
        + (diagnose(headers, rows) + "\n" if rows is not None else "")
        + "You can name the column yourself, e.g.:  python -m scripts.score_review --relevant-col 33 "
          "--real-col 8 --supports-col 9\n"
        "Fix: re-run 'python -m scripts.export_review <project_id>' for a fresh file "
        "(this erases labels, so copy your current file first), and label it again.\n"
        "Tip: type y/n only in the label columns; do not drag or fill cells across the header row.")


def score(projects_path="review_projects.csv", needs_path="review_needs.csv", notes=None,
          relevant_col=None, real_col=None, supports_col=None) -> dict:
    """*_col are optional 1-based column numbers that override automatic detection."""
    notes = notes if notes is not None else []
    out = {}

    headers, rows = read_table(projects_path)
    col = relevant_col - 1 if relevant_col else find_index(headers, "relevant")
    if col is None:
        candidates = label_columns(rows, len(headers))
        if len(candidates) != 1:
            fail_columns(projects_path, headers, "'RELEVANT (y/n)' column", rows)
        col = candidates[0]
        notes.append(f"{projects_path}: heading missing; using column {col + 1} "
                     f"(the only column containing just y/n values) as RELEVANT.")
    labels = [yn(cell(r, col)) for r in rows]               # rows are already in rank order
    for k in (3, 5, 10):
        out[f"precision@{k}"] = rate(labels[:k])

    headers, rows = read_table(needs_path)
    real = real_col - 1 if real_col else find_index(headers, "real", "stakeholder")
    supports = supports_col - 1 if supports_col else find_index(headers, "supports")
    if real is None or supports is None or real == supports:
        candidates = label_columns(rows, len(headers))
        if len(candidates) != 2:
            fail_columns(needs_path, headers, "'REAL STAKEHOLDER' and 'QUOTE SUPPORTS THE NEED' columns", rows)
        real, supports = candidates
        notes.append(f"{needs_path}: headings missing; using columns {real + 1} and {supports + 1} "
                     "(the two y/n columns, in order) as REAL STAKEHOLDER and QUOTE SUPPORTS THE NEED.")
    out["real_stakeholder"] = rate([yn(cell(r, real)) for r in rows])
    out["quote_supports_need"] = rate([yn(cell(r, supports)) for r in rows])
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--relevant-col", type=int, help="1-based column number in review_projects.csv")
    ap.add_argument("--real-col", type=int, help="1-based column number in review_needs.csv")
    ap.add_argument("--supports-col", type=int, help="1-based column number in review_needs.csv")
    args = ap.parse_args()
    notes: list[str] = []
    try:
        results = score(notes=notes, relevant_col=args.relevant_col, real_col=args.real_col,
                        supports_col=args.supports_col)
    except FileNotFoundError as e:
        sys.exit(f"File not found: {e.filename}. Run this from the inner project folder, "
                 "after 'python -m scripts.export_review <project_id>'.")
    except PermissionError as e:
        sys.exit(f"Cannot open {e.filename}. Close it in Excel and try again.")
    for n in notes:
        print("NOTE:", n)
    if notes:
        print("Check that these are really your label columns before trusting the numbers.\n")
    for name, result in results.items():
        print(f"{name:22s}", "not labelled yet" if result is None else f"{result[0]:.0%}  (from {result[1]} labelled)")
    print("\nReport these as 'manual check of N items', never as a general accuracy figure.")
