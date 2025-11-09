import fitz

doc = fitz.open('uploads/qT 9603.pdf')
page = doc[0]
blocks = page.get_text('rawdict')

spans_found = 0
for b in blocks.get('blocks', []):
    if 'lines' in b:
        for line in b.get('lines', []):
            for span in line.get('spans', []):
                text = span.get('text', '')
                if text and text.strip():
                    spans_found += 1
                    if spans_found == 1:
                        print('First span text:', repr(text))
                        print('First span bbox:', span.get('bbox'))
                        print('First span font:', span.get('font'))
                        print('First span size:', span.get('size'))

print('Total spans with text:', spans_found)

