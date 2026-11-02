"""Compare original Torch checkpoint decoding with its exported FP32 ONNX."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.export_ocr import decode_texts
from scripts.train_ocr import sha


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--export-report',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Parity evidence already exists')
    os.environ['KERAS_BACKEND']='torch'
    os.environ.setdefault('OMP_NUM_THREADS','2')
    import cv2
    import keras
    import numpy as np
    import onnxruntime as ort
    import torch
    from fast_plate_ocr.train.model.model_builders import build_model
    from fast_plate_ocr.train.model.model_schema import load_model_config_from_yaml
    from fast_plate_ocr.train.model.config import load_plate_config_from_yaml
    torch.set_num_threads(2)
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    report=json.loads(args.export_report.read_text(encoding='utf-8'))
    checkpoint=ROOT/Path(report['checkpoint'].replace('\\','/'))
    assert sha(checkpoint)==report['checkpoint_sha256']
    onnx=args.export_report.with_suffix('.onnx');assert sha(onnx)==report['onnx_sha256']
    manifest_path=ROOT/'reports/ocr_finetune_manifest.json';assert sha(manifest_path)==report['manifest_sha256']
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    lookup={r['member']:r for r in manifest['samples'] if r['split']=='val'}
    selected=[lookup[r['member']] for r in report['results']]
    assert len(selected)==32 and len({r['member'] for r in selected})==32
    images=[]
    for row in selected:
        assert sha(ROOT/row['image'])==row['image_sha256']
        image=cv2.cvtColor(cv2.imread(str(ROOT/row['image'])),cv2.COLOR_BGR2RGB)
        images.append(cv2.resize(image,(128,64),interpolation=cv2.INTER_LINEAR))
    folder=ROOT/'models/training'
    plate=load_plate_config_from_yaml(folder/'cct_s_v2_global_plate_config.yaml')
    config=load_model_config_from_yaml(folder/'cct_s_v2_global_model_config.yaml')
    options=ort.SessionOptions();options.intra_op_num_threads=2
    session=ort.InferenceSession(str(onnx),sess_options=options,providers=['CPUExecutionProvider'])
    results={}
    for precision in ('float32','mixed_float16'):
        keras.backend.clear_session();keras.mixed_precision.set_global_policy(precision)
        model=build_model(config,plate,enable_region_head=True);model.load_weights(checkpoint,skip_mismatch=False)
        rows=[];difference=0.
        for start in range(0,len(images),8):
            batch=np.stack(images[start:start+8])
            with torch.no_grad():predicted=model(batch,training=False)
            torch_probs=keras.ops.convert_to_numpy(predicted['plate'])
            onnx_probs=session.run(['plate'],{session.get_inputs()[0].name:batch})[0]
            difference=max(difference,float(np.max(np.abs(torch_probs.astype(np.float32)-onnx_probs))))
            first=decode_texts(torch_probs,plate.alphabet,plate.max_plate_slots)
            second=decode_texts(onnx_probs,plate.alphabet,plate.max_plate_slots)
            rows.extend({'member':r['member'],'torch':a,'onnx':b,'same':a==b}
                        for r,a,b in zip(selected[start:start+8],first,second))
        results[precision]={'same':sum(r['same'] for r in rows),'samples':len(rows),
            'max_absolute_probability_difference':difference,'device':str(model.trainable_variables[0].value.device),'results':rows}
        del model;keras.backend.clear_session();torch.cuda.empty_cache()
    evidence={'checkpoint_sha256':sha(checkpoint),'onnx_sha256':sha(onnx),'source_sha256':sha(Path(__file__)),
        'selection':'Same32 validation IDs as the TF-FP32 export check; no final data.',
        'runtime':{'keras':keras.__version__,'torch':torch.__version__,'onnxruntime':ort.__version__},'results':results}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(evidence,indent=2),encoding='utf-8',newline='\n')
    print(json.dumps({p:{k:v for k,v in r.items() if k!='results'} for p,r in results.items()},indent=2),flush=True)
    if results['float32']['same']!=32:raise ValueError('Original Torch FP32 differs from exported decoding; investigate before selection')


if __name__=='__main__':main()
