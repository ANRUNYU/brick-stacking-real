"""Compose explicitly calibrated/declared mechanical tool poses, no TCP guess."""
def attach_tool_poses(tip_pose,tip_tool_root,tool_local_poses):
    root=tip_pose.compose(tip_tool_root)
    if not tool_local_poses:raise ValueError('explicit tool link poses required')
    result={}
    for name,local in tool_local_poses.items():
        if local.source_frame!=name:raise ValueError('named tool frame mismatch')
        result[name]=root.compose(local)
    return result
