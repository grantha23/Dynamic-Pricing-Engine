"""strip_sidebar_calls.py — Remove render_sidebar() from page files (now handled by app.py)."""
import glob, re

files = glob.glob("dashboard/pages/[1-5]*.py")

for fpath in files:
    with open(fpath, encoding="utf-8") as f:
        content = f.read()
    original = content

    # Remove the import line
    content = re.sub(r'^from dashboard\.sidebar import render_sidebar\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^from dashboard\.sidebar import render_sidebar, GLOBAL_CSS\n', '', content, flags=re.MULTILINE)

    # Remove the call (with optional comment above it)
    content = re.sub(r'\n# Shared sidebar.*?\nrender_sidebar\(__file__\)\n', '\n', content)
    content = re.sub(r'\nrender_sidebar\(__file__\)\n', '\n', content)

    if content != original:
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Stripped: {fpath}")
    else:
        print(f"No change: {fpath}")

print("Done.")
