"""Bounded CUDA fine-tuning using the upstream CLI and recoverable checkpoints."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
BASE='https://github.com/ankandrew/fast-plate-ocr/releases/download/arg-plates/'
ASSETS={
    'cct_s_v2_global.keras':'dc6db494714d88e1fb0a21b4e4e96089842dd5440418262abfc382454453c2c8',
    'cct_s_v2_global_model_config.yaml':'244c3c712205750e9747bca4707cd553a84005f41959745bff676b0fca8faba3',
    'cct_s_v2_global_plate_config.yaml':'0335c74a305173bb6f393efed0fde03cadeaa0b649ed8e19f431016d8232d0a6'}


def sha(path):
    with Path(path).open('rb') as file:return hashlib.file_digest(file,'sha256').hexdigest()


def verify_training_crops(samples,root):
    count=0;parents={};data=(root/'data').resolve()
    for row in samples:
        if row['split'] not in ('train','val'):continue
        path=root/row['image']
        if path.parent not in parents:parents[path.parent]=path.parent.resolve()
        resolved=path.resolve() if path.is_symlink() else parents[path.parent]/path.name
        if not resolved.is_relative_to(data):raise ValueError('Training image outside data directory')
        if sha(path)!=row['image_sha256']:raise ValueError('Training image checksum mismatch')
        count+=1
    return count


def fetch_assets(folder):
    folder.mkdir(parents=True,exist_ok=True)
    for name,expected in ASSETS.items():
        path=folder/name
        if not path.exists():
            temporary=path.with_suffix('.download')
            urllib.request.urlretrieve(BASE+name,temporary)
            if sha(temporary)!=expected:raise ValueError('Checksum mismatch: '+name)
            temporary.replace(path)
        if sha(path)!=expected:raise ValueError('Checksum mismatch: '+name)
    return {name:folder/name for name in ASSETS}


def training_progress(folder):
    logs=sorted(folder.glob('*/training_log.csv'))
    if not logs:return {'completed_epochs':0}
    with logs[-1].open(encoding='utf-8',newline='') as file:rows=list(csv.DictReader(file))
    rows=[row for row in rows if row.get('val_plate_acc') not in (None,'') and all(value not in (None,'') for value in row.values())]
    if not rows:return {'completed_epochs':0}
    scores=[float(row['val_plate_acc']) for row in rows]
    if not all(math.isfinite(float(value)) for row in rows for value in row.values()):
        raise ValueError('Nonfinite training/validation metrics')
    return {'completed_epochs':len(rows),'last_metrics':{key:float(value) for key,value in rows[-1].items()},
            'best_validation_accuracy':max(scores),'best_epoch':scores.index(max(scores))+1,
            'checkpoint_dir':str(logs[-1].parent.relative_to(ROOT)) if logs[-1].is_relative_to(ROOT) else str(logs[-1].parent)}


def exact_plate_accuracy(max_plate_slots,vocabulary_size):
    from keras import ops
    def acc(y_true,y_pred):
        truth=ops.argmax(ops.reshape(y_true,(-1,max_plate_slots,vocabulary_size)),axis=-1)
        predicted=ops.argmax(ops.reshape(y_pred,(-1,max_plate_slots,vocabulary_size)),axis=-1)
        # Return one value per plate so Keras weights a short final batch correctly.
        return ops.cast(ops.all(ops.equal(truth,predicted),axis=-1),'float32')
    return acc


def save_augmentation(path,seed):
    import albumentations as A
    import yaml
    from fast_plate_ocr.train.data.augmentation import default_train_augmentation
    augmentation=default_train_augmentation('rgb')
    augmentation.transforms.extend([A.MotionBlur(blur_limit=(3,7),p=.15),
        A.RandomGamma(gamma_limit=(70,140),p=.15),A.GaussNoise(std_range=(.01,.04),p=.1)])
    config=A.to_dict(augmentation)
    # Compose omits its seed when serialized; persist the supported constructor argument.
    config['transform']['seed']=seed
    path.write_text(yaml.safe_dump(config,sort_keys=False),encoding='utf-8',newline='\n')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--name',default='ocr_finetune')
    parser.add_argument('--batch',type=int,choices=(16,32),default=32)
    parser.add_argument('--epochs',type=int,default=30)
    parser.add_argument('--lr',type=float,default=1e-4)
    args=parser.parse_args()
    if not 1<=args.epochs<=30 or not 0<args.lr<=1e-3:parser.error('Invalid declared training bounds')
    if not args.name.replace('_','').replace('-','').isalnum():parser.error('Invalid run name')
    run=ROOT/'runs'/args.name
    if run.exists():parser.error('Run exists; preserve checkpoints and use a new name')
    manifest_path=ROOT/'reports/ocr_finetune_manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    verified_images=verify_training_crops(manifest['samples'],ROOT)
    data=ROOT/'data/ocr_training'
    for split in ('train','val'):
        if sha(data/(split+'.csv'))!=manifest['csv_sha256'][split]:raise ValueError('Training CSV checksum mismatch')
        with (data/(split+'.csv')).open(encoding='utf-8',newline='') as file:rows=list(csv.DictReader(file))
        expected={(Path(row['image']).relative_to('data/ocr_training').as_posix(),row['plate'],'Vietnam')
                  for row in manifest['samples'] if row['split']==split}
        if {(row['image_path'],row['plate_text'],row.get('plate_region')) for row in rows}!=expected or len(rows)!=len(expected):
            raise ValueError('Training CSV does not match frozen split and region head')
    assets=fetch_assets(ROOT/'models/training')
    os.environ['KERAS_BACKEND']='torch'
    os.environ['NO_ALBUMENTATIONS_UPDATE']='1'
    os.environ.setdefault('OMP_NUM_THREADS','4')
    import keras
    import numpy as np
    import torch
    from fast_plate_ocr.train.model.model_builders import build_model
    from fast_plate_ocr.train.model.model_schema import load_model_config_from_yaml
    from fast_plate_ocr.train.model.config import load_plate_config_from_yaml
    from fast_plate_ocr.train.model.loss import cce_loss
    from fast_plate_ocr.train.utilities.utils import target_transform
    from fast_plate_ocr.cli.train import train
    import importlib
    importlib.import_module('fast_plate_ocr.cli.train').plate_acc_metric=exact_plate_accuracy
    if not torch.cuda.is_available():raise RuntimeError('CUDA is required for this declared run')
    torch.set_num_threads(4);keras.utils.set_random_seed(20261102)
    keras.utils.disable_interactive_logging()
    plate=load_plate_config_from_yaml(assets['cct_s_v2_global_plate_config.yaml'])
    architecture=load_model_config_from_yaml(assets['cct_s_v2_global_model_config.yaml'])
    model=build_model(architecture,plate,enable_region_head=True)
    model.load_weights(assets['cct_s_v2_global.keras'],skip_mismatch=False)
    if not any('cuda' in str(var.value.device) for var in model.trainable_variables):raise RuntimeError('Model is not on CUDA')
    model.compile(optimizer=keras.optimizers.AdamW(learning_rate=args.lr),
                  loss={'plate':cce_loss(plate.vocabulary_size,label_smoothing=0.),'region':keras.losses.CategoricalCrossentropy()},
                  loss_weights={'plate':1.,'region':0.})
    x=np.full((2,plate.img_height,plate.img_width,3),180,np.uint8)
    y=np.stack([target_transform('51A12345',plate.max_plate_slots,plate.alphabet,plate.pad_char)]*2)
    region=np.zeros((2,len(plate.plate_regions)),np.float32);region[:,plate.plate_regions.index('Vietnam')]=1
    sanity=model.train_on_batch(x,{'plate':y,'region':region},return_dict=True)
    if not all(np.isfinite(value).all() for value in sanity.values()):raise RuntimeError('Sanity loss is nonfinite')
    print('Strict pretrained weight load and CUDA forward/backward passed:',sanity,flush=True)
    del model;keras.backend.clear_session();torch.cuda.empty_cache()
    run.mkdir(parents=True)
    save_augmentation(run/'augmentation.yaml',20261102)
    started=time.monotonic();stopped=threading.Event()
    status={'state':'training','started_at':datetime.now(timezone.utc).isoformat(),'pid':os.getpid(),
        'manifest_sha256':sha(manifest_path),'assets':{name:{'url':BASE+name,'sha256':expected} for name,expected in ASSETS.items()},
        'verified_training_validation_images':verified_images,
        'dependency_lock_sha256':sha(ROOT/'requirements-ocr-train-lock.txt'),
        'training_source_sha256':sha(Path(__file__)),
        'primary_metric':'Per-sample whole-plate slot exact accuracy; fixes upstream batch-mean weighting. Auxiliary metrics remain upstream batch means; region head has zero loss weight.',
        'augmentation_seed_persisted':20261102,
        'data_csv_sha256':{s:sha(data/(s+'.csv')) for s in ('train','val')},'seed':20261102,
        'settings':{'epochs_max':args.epochs,'batch':args.batch,'learning_rate':args.lr,'early_stopping_patience':6,
                    'region_loss_weight':0.,'plate_loss_weight':1.,'mixed_precision':'mixed_float16'},
        'runtime':{'keras':keras.__version__,'torch':torch.__version__,'gpu':torch.cuda.get_device_name(0)},
        'sanity':{key:float(value) for key,value in sanity.items()}}
    def write_status():
        while not stopped.is_set():
            try:
                status.update(training_progress(run));status['elapsed_seconds']=time.monotonic()-started
                temporary=run/'live.tmp';temporary.write_text(json.dumps(status,indent=2),encoding='utf-8',newline='\n')
                temporary.replace(run/'live.json')
            except (OSError,ValueError):pass  # CSV may be between an epoch write and flush.
            stopped.wait(10)
    monitor=threading.Thread(target=write_status,daemon=True);monitor.start()
    arguments=['--model-config-file',str(assets['cct_s_v2_global_model_config.yaml']),
        '--plate-config-file',str(assets['cct_s_v2_global_plate_config.yaml']),
        '--annotations',str(data/'train.csv'),'--val-annotations',str(data/'val.csv'),
        '--augmentation-path',str(run/'augmentation.yaml'),'--epochs',str(args.epochs),'--batch-size',str(args.batch),
        '--lr',str(args.lr),'--weight-decay','0.0005','--label-smoothing','0.0',
        '--plate-loss-weight','1.0','--region-loss-weight','0.0','--seed','20261102',
        '--workers','2','--max-queue-size','4','--early-stopping-patience','6',
        '--mixed-precision-policy','mixed_float16','--weights-path',str(assets['cct_s_v2_global.keras']),
        '--output-dir',str(run)]
    try:
        train.main(args=arguments,standalone_mode=False)
        status.update(training_progress(run));status['state']='complete'
        selected=ROOT/status['checkpoint_dir']/'best.keras'
        status['best_checkpoint_sha256']=sha(selected)
        status['last_checkpoint_sha256']=sha(selected.with_name('last.keras'))
    except BaseException as error:
        status.update(state='failed',error=type(error).__name__+': '+str(error))
        raise
    finally:
        stopped.set();monitor.join(timeout=12)
        status['elapsed_seconds']=time.monotonic()-started
        (run/'live.json').write_text(json.dumps(status,indent=2),encoding='utf-8',newline='\n')
        (run/'training_report.json').write_text(json.dumps(status,indent=2),encoding='utf-8',newline='\n')
    print(json.dumps(status,indent=2),flush=True)


if __name__=='__main__':main()
