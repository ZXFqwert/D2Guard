"""Exact Jaccard membership with cached NumPy posting lists, not approximation."""
import collections
import numpy as np
from stage_d_prime_isolation import grams


class FastIndex:
    def __init__(self):
        self.parts={}

    def add(self,text,identity,split):
        p=self.parts.setdefault(split,{'lengths':[],'ids':[],'postings':collections.defaultdict(list),'arrays':{},'sizes':None})
        g=grams(text);i=len(p['ids']);p['ids'].append(identity);p['lengths'].append(len(g));p['sizes']=None
        for gram in g:
            p['postings'][gram].append(i);p['arrays'].pop(gram,None)

    def match(self,text,split,threshold=.5):
        g=grams(text)
        for previous,p in self.parts.items():
            if previous==split:continue
            arrays=[]
            for gram in g:
                if gram not in p['postings']:continue
                if gram not in p['arrays']:p['arrays'][gram]=np.asarray(p['postings'][gram],dtype=np.int32)
                arrays.append(p['arrays'][gram])
            if not arrays:continue
            counts=np.bincount(np.concatenate(arrays),minlength=len(p['ids']))
            if p['sizes'] is None:p['sizes']=np.asarray(p['lengths'],dtype=np.int64)
            # Same integer intersection/union and floating division as Index.
            possible=np.flatnonzero(counts)
            score=counts[possible]/(len(g)+p['sizes'][possible]-counts[possible])
            hits=possible[score>=threshold]
            if len(hits):return p['ids'][int(hits[0])]
        return None


def batched_maximum(reference,queries,check_budget=lambda:None):
    """BLAS matrix multiply, preserving legacy GEMV decisions near the gate."""
    result=[]
    for start in range(0,len(queries),128):
        check_budget();part=queries[start:start+128]
        maximum=(part@reference.T).max(axis=1)
        # Different BLAS accumulation orders can differ by a few ULPs.
        for j in np.flatnonzero(np.abs(maximum-.9)<1e-4):
            maximum[j]=(reference@part[j]).max()
        result.extend(maximum)
    return np.asarray(result)
