"""Export FP32 OCR and verify dynamic batches and decoded validation parity."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.train_ocr import sha


def decode_texts(probabilities,alphabet,slots):
    import numpy as np
    indices=np.asarray(probabilities).reshape(-1,slots,len(alphabet)).argmax(axis=-1)
    return [''.join(alphabet[index] for index in row).rstrip('_') for row in indices]


def export_paths(output):
    fp32=output.with_name(output.stem+'-fp32.keras')
    for path in (output,output.with_suffix('.json'),fp32,output.with_suffix('.raw.onnx')):
        if path.exists():raise FileExistsError('Preserve existing artifact: '+str(path))
    return fp32


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--checkpoint',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not args.checkpoint.is_file():parser.error('Checkpoint not found')
    try:keras_path=export_paths(args.output)
    except FileExistsError as error:parser.error(str(error))
    os.environ['KERAS_BACKEND']='tensorflow'
    os.environ['CUDA_VISIBLE_DEVICES']='-1'
    os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
    os.environ['TF_ENABLE_ONEDNN_OPTS']='0'
    os.environ.setdefault('OMP_NUM_THREADS','2')
    import cv2
    import keras
    import numpy as np
    import onnx
    import onnxruntime as ort
    import onnxslim
    import tensorflow as tf
    from fast_plate_ocr import LicensePlateRecognizer
    from fast_plate_ocr.train.model.model_builders import build_model
    from fast_plate_ocr.train.model.model_schema import load_model_config_from_yaml
    from fast_plate_ocr.train.model.config import load_plate_config_from_yaml
    tf.config.threading.set_intra_op_parallelism_threads(2)
    tf.config.threading.set_inter_op_parallelism_threads(2)
    keras.mixed_precision.set_global_policy('float32')
    folder=ROOT/'models/training'
    plate=load_plate_config_from_yaml(folder/'cct_s_v2_global_plate_config.yaml')
    model=build_model(load_model_config_from_yaml(folder/'cct_s_v2_global_model_config.yaml'),plate,enable_region_head=True)
    model.load_weights(args.checkpoint,skip_mismatch=False)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    model.save(keras_path)
    shape=(None,plate.img_height,plate.img_width,plate.num_channels)
    temporary=args.output.with_suffix('.raw.onnx')
    # Use Keras' export API directly: upstream NamedTemporaryFile cannot be reopened on Windows.
    model.export(temporary,format='onnx',verbose=False,
                 input_signature=[keras.InputSpec(name='input',shape=shape,dtype='uint8')],opset_version=18)
    graph=onnxslim.slim(onnx.load(temporary))
    originals=list(graph.graph.output);del graph.graph.output[:]
    for item,name in zip(originals,model.output):
        if item.name!=name:
            graph.graph.node.append(onnx.helper.make_node('Identity',[item.name],[name],name='name_'+name))
        alias=onnx.ValueInfoProto();alias.CopyFrom(item);alias.name=name;graph.graph.output.append(alias)
    onnx.checker.check_model(graph)
    onnx.save_model(graph,args.output,save_as_external_data=False)
    temporary.unlink()
    options=ort.SessionOptions();options.intra_op_num_threads=2
    session=ort.InferenceSession(str(args.output),sess_options=options,providers=['CPUExecutionProvider'])
    recognizer=LicensePlateRecognizer(onnx_model_path=args.output,
        plate_config_path=folder/'cct_s_v2_global_plate_config.yaml',providers=['CPUExecutionProvider'],sess_options=options)
    manifest_path=ROOT/'reports/ocr_finetune_manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    selected=sorted([r for r in manifest['samples'] if r['split']=='val'],
        key=lambda r:hashlib.sha256(('export-parity-20261102:'+r['member']).encode()).hexdigest())[:32]
    if len(selected)!=32:raise ValueError('Need32 validation examples for export parity')
    images=[]
    for row in selected:
        if sha(ROOT/row['image'])!=row['image_sha256']:raise ValueError('Validation pixels changed')
        image=cv2.cvtColor(cv2.imread(str(ROOT/row['image'])),cv2.COLOR_BGR2RGB)
        images.append(cv2.resize(image,(plate.img_width,plate.img_height),interpolation=cv2.INTER_LINEAR))
    max_difference=0.;rows=[]
    for size in (1,2,8):
        for start in range(0,len(images),size):
            batch=np.stack(images[start:start+size])
            predicted=model(batch,training=False)
            expected={key:keras.ops.convert_to_numpy(value) for key,value in predicted.items()}
            actual=dict(zip([o.name for o in session.get_outputs()],session.run(None,{session.get_inputs()[0].name:batch})))
            for key in expected:
                difference=float(np.max(np.abs(expected[key]-actual[key])))
                max_difference=max(max_difference,difference)
                if not np.allclose(expected[key],actual[key],rtol=2e-4,atol=2e-4):
                    raise ValueError(f'Keras/ONNX numerical mismatch: {key}, max_abs={difference}')
            keras_text=decode_texts(expected['plate'],plate.alphabet,plate.max_plate_slots)
            onnx_text=[r.plate for r in recognizer.run(list(batch),return_confidence=True)]
            if keras_text!=onnx_text:raise ValueError('Serving decoder differs from Keras')
            if size==8:
                rows.extend({'member':row['member'],'keras':a,'onnx':b} for row,a,b in zip(selected[start:start+size],keras_text,onnx_text))
    report={'checkpoint':str(args.checkpoint.resolve().relative_to(ROOT)),'checkpoint_sha256':sha(args.checkpoint),
        'onnx_sha256':sha(args.output),'fp32_keras_sha256':sha(keras_path),
        'manifest_sha256':sha(manifest_path),'export_source_sha256':sha(Path(__file__)),
        'runtime':{'keras':keras.__version__,'tensorflow':tf.__version__,'onnx':onnx.__version__,'onnxruntime':ort.__version__},
        'model_parameters':model.count_params(),'input':session.get_inputs()[0].shape,
        'outputs':{o.name:o.shape for o in session.get_outputs()},'precision':'FP32 rebuilt from saved weights; CPU parity',
        'validated_unique_validation_samples':len(selected),'validated_batch_sizes':[1,2,8],
        'max_absolute_difference':max_difference,'decoded_parity':True,'results':rows}
    args.output.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf-8',newline='\n')
    print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2),flush=True)


if __name__=='__main__':main()
