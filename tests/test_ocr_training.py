"""Isolation contracts for fine-tuning, independent of training dependencies."""
import unittest
import csv
from pathlib import Path
import tempfile

from scripts.prepare_ocr_training import build_groups, assign_splits, write_csvs
from scripts.train_ocr import fetch_assets, training_progress


class TrainingDataChecks(unittest.TestCase):
    def test_cached_weights_must_match_pinned_upstream_digest(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'cct_s_v2_global.keras').write_bytes(b'wrong weights')
            with self.assertRaisesRegex(ValueError,'Checksum'):fetch_assets(Path(folder))

    def test_progress_uses_completed_epoch_csv(self):
        with tempfile.TemporaryDirectory() as folder:
            run=Path(folder)/'run';run.mkdir()
            (run/'training_log.csv').write_text('epoch,loss,val_plate_acc,val_loss\n0,1.5,0.8,1.4\n1,0.5,0.9,0.8\n2,0.4,0.95',encoding='utf-8')
            result=training_progress(Path(folder))
            self.assertEqual(result['completed_epochs'],2)
            self.assertEqual(result['last_metrics']['val_plate_acc'],.9)
            self.assertEqual(result['best_validation_accuracy'],.9)
            (run/'training_log.csv').write_text('epoch,loss,val_plate_acc\n0,nan,0.9\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Nonfinite'):training_progress(Path(folder))

    def test_csv_keeps_region_head_shapes_and_never_writes_test_labels(self):
        rows=[{'image':'data/ocr_training/crops/'+s+'.png','plate':'51A12345','split':s}
              for s in ('train','val','test')]
        with tempfile.TemporaryDirectory() as folder:
            write_csvs(rows,Path(folder))
            with (Path(folder)/'train.csv').open(newline='',encoding='utf-8') as file:
                self.assertEqual(list(csv.DictReader(file)),[{'image_path':'crops/train.png','plate_text':'51A12345','plate_region':'Vietnam'}])
            self.assertFalse((Path(folder)/'test.csv').exists())

    def test_transitive_groups_and_reserved_sources_cannot_leak(self):
        rows=[{'member':m,'plate':p,'source_pixel_sha256':s,'pixel_sha256':c}
              for m,p,s,c in [('a','A','s1','c1'),('b','B','s1','c2'),
                              ('c','B','s2','c3'),('d','C','s2','c4'),('e','D','s3','c5')]]
        self.assertEqual(sorted(map(len,build_groups(rows))),[1,4])
        for plates,sources in [({'A'},set()),(set(),{'s1'})]:
            result=assign_splits(rows,plates,sources,'test-seed')
            self.assertEqual({r['plate'] for r in result if r['split']=='excluded'},{'A','B','C'})
            self.assertEqual(sum(r['split']!='excluded' for r in result),1)
        same_crop=[dict(rows[0]),dict(rows[4],pixel_sha256='c1')]
        self.assertEqual(len(build_groups(same_crop)),1)

    def test_deterministic_split_has_disjoint_ids_and_pixels(self):
        rows=[{'member':str(i),'plate':str(i),'source_pixel_sha256':'s'+str(i),
               'pixel_sha256':'c'+str(i)} for i in range(400)]
        first=assign_splits(rows,set(),set(),'vnlp-finetune-20261102')
        second=assign_splits(list(reversed(rows)),set(),set(),'vnlp-finetune-20261102')
        self.assertEqual(first,second)
        self.assertEqual({r['split'] for r in first},{'train','val','test'})
        for key in ('plate','source_pixel_sha256','pixel_sha256'):
            seen={}
            for row in first:
                self.assertNotIn(row[key],seen)
                seen[row[key]]=row['split']


if __name__=='__main__':unittest.main()
