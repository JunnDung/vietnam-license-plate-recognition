"""Dataset leakage and OCR metric contracts, independent of model weights."""
import unittest
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from scripts.prepare_ocr_benchmark import parse_name, partition, deduplicate
from scripts.benchmark_ocr import summarize


class EvaluationChecks(unittest.TestCase):
    def test_filename_boxes_split_and_conflicts(self):
        item = parse_name('detection/two_rows/4_710_0_29t116544_12_17_153_138.jpg')
        self.assertEqual(item['plate'],'29T116544')
        self.assertEqual(item['bbox'],[12,17,153,138])
        self.assertTrue(item['square'])
        self.assertEqual(partition('29T116544'),partition('29t116544'))
        with self.assertRaises(ValueError): parse_name('detection/one_row/invalid.jpg')
        with self.assertRaises(ValueError): parse_name('../4_710_0_29T116544_12_17_153_138.jpg')
        with self.assertRaises(ValueError): parse_name('detection/two_rows/4_710_0_29T116544_153_17_12_138.jpg')
        rows=[{'plate':'29T116544','pixel_sha256':'a','member':'b'},
              {'plate':'29T116544','pixel_sha256':'a','member':'a'},
              {'plate':'30A12345','pixel_sha256':'bad','member':'c'},
              {'plate':'30A12346','pixel_sha256':'bad','member':'d'}]
        kept,audit=deduplicate(rows)
        self.assertEqual([row['member'] for row in kept],['a'])
        self.assertEqual(audit,{'duplicate_images':1,'conflicting_images':2})

    def test_metrics_include_failures_and_interval(self):
        rows=[{'expected':'AB12','predicted':'AB12','latency_ms':10},
              {'expected':'CD34','predicted':'CD3','latency_ms':20},
              {'expected':'EF56','predicted':'','latency_ms':30}]
        result=summarize(rows)
        self.assertEqual(result['samples'],3)
        self.assertEqual(result['correct'],1)
        self.assertAlmostEqual(result['exact_match'],1/3)
        self.assertAlmostEqual(result['cer'],5/12)
        self.assertLess(result['wilson95'][0],1/3)
        self.assertGreater(result['wilson95'][1],1/3)
        self.assertEqual(result['latency_p50_ms'],20)
        with self.assertRaises(ValueError): summarize([])

    def test_cli_rejects_empty_selection_and_unsafe_paths_before_model_load(self):
        script=Path(__file__).resolve().parents[1]/'scripts/benchmark_ocr.py'
        with tempfile.TemporaryDirectory() as folder:
            manifest=Path(folder)/'manifest.json'
            for samples,expected in [([], 'No selected samples'),
                ([{'plate':'51A12345','split':'dev','image':'../outside.png'}], 'Sample outside data directory'),
                ([{'plate':'51A12345','split':split} for split in ('dev','test')], 'Repeated plate identity')]:
                manifest.write_text(json.dumps({'samples':samples}),encoding='utf-8')
                result=subprocess.run([sys.executable,str(script),'--manifest',str(manifest),
                    '--baseline-module',str(Path(folder)/'absent.py'),'--output',str(Path(folder)/'report.json')],
                    capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0)
                self.assertIn(expected,result.stderr)


if __name__ == '__main__':
    unittest.main()
