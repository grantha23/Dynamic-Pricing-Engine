"""Final pass: replace all remaining mojibake sequences in dashboard pages."""
import glob

files = glob.glob("dashboard/pages/*.py")

replacements = [
    ("\u00c2\u00b7", "\u00b7"),      # Â· → ·  (middle dot)
    ("\u00e2\u0082\u00b9", "\u20b9"), # â‚¹ → ₹  (rupee)
    ("\u00e2\u0080\u0093", "\u2013"), # en dash
    ("\u00e2\u0080\u0094", "\u2014"), # em dash
    ("\u00e2\u0080\u009c", "\u201c"), # left quote
    ("\u00e2\u0080\u009d", "\u201d"), # right quote
    ("\u00e2\u0096\u00b2", "\u25b2"), # ▲
    ("\u00e2\u0096\u00bc", "\u25bc"), # ▼
    ("\u00e2\u0097\u008f", "\u25cf"), # ●
    ("\u00e2\u0086\u0092", "\u2192"), # →
    ("\u00e2\u0086\u0093", "\u2193"), # ↓
    ("\u00e2\u0086\u00ba", "\u21ba"), # ↺
    ("\u00e2\u008c\u009b", "\u231b"), # ⌛
    ("\u00c3\u00a9", "\u00e9"),       # é
]

for fpath in files:
    with open(fpath, encoding="utf-8") as f:
        text = f.read()
    original = text
    for bad, good in replacements:
        text = text.replace(bad, good)
    if text != original:
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Cleaned: {fpath}")
    else:
        print(f"OK:      {fpath}")

print("Done.")
