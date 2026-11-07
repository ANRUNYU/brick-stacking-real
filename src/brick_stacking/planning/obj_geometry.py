"""Strict triangle-only OBJ parsing; never loads material or external files."""
import numpy as np


def obj_triangles(data):
    vertices=[];triangles=[]
    for line in data.decode('utf-8-sig').splitlines():
        tokens=line.split('#',1)[0].split()
        if not tokens:continue
        if tokens[0]=='v':
            if len(tokens)!=4:raise ValueError('explicit xyz OBJ vertices required')
            vertices.append([float(x) for x in tokens[1:]])
        elif tokens[0]=='f':
            if len(tokens)!=4:raise ValueError('triangulated OBJ required; no implicit polygon fan')
            face=[]
            for token in tokens[1:]:
                index=int(token.split('/')[0])
                if index==0:raise ValueError('OBJ zero index')
                index=index-1 if index>0 else len(vertices)+index
                if not 0<=index<len(vertices):raise ValueError('OBJ face index out of range')
                face.append(index)
            triangles.append(face)
    v,t=np.asarray(vertices,float),np.asarray(triangles,int)
    if v.ndim!=2 or v.shape[1]!=3 or not np.isfinite(v).all() or t.ndim!=2 or t.shape[1]!=3:
        raise ValueError('finite nonempty triangle OBJ required')
    return v,t
