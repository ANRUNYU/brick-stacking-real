"""Relative geometric proposal ranking, not calibrated pose confidence."""
import numpy as np


def cube_geometry_error(candidate, edge_m):
    sizes=candidate.get('footprint_size_m')
    if sizes is None or len(sizes)!=2 or not np.isfinite(sizes).all() or min(sizes)<=0:
        return float('inf')
    sizes=np.asarray(sizes,float)
    scale=np.sum(np.log(sizes/edge_m)**2)
    aspect=2*np.log(sizes[0]/sizes[1])**2
    fill=(1-float(candidate.get('footprint_fill_ratio',1.)))**2
    return float(scale+aspect+fill)
