"""Extract the brief's text so the content can be checked without Word."""
import re
import zipfile

z = zipfile.ZipFile("BMO-Capital-Markets-Client-Intelligence-Brief.docx")
x = z.read("word/document.xml").decode("utf-8")

paras = re.findall(r"<w:p[ >].*?</w:p>", x, re.S)
out = []
for pp in paras:
    t = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", pp, re.S))
    if t.strip():
        out.append(t)

print(f"paragraphs with text : {len(out)}")
print(f"tables               : {x.count('<w:tbl>')}")
print(f"page breaks          : {x.count('w:br w:type=')}")

quotes = [t for t in out if t.startswith("\u201c")]
print(f"\nDEMO QUESTIONS ({len(quotes)}):")
for q in quotes:
    print(f"  - {q[:110]}")

heads = re.findall(r'<w:pStyle w:val="(Heading[123])"/>.*?<w:t[^>]*>(.*?)</w:t>', x, re.S)
print(f"\nHEADINGS ({len(heads)}):")
for lvl, txt in heads:
    print(f"  {'  ' * (int(lvl[-1]) - 1)}{lvl[-1]}. {txt}")

blob = " ".join(out)
print("\nFACT CHECK:")
for label, needle in [
    ("country limit 2,400", "2,400m"),
    ("utilised 2,196", "2,196m"),
    ("headroom 204", "204m"),
    ("demand 246", "246m"),
    ("shortfall 42", "42m"),
    ("91.5%", "91.5%"),
    ("72.2%", "72.2%"),
    ("72.6%", "72.6%"),
    ("58.5%", "58.5%"),
    ("IG-5", "IG-5"),
    ("CRC ref", "CRC-2026-0412"),
    ("14.8% wallet", "14.8%"),
    ("86.7% PSE", "86.7%"),
    ("1.98x", "1.98x"),
    ("disclaimer", "Synthetic demonstration data"),
]:
    print(f"  {'OK ' if needle in blob else 'MISSING'} {label}")
