"""Render measured learning curves and final paired OCR results for the report."""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
REPORTS=ROOT/'reports'


def main():
    read=lambda name:json.loads((REPORTS/(name+'.json')).read_text(encoding='utf-8'))
    training=read('ocr_finetune_training')
    with (REPORTS/'ocr_finetune_log.csv').open(encoding='utf-8-sig',newline='') as stream:
        rows=list(csv.DictReader(stream))
    assert len(rows)==training['completed_epochs']
    epochs=[int(float(row['epoch']))+1 for row in rows]
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':12,'axes.titlesize':10.5,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(8,2.75),layout='constrained')
    for name,label,color in [('plate_acc','Train','#2269a8'),('val_plate_acc','Validation','#c15719')]:
        axes[0].plot(epochs,[100*float(row[name]) for row in rows],label=label,color=color,marker='.',lw=1.5)
    for name,label,color in [('loss','Train','#2269a8'),('val_loss','Validation','#c15719')]:
        axes[1].plot(epochs,[float(row[name]) for row in rows],label=label,color=color,marker='.',lw=1.5)
    axes[0].set(ylabel='Exact accuracy (%)',xlabel='Epoch',title='Per-sample metric used for selection')
    axes[1].set(ylabel='Categorical cross-entropy',xlabel='Epoch',title='Training and validation loss')
    for ax in axes:
        ax.axvline(training['best_epoch'],color='#444444',ls='--',lw=1,label='Selected epoch')
        ax.set_xticks(range(1,len(rows)+1,2));ax.grid(alpha=.2);ax.legend(fontsize=10.5)
        ax.tick_params(axis='both',labelsize=10.5)
    fig.savefig(REPORTS/'ocr_finetune_learning.png',dpi=180);plt.close(fig)

    release=read('ocr_finetune_release');test=read('ocr_finetune_test')
    names=['Baseline\n1.4','Fine-tuned\n'+release['candidate_mode']]
    items=[test['results'][key] for key in ('baseline',release['candidate_mode'])]
    fig,axes=plt.subplots(1,3,figsize=(8,2.75),layout='constrained')
    values=[100*r['exact_match'] for r in items]
    intervals=np.array([[100*(r['exact_match']-r['wilson95'][0]),100*(r['wilson95'][1]-r['exact_match'])] for r in items]).T
    axes[0].bar(names,values,color=['#8393a0','#2269a8'],yerr=intervals,capsize=4)
    axes[0].set(ylim=(0,105),ylabel='Crop exact match (%)',title=f'Final test: {items[0]["samples"]} unique plates')
    for x,(r,y) in enumerate(zip(items,values)):
        axes[0].text(x,y-18,f'{r["correct"]}/{r["samples"]}\n{y:.2f}%',ha='center',color='black' if x==0 else 'white',fontsize=10.5)
    for ax,key,title in [(axes[1],'cer','Character error rate (%)'),(axes[2],'latency_p95_ms','OCR p95 latency (ms)')]:
        values=[r[key]*(100 if key=='cer' else 1) for r in items]
        ax.bar(names,values,color=['#8393a0','#2269a8']);ax.set(title=title,ylim=(0,max(values)*1.3))
        for x,y in enumerate(values):ax.text(x,y+max(values)*.04,f'{y:.3f}',ha='center',fontsize=10.5)
    for ax in axes:ax.tick_params(axis='both',labelsize=10.5);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    fig.savefig(REPORTS/'ocr_finetune_comparison.png',dpi=180);plt.close(fig)


if __name__=='__main__':main()
