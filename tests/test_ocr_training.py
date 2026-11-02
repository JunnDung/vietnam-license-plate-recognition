"""Isolation contracts for fine-tuning, independent of training dependencies."""
import unittest
import csv
from pathlib import Path
import tempfile
from copy import deepcopy
from types import SimpleNamespace

import numpy as np

from scripts.prepare_ocr_training import build_groups, assign_splits, write_csvs, split_unique_rows
from scripts.train_ocr import fetch_assets, training_progress, verify_training_crops, sha
from scripts.evaluate_ocr_finetune import adoption_checks, match_target, read_single
from scripts.export_ocr import decode_texts, export_paths


class TrainingDataChecks(unittest.TestCase):
    def test_training_rejects_changed_pixels_and_paths_outside_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'data').mkdir();image=root/'data/a.png';image.write_bytes(b'pixels')
            rows=[{'split':'train','image':'data/a.png','image_sha256':sha(image)}]
            self.assertEqual(verify_training_crops(rows,root),1)
            image.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'checksum'):verify_training_crops(rows,root)
            rows[0]['image']='../outside.png'
            with self.assertRaisesRegex(ValueError,'outside'):verify_training_crops(rows,root)
            outside=root/'outside.png';outside.write_bytes(b'pixels')
            link=root/'data/link.png'
            try:link.symlink_to(outside)
            except OSError:return  # Windows without symlink privilege still runs the other boundary checks.
            rows[0].update(image='data/link.png',image_sha256=sha(outside))
            with self.assertRaisesRegex(ValueError,'outside'):verify_training_crops(rows,root)

    def test_deduplication_preserves_reserved_links_from_all_captures(self):
        rows=[{'member':m,'plate':p,'source_pixel_sha256':s,'pixel_sha256':c}
              for m,p,s,c in [('a','A','s1','same'),('b','A','s2','same'),('c','B','s2','other')]]
        selected,audit=split_unique_rows(rows,set(),{'s2'},'seed')
        self.assertEqual(audit['duplicate_images'],1)
        self.assertEqual({r['split'] for r in selected},{'excluded'})
        self.assertEqual(len({r['group'] for r in selected}),1)

    def test_export_never_overwrites_a_resumable_checkpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            checkpoint=Path(folder)/'best.keras';checkpoint.write_bytes(b'optimizer and weights')
            output=Path(folder)/'best.onnx'
            fp32=export_paths(output)
            self.assertEqual(fp32.name,'best-fp32.keras')
            self.assertEqual(checkpoint.read_bytes(),b'optimizer and weights')
            fp32.write_bytes(b'prior export')
            with self.assertRaises(FileExistsError):export_paths(output)

    def test_export_decoder_preserves_slots_and_strips_only_trailing_padding(self):
        probabilities=np.eye(3,dtype=np.float32)[np.array([[0,2],[1,0]])]
        self.assertEqual(decode_texts(probabilities,'AB_',2),['A','BA'])

    def test_adoption_rejects_accuracy_character_layout_latency_and_legacy_regressions(self):
        base={'samples':1000,'correct':960,'cer':.01,'latency_p95_ms':100.,
              'two_lines':{'samples':400,'correct':370},'pipeline_exact_match':.94}
        candidate=deepcopy(base);candidate.update(correct=970,cer=.009,latency_p95_ms=105.,pipeline_exact_match=.95)
        candidate['two_lines']['correct']=375
        legacy={'crop':37,'pipeline':37}
        self.assertTrue(all(adoption_checks(base,candidate,legacy,legacy).values()))
        for change in ({'correct':964},{'cer':.011},{'latency_p95_ms':111.},{'pipeline_exact_match':.93}):
            with self.subTest(change=change):
                self.assertFalse(all(adoption_checks(base,dict(candidate,**change),legacy,legacy).values()))
        changed=deepcopy(candidate);changed['two_lines']['correct']=369
        self.assertFalse(all(adoption_checks(base,changed,legacy,legacy).values()))
        self.assertFalse(all(adoption_checks(base,candidate,legacy,{'crop':36,'pipeline':37}).values()))

    def test_target_matching_does_not_choose_a_box_by_ground_truth_text(self):
        target=[0,0,100,100]
        detections=[{'bbox':target,'plate':'WRONG'}, {'bbox':[1,1,99,99],'plate':'51A12345'},
                    {'bbox':[200,200,300,300],'plate':'UNANNOTATED'}]
        matched=match_target(detections,target)
        self.assertEqual(matched['plate'],'WRONG')
        self.assertIsNone(match_target(detections,[500,500,600,600]))

    def test_single_pass_uses_one_rgb_image_and_shared_slot_decoding(self):
        calls=[]
        def run(images,**kwargs):
            calls.extend(images)
            return [SimpleNamespace(plate='51A_12345',char_probs=[.9,.9,.9,.01,.8,.8,.8,.8,.8,.01])]
        ocr=SimpleNamespace(run=run)
        result=read_single(ocr,np.full((40,80,3),(10,20,200),np.uint8))
        self.assertEqual(len(calls),1)
        np.testing.assert_array_equal(calls[0][0,0],[200,20,10])
        self.assertEqual(result['plate'],'51A12345')
        self.assertAlmostEqual(result['ocr_confidence'],.8375)
        self.assertEqual(read_single(ocr,np.zeros((7,80,3),np.uint8))['plate'],'')
        self.assertEqual(len(calls),1)

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
