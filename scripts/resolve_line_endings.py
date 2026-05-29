from pathlib import Path

EXCLUDED = {
    ".git",
    ".venv",
    "__pycache__",
}

TEXT_EXTENSIONS = {
    ".py",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".md",
    ".txt",
    ".sql",
    ".sh",
}

updated = 0

for path in Path(".").rglob("*"):
    if (
        not path.is_file()
        or any(part in EXCLUDED for part in path.parts)
        or path.suffix not in TEXT_EXTENSIONS
    ):
        continue

    try:
        text = path.read_text()

        normalized = text.replace(
            "\r\n",
            "\n",
        )

        if normalized != text:
            path.write_text(normalized)
            updated += 1
            print(f"Normalized: {path}")

    except Exception:
        pass

print(f"\nUpdated {updated} files")
