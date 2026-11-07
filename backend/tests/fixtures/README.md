# Synthetic OCR fixture

`synthetic-income.png` is a fixed 1500 × 450 RGB scan containing only:

- SYNTHETIC INCOME RECORD
- Monthly income: 50000
- Monthly debt: 12000

It was rendered once using 52 px Arial on white. No font file or real applicant
data is included. Tests load these exact pixels instead of selecting a different
installed font on Windows and Ubuntu. The PDF test rasterizes the same fixture
into an image-only PDF at maximum JPEG quality.

Tests still run the real local OCR engine and assert the expected amounts,
page provenance, and unverified status. Recognition errors remain unverified;
the application does not replace ambiguous characters with guessed amounts.
