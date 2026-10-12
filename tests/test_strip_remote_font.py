import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'strip_remote_font', Path(__file__).resolve().parents[1]/'scripts/strip_remote_font.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
FONT = "@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Space+Grotesk:wght@400;500;600;700&display=swap');"


class FontProfileTests(unittest.TestCase):
    def test_exact_font_removed_despite_embedded_semicolons(self):
        css = FONT + 'body{font-family:system-ui}'
        output, n = mod.strip_fonts(css)
        self.assertEqual(n, 1)
        self.assertEqual(output, 'body{font-family:system-ui}')

    def test_quoted_import_and_remote_origin_refusal(self):
        self.assertEqual(mod.strip_fonts(FONT.replace('url(', '').replace(');', ';'))[1], 1)
        with self.assertRaisesRegex(ValueError, 'UNREVIEWED_REMOTE_CSS_IMPORT'):
            mod.strip_fonts('@import url("https://evil.test/style.css");' + FONT)

    def test_drift_and_extra_remote_asset_refusal(self):
        with self.assertRaisesRegex(ValueError, 'FONT_IMPORT_IDENTITY_DRIFT'):
            mod.strip_fonts(FONT.replace('DM+Mono', 'Other'))
        with self.assertRaisesRegex(ValueError, 'UNREVIEWED_REMOTE_ASSET'):
            mod.strip_fonts(FONT + 'body{background:url(https://remote.test/a.png)}')

    def test_transform_receipt_and_repeat_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'assets').mkdir()
            css = root / 'assets/main.css'
            css.write_text(FONT + 'div{color:red}')
            report = mod.transform(root)
            self.assertEqual(report['reviewed_imports_removed'], 1)
            self.assertEqual(css.read_text(), 'div{color:red}')
            self.assertFalse(report['external_done'])
            with self.assertRaisesRegex(ValueError, 'EXPECTED_EXACTLY_ONE'):
                mod.transform(root)


if __name__ == '__main__':
    unittest.main()
