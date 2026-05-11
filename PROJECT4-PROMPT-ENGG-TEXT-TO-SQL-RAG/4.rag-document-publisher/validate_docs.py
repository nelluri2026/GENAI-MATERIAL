import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from shared.rag.frontmatter import FRONTMATTER_PATTERN, parse_simple_yaml

REQUIRED_FIELDS = {"doc_id", "doc_type", "domain", "owner", "status"}
VALID_DOC_TYPES = {"schema", "business_rule", "example_sql", "glossary"}
VALID_STATUSES = {"active", "draft", "deprecated"}


def validate_file(path: Path) -> list[str]:
    errors: list[str] = []
    raw = path.read_text(encoding="utf-8")
    match = FRONTMATTER_PATTERN.match(raw)
    if not match:
        return [f"{path}: missing YAML frontmatter"]

    metadata = parse_simple_yaml(match.group(1))
    missing = REQUIRED_FIELDS - set(metadata)
    if missing:
        errors.append(f"{path}: missing required fields: {', '.join(sorted(missing))}")
    if metadata.get("doc_type") not in VALID_DOC_TYPES:
        errors.append(f"{path}: invalid doc_type {metadata.get('doc_type')}")
    if metadata.get("status") not in VALID_STATUSES:
        errors.append(f"{path}: invalid status {metadata.get('status')}")
    if not match.group(2).strip():
        errors.append(f"{path}: document body is empty")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate RAG markdown documents.")
    parser.add_argument("--doc-root", default="rag-docs")
    args = parser.parse_args()

    root = Path(args.doc_root)
    errors: list[str] = []
    for path in sorted(root.rglob("*.md")):
        errors.extend(validate_file(path))

    if errors:
        print("\n".join(errors), file=sys.stderr)
        raise SystemExit(1)
    print(f"Validated {len(list(root.rglob('*.md')))} RAG documents")


if __name__ == "__main__":
    main()
