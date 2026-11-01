"""Optional Keras training checks; run with the isolated training interpreter."""
import importlib.util
import os
import unittest
from pathlib import Path
import tempfile

os.environ.setdefault('KERAS_BACKEND','torch')


@unittest.skipUnless(importlib.util.find_spec('keras'),'Requires isolated OCR training environment')
class TrainingBackendChecks(unittest.TestCase):
    def test_serialized_augmentation_preserves_seed(self):
        import albumentations as A
        import numpy as np
        from scripts.train_ocr import save_augmentation
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'augmentation.yaml';save_augmentation(path,123)
            first=A.load(path,data_format='yaml');second=A.load(path,data_format='yaml')
            image=np.arange(64*128*3,dtype=np.uint8).reshape(64,128,3)
            for _ in range(4):np.testing.assert_array_equal(first(image=image)['image'],second(image=image)['image'])

    def test_exact_accuracy_weights_examples_in_unequal_batches(self):
        import keras
        import numpy as np
        from fast_plate_ocr.train.model.metric import plate_acc_metric
        from scripts import train_ocr
        factory=getattr(train_ocr,'exact_plate_accuracy',plate_acc_metric)
        metric=keras.metrics.MeanMetricWrapper(factory(2,3))
        truth=np.eye(3,dtype=np.float32)[np.array([[0,1],[1,2]])]
        metric.update_state(truth,truth)
        wrong=np.eye(3,dtype=np.float32)[np.array([[1,1]])]
        metric.update_state(truth[:1],wrong)
        self.assertAlmostEqual(float(keras.ops.convert_to_numpy(metric.result())),2/3,places=6)


if __name__=='__main__':unittest.main()
