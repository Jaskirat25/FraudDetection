import re

with open(r'c:\Users\HP\Desktop\FraudDetection\rebuild_perfect_docx.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace dashes and unicode characters
text = text.replace('\u2014', ' -- ')  # em dash
text = text.replace('\u2013', '-')    # en dash
text = text.replace('\u2022', '-')    # bullet
text = text.replace('\u00e9', 'e')    # e with acute (Moire)
text = text.replace('\u201d', '"')    # right double quote
text = text.replace('\u201c', '"')    # left double quote
text = text.replace('\u2019', "'")    # right single quote
text = text.replace('\u2018', "'")    # left single quote
text = text.replace('\u2264', '<=')   # less than or equal
text = text.replace('\u2265', '>=')   # greater than or equal

with open(r'c:\Users\HP\Desktop\FraudDetection\rebuild_perfect_docx.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("All unicode characters normalized successfully.")
