##--------------------------------------------------------------------------
## ScriptName : instantQPatch
## Contents   : smart hole patching utility designed for polygonal meshes.
## Author     : Joe Wu
## URL        : http://im3djoe.com
## Since      : 2025/07
## Version    : 1.0  First version for public test
## Install    : copy and paste entire code to a pyhotn script editor run it.
##              drag entire code to shelf to make a button.
##--------------------------------------------------------------------------

import maya.cmds as mc
import maya.mel as mel
import re, math
from collections import defaultdict

def checkFlatLoop(vtx_list, flat_threshold):
    n = len(vtx_list)
    angle_data = []
    for i, v in enumerate(vtx_list):
        if i == 0 or i == n - 1:
            angle = 180.0
            deviation = abs(angle - 90.0)
            angle_data.append((i, v, angle, deviation))
            continue
        prev_pt = mc.xform(vtx_list[i - 1], q=True, ws=True, t=True)
        cur_pt  = mc.xform(vtx_list[i],     q=True, ws=True, t=True)
        next_pt = mc.xform(vtx_list[i + 1], q=True, ws=True, t=True)
        v1 = [prev_pt[j] - cur_pt[j] for j in range(3)]
        v2 = [next_pt[j] - cur_pt[j] for j in range(3)]
        m1 = math.sqrt(sum(x*x for x in v1))
        m2 = math.sqrt(sum(x*x for x in v2))
        if m1 == 0 or m2 == 0:
            angle = 90.0
        else:
            cosang = sum(a*b for a,b in zip(v1,v2)) / (m1*m2)
            angle = math.degrees(math.acos(max(-1.0, min(1.0, cosang))))

        deviation = abs(angle - 90.0)
        angle_data.append((i, v, angle, deviation))
    angles = [t[2] for t in angle_data]
    diffs = [angles[i] - angles[i+1] for i in range(len(angles)-1)]
    abs_diffs = [abs(d) for d in diffs]
    if not abs_diffs:
        return 0

    avg_abs_diff = sum(abs_diffs) / len(abs_diffs)
    return 1 if avg_abs_diff < flat_threshold else 0



def segmentsAdaptiveOpen(vtx_list, similarity_threshold=5.0, corner_threshold=30.0):
    k = 3
    n = len(vtx_list)
    if n < k:
        return [], [], [], []
    angle_data = []
    for i, v in enumerate(vtx_list):
        if i in (0, n - 1):
            angle_data.append((i, v, 180.0, 90.0))
            continue
        prev_pt = mc.xform(vtx_list[i - 1], q=True, ws=True, t=True)
        cur_pt  = mc.xform(vtx_list[i],     q=True, ws=True, t=True)
        next_pt = mc.xform(vtx_list[i + 1], q=True, ws=True, t=True)
        v1 = [prev_pt[j] - cur_pt[j] for j in range(3)]
        v2 = [next_pt[j] - cur_pt[j] for j in range(3)]
        m1 = math.sqrt(sum(x * x for x in v1))
        m2 = math.sqrt(sum(x * x for x in v2))
        if m1 == 0 or m2 == 0:
            angle = 90.0
        else:
            cosang = sum(a * b for a, b in zip(v1, v2)) / (m1 * m2)
            angle = math.degrees(math.acos(max(-1.0, min(1.0, cosang))))
            
        deviation = abs(angle - 90.0)
        angle_data.append((i, v, angle, deviation))
    deviations = [d for (_, _, _, d) in angle_data if d != 90.0]
    if deviations and (max(deviations) - min(deviations) <= similarity_threshold):
        corner_idxs = [int(i * n / k) for i in range(k)]
    else:
        candidates = [item for item in angle_data
                      if (item[3] <= corner_threshold and item[0] not in (0, n - 1))]
        if len(candidates) >= k:
            candidates = sorted(candidates, key=lambda x: x[3])[:k]
        else:
            interior = [item for item in angle_data if item[0] not in (0, n - 1)]
            candidates = sorted(interior, key=lambda x: x[3])[:k]
        candidates.sort(key=lambda x: x[0])
        corner_idxs = [item[0] for item in candidates]
    if len(corner_idxs) != k:
        interior = [item for item in angle_data if item[0] not in (0, n - 1)]
        fb = sorted(interior, key=lambda x: x[3])[:k]
        fb.sort(key=lambda x: x[0])
        corner_idxs = [item[0] for item in fb]
    corner_vertices  = [vtx_list[i] for i in corner_idxs]
    corner_positions = [mc.xform(v, q=True, ws=True, t=True) for v in corner_vertices]
    sharp = [i for (i, v, ang, dev) in angle_data
             if (dev <= corner_threshold and i not in (0, n - 1))]

    if len(sharp) == 2:
        c0, c1 = sorted(sharp)
        seg0 = []
        idx = c0
        while True:
            seg0.append(vtx_list[idx])
            if idx == c1:
                break
            idx += 1
        seg1 = vtx_list[0: c0 + 1]
        seg2 = vtx_list[c1:]
        l1, l2 = len(seg1), len(seg2)
        if l1 > l2:
            seg1 = seg1[l1 - l2:]
        elif l2 > l1:
            seg2 = seg2[:l1]
        init_segments = [seg0, seg1, seg2]
    else:
        base = n // 3
        rem  = n % 3
        lengths = [base, base, base]
        start   = rem - 1
        for i in range(rem):
            lengths[(start + i) % 3] += 1
        lengths[0], lengths[1] = lengths[1], lengths[0]

        seg0 = vtx_list[0: lengths[0]]
        seg1 = vtx_list[lengths[0] - 1: lengths[0] + lengths[1] + 1]
        seg2 = vtx_list[lengths[0] + lengths[1] - 1: -1]
        init_segments = [seg1, seg0, seg2]
    segments_pos = [[mc.xform(vtx, q=True, ws=True, t=True) for vtx in seg]
                    for seg in init_segments]
    return init_segments, segments_pos, corner_vertices, corner_positions


def instantQPatchOpen():
    #autoModeState = mc.checkBox('QPatchAutoMode', q=1 ,v=1)
    cleanList = ('innerLoop','oldSelLoop')
    for c in cleanList:
        if mc.objExists(c):
            mc.delete(c)
    selEdge = mc.filterExpand(sm = 32)
    if selEdge:
        selShape = mc.ls(selEdge[0], objectsOnly=True)[0]
        transNode = mc.listRelatives(selShape, parent=True)
        selGeo = transNode[0]
        cmd  = 'doMenuComponentSelectionExt("' + selGeo + '", "edge", 0);'  
        mel.eval(cmd)
        mc.displaySmoothness(selGeo, divisionsU=0, divisionsV=0, pointsWire=4, pointsShaded=1, polygonObject=1)
        mc.nurbsToPolygonsPref(polyType=1, format=2, uType=3, uNumber=1, vType=3, vNumber=1)
        curves = []
        segments_pos = []
        checkLoopSize = getEdgeRingGroupList(selEdge)
        if len(checkLoopSize) == 1:
            getCircleState, listSelVtx = vtxLoopOrderCheck(selEdge)  
            flatState = checkFlatLoop(listSelVtx, 5)
            if getCircleState == 0:
                if flatState == 0:
                    getCircleState, listSelVtx = vtxLoopOrderCheck(selEdge)  
                    segments, segments_pos, corner_verts, corner_pos = segmentsAdaptiveOpen(listSelVtx,similarity_threshold=35.0,corner_threshold=55.0)
                else:
                    mc.polySelectConstraint(disable=True)
                    mc.polySelectConstraint(m=2, w=2, t=0x8000)
                    selInner = mc.ls(sl=True, fl=True)
                    mc.select(selEdge, r=True)
                    mc.polySelectConstraint(m=2, w=1, t=0x8000)
                    selBorder = mc.ls(sl=True, fl=True)
                    mc.select(selEdge, r=True)
                    if len(selInner) > len(selBorder):
                        mc.polySelectConstraint(pp=5, t=0x8000)
                        mc.polySelectConstraint(m=0, w=0)
                        mc.polySelectConstraint(disable=True)
                    else:
                        mc.polySelectConstraint(pp=1, m=2, w=1, t=0x8000)
                        mc.polySelectConstraint(m=0, w=0)
                        mc.polySelectConstraint(disable=True)
                        selEdge = mc.filterExpand(sm = 32)
                        getCircleState, listSelVtx = vtxLoopOrderCheck(selEdge)  
                        seg0 = listSelVtx[0:2]
                        seg1 = listSelVtx[1:-1]
                        seg2 = (listSelVtx[-2],listSelVtx[-1])
                        init_segments = [seg1, seg0, seg2]
                        segments_pos = [[mc.xform(vtx, q=True, ws=True, t=True) for vtx in seg]
                                        for seg in init_segments]

                curves = create_segment_curves(segments_pos, degree=1, close_loop=False)
                if curves:
                    mc.singleProfileBirailSurface(curves[0],curves[1],curves[2],ch=1, po=1, tm=1, tp1=0)
                    mc.delete(curves)
                    newMesh = mc.ls(sl=1)
                    mc.ConvertSelectionToEdges()
                    mc.sets(name='oldSelLoop', text='oldSelLoop')
                    mc.select(newMesh)           
                    mc.select(selGeo, add=True)
                    mc.polyUnite(ch=0, mergeUVSets=1, name=selGeo)
                    newName = mc.ls(selection=True)
                    mc.polyMergeVertex(distance= 0.001, am=True, ch=0)
                    mc.rename(newName[0], selGeo)
                    mc.polyNormal(selGeo,normalMode=2, userNormalMode=0, ch=0)
                    mc.SetToFaceNormals()
                    mc.select('oldSelLoop')
                    cmd  = 'doMenuComponentSelectionExt("' + selGeo  + '", "edge", 0);'  
                    mel.eval(cmd)
                    mc.polySelectConstraint(m=2, w=1, t=0x8000)
                    mc.polySelectConstraint(disable=True)


    
def segmentsPositions(vtx_list, initial_verts):
    n = len(vtx_list)
    len0 = len(initial_verts)
    if n < 4 or len0 < 1:
        return [], []
    init_set = set(initial_verts)
    start_idx = None
    for s in range(n):
        block = [vtx_list[(s + j) % n] for j in range(len0)]
        if set(block) == init_set:
            start_idx = s
            break
    if start_idx is None:
        return [], []
    rotated = [vtx_list[(start_idx + i) % n] for i in range(n)]
    half = n // 2
    len1 = half - len0
    if len1 < 0:
        return [], []
    len2 = len0
    len3 = len1
    seg0 = rotated[0:len0]
    start1 = len0 - 1
    end1 = len0 + len1 + 1
    seg1 = rotated[start1:end1]
    start2 = end1 - 1
    end2 = start2 + len2
    seg2 = rotated[start2:end2]
    last2 = end2 - 1
    seg3_body = rotated[last2 + 1:]
    seg3 = [rotated[last2]] + seg3_body + [rotated[0]]
    segments = [seg0, seg1, seg2, seg3]
    segments_pos = [
        [mc.xform(v, q=True, ws=True, t=True) for v in seg]
        for seg in segments
    ]
    return segments, segments_pos


def getEdgeRingGroupList(selEdges):
    if not selEdges:
        return []
    transform = selEdges[0].split('.')[0]
    e2v = {}
    v2e = defaultdict(set)
    infos = mc.polyInfo(selEdges, ev=True) or []
    for info in infos:
        nums = list(map(int, re.findall(r"\d+", info)))
        if len(nums) < 3:
            continue
        edge_idx, v1, v2 = nums[0], nums[1], nums[2]
        e2v[edge_idx] = (v1, v2)
        v2e[v1].add(edge_idx)
        v2e[v2].add(edge_idx)
    groups = []
    for start in list(e2v.keys()):
        verts = e2v.pop(start, None)
        if verts is None:
            continue
        v1, v2 = verts
        v2e[v1].discard(start)
        v2e[v2].discard(start)
        ring = [start]
        for initial_vert, prepend in ((v2, False), (v1, True)):
            current = initial_vert
            while True:
                adj = v2e.get(current)
                if not adj or len(adj) != 1:
                    break
                nxt = adj.pop()
                verts = e2v.pop(nxt, None)
                if verts is None:
                    break
                a, b = verts
                v2e[a].discard(nxt)
                v2e[b].discard(nxt)
                if prepend:
                    ring.insert(0, nxt)
                    current = b if a == current else a
                else:
                    ring.append(nxt)
                    current = b if a == current else a

        groups.append(ring)
    result = []
    for ring in groups:
        result.append([f"{transform}.e[{e}]" for e in ring])
    return result
    
def vtxLoopOrderCheck(selEdges):
    shapeNode = mc.listRelatives(selEdges[0], fullPath=True , parent=True )
    transformNode = mc.listRelatives(shapeNode[0], fullPath=True , parent=True )
    edgeNumberList = []
    for a in selEdges:
        checkNumber = ((a.split('.')[1]).split('\n')[0]).split(' ')
        for c in checkNumber:
            findNumber = ''.join([n for n in c.split('|')[-1] if n.isdigit()])
            if findNumber:
                edgeNumberList.append(findNumber)
    getNumber = []
    for s in selEdges:
        evlist = mc.polyInfo(s,ev=True)
        checkNumber = ((evlist[0].split(':')[1]).split('\n')[0]).split(' ')
        for c in checkNumber:
            findNumber = ''.join([n for n in c.split('|')[-1] if n.isdigit()])
            if findNumber:
                getNumber.append(findNumber)
    dup = set([x for x in getNumber if getNumber.count(x) > 1])
    getHeadTail = list(set(getNumber) - dup)
    checkCircleState = 0
    if not getHeadTail:
        checkCircleState = 1
        getHeadTail.append(getNumber[0])
    vftOrder = []
    vftOrder.append(getHeadTail[0])
    count = 0
    while len(dup)> 0 and count < 1000:
        checkVtx = transformNode[0]+'.vtx['+ vftOrder[-1] + ']'
        velist = mc.polyInfo(checkVtx,ve=True)
        getNumber = []
        checkNumber = ((velist[0].split(':')[1]).split('\n')[0]).split(' ')
        for c in checkNumber:
            findNumber = ''.join([n for n in c.split('|')[-1] if n.isdigit()])
            if findNumber:
                getNumber.append(findNumber)
        findNextEdge = []
        for g in getNumber:
            if g in edgeNumberList:
                findNextEdge = g
        edgeNumberList.remove(findNextEdge)
        checkVtx = transformNode[0]+'.e['+ findNextEdge + ']'
        findVtx = mc.polyInfo(checkVtx,ev=True)
        getNumber = []
        checkNumber = ((findVtx[0].split(':')[1]).split('\n')[0]).split(' ')
        for c in checkNumber:
            findNumber = ''.join([n for n in c.split('|')[-1] if n.isdigit()])
            if findNumber:
                getNumber.append(findNumber)
        gotNextVtx = []
        for g in getNumber:
            if g in dup:
                gotNextVtx = g
        dup.remove(gotNextVtx)
        vftOrder.append(gotNextVtx)
        count +=  1
    if checkCircleState == 0:
        vftOrder.append(getHeadTail[1])
    else:
        if vftOrder[0] == vftOrder[1]:
            vftOrder = vftOrder[1:]
        elif vftOrder[0] == vftOrder[-1]:
            vftOrder = vftOrder[0:-1]
    finalList = []
    for v in vftOrder:
        finalList.append(transformNode[0]+'.vtx['+ v + ']' )

    return checkCircleState, finalList


def create_segment_curves(segments_pos, degree=1, close_loop=False, name_prefix="segmentCurve"):
    curve_names = []
    for i, pts in enumerate(segments_pos, start=1):
        pts_for_curve = list(pts)
        if close_loop:
            pts_for_curve.append(pts[0])
        curve_name = f"{name_prefix}_{i}"
        curve = mc.curve(p=pts_for_curve, degree=degree, n=curve_name)
        curve_names.append(curve)
    return curve_names

def get_shortest_edge(edge_list):
    shortest_edge = None
    shortest_length = float('inf')
    for e in edge_list:
        verts = mc.polyListComponentConversion(e, fromEdge=True, toVertex=True)
        verts = mc.ls(verts, flatten=True)
        if len(verts) != 2:
            continue
        p1 = mc.xform(verts[0], q=True, ws=True, t=True)
        p2 = mc.xform(verts[1], q=True, ws=True, t=True)
        dx, dy, dz = (p2[0]-p1[0], p2[1]-p1[1], p2[2]-p1[2])
        length = math.sqrt(dx*dx + dy*dy + dz*dz)
        
        if length < shortest_length:
            shortest_length = length
            shortest_edge = e
    
    return shortest_edge, shortest_length


def segmentsPositions_adaptive(vtx_list,
                                        similarity_threshold=5.0,
                                        corner_threshold=30.0):
    n = len(vtx_list)
    if n < 4:
        return [], [], [], []
    angle_data = []
    for i, v in enumerate(vtx_list):
        prev_pt = mc.xform(vtx_list[(i-1) % n], q=True, ws=True, t=True)
        cur_pt  = mc.xform(vtx_list[i],          q=True, ws=True, t=True)
        next_pt = mc.xform(vtx_list[(i+1) % n],  q=True, ws=True, t=True)

        v1 = [prev_pt[j] - cur_pt[j] for j in range(3)]
        v2 = [next_pt[j] - cur_pt[j] for j in range(3)]
        m1 = math.sqrt(sum(x*x for x in v1))
        m2 = math.sqrt(sum(x*x for x in v2))

        if m1 == 0 or m2 == 0:
            angle = 90.0
        else:
            cosang = sum(a*b for a, b in zip(v1, v2)) / (m1 * m2)
            cosang = max(-1.0, min(1.0, cosang))
            angle = math.degrees(math.acos(cosang))
        deviation = abs(angle - 90.0)
        angle_data.append((i, v, angle, deviation))
    deviations = [d for (_, _, _, d) in angle_data]
    if max(deviations) - min(deviations) <= similarity_threshold:
        corner_idxs = [int(i * n / 4) for i in range(4)]
    else:
        candidates = [item for item in angle_data if item[3] <= corner_threshold]
        if len(candidates) >= 4:
            candidates = sorted(candidates, key=lambda x: x[3])[:4]
        else:
            candidates = sorted(angle_data, key=lambda x: x[3])[:4]
        candidates.sort(key=lambda x: x[0])
        corner_idxs = [item[0] for item in candidates]

    if len(corner_idxs) != 4:
        fallback = sorted(angle_data, key=lambda x: x[3])[:4]
        fallback.sort(key=lambda x: x[0])
        corner_idxs = [item[0] for item in fallback]

    corner_vertices  = [vtx_list[i] for i in corner_idxs]
    corner_positions = [mc.xform(v, q=True, ws=True, t=True) for v in corner_vertices]
    init_segments = []
    for k in range(4):
        start = corner_idxs[k]
        end = corner_idxs[(k+1) % 4]
        seg = []
        idx = start
        while True:
            seg.append(vtx_list[idx])
            if idx == end:
                break
            idx = (idx + 1) % n
        init_segments.append(seg)

    target = n / 4.0
    best_idx = min(range(4), key=lambda i: abs(len(init_segments[i]) - target))
    start_loop = corner_idxs[best_idx]
    rotated = vtx_list[start_loop:] + vtx_list[:start_loop]
    len0 = len(init_segments[best_idx])
    half = n // 2
    len1 = half - len0
    len2 = len0
    seg0 = rotated[0:len0]
    start1 = len0 - 1
    end1   = len0 + len1 + 1
    seg1 = rotated[start1:end1]
    start2 = end1 - 1
    end2   = start2 + len2
    seg2 = rotated[start2:end2]
    last2 = end2 - 1
    seg3_body = rotated[last2 + 1:]
    seg3 = [rotated[last2]] + seg3_body + [rotated[0]]
    segments = [seg0, seg1, seg2, seg3]
    segments_pos = [
        [mc.xform(v, q=True, ws=True, t=True) for v in seg]
        for seg in segments
    ]
    return segments, segments_pos, corner_vertices, corner_positions


def instantQPatch():
    cleanList = ('innerLoop','oldSelLoop')
    for c in cleanList:
        if mc.objExists(c):
            mc.delete(c)
    selEdge = mc.filterExpand(sm = 32)
    if selEdge:
        selGeo = mc.ls(hl=1)
        mc.displaySmoothness(selGeo, divisionsU=0, divisionsV=0, pointsWire=4, pointsShaded=1, polygonObject=1)
        mc.nurbsToPolygonsPref(polyType=1, format=2, uType=3, uNumber=1, vType=3, vNumber=1)
        curves = []
        segments_pos = []
        checkLoopSize = getEdgeRingGroupList(selEdge)
        if len(checkLoopSize) == 1:
            getCircleState, listSelVtx = vtxLoopOrderCheck(selEdge)  
            if getCircleState == 0:
                fullPossibleLoop = mc.polySelectSp(selEdge[0], loop=1, q=1)
                fullPossibleLoop = mc.ls(fullPossibleLoop,fl=1)
                getCircleState, listVtx = vtxLoopOrderCheck(fullPossibleLoop)  
                if getCircleState == 1:
                    amount = len(fullPossibleLoop)
                    checkSelAmount = len(selEdge)
                    maxPossible = int((amount / 2) - 1)
                    if checkSelAmount > maxPossible:
                        mc.select(listSelVtx[0:maxPossible]) 
                        mc.ConvertSelectionToContainedEdges()
                        selEdge = mc.filterExpand(sm = 32) 
                    if amount % 2 == 1:
                        mc.sets(name='oldSelLoop', text='oldSelLoop')
                        short_edge, short_len = get_shortest_edge(fullPossibleLoop)
                        mc.select(fullPossibleLoop)
                        mc.polyExtrudeEdge(constructionHistory=0, keepFacesTogether=1, divisions=1, twist=0, taper=1, offset=0.05, thickness=0, smoothingAngle=30)
                        mc.sets(name='innerLoop', text='innerLoop')
                        inner = mc.ls(selection=True, flatten=True) or []
                        getCircleState, listVtx = vtxLoopOrderCheck(inner)  
                        short_edge, short_len = get_shortest_edge(inner)
                        edge_comp = short_edge if short_edge.startswith("|") else "|" + short_edge
                        verts = mc.polyListComponentConversion(edge_comp, fromEdge=True, toVertex=True)
                        verts = mc.ls(verts, l=1,fl=1) or []  
                        segments, segments_pos, corner_verts, corner_pos = segmentsPositions_adaptive(listVtx,similarity_threshold=5.0,corner_threshold=30.0)
                        matches = set(verts) & set(corner_verts)
                        if matches:
                            pointB = set(verts) - set(matches)
                            target_pos = mc.xform(matches, q=True, t=True, ws=True)
                            mc.xform(pointB, t=target_pos, ws=True)
                        mc.polyCollapseEdge(short_edge,ch=0)
                        oldSelLoopList = mc.sets('oldSelLoop', query=True)
                        toface = mc.polyListComponentConversion(oldSelLoopList,fromEdge=True, toFace=True)
                        toEdge = mc.polyListComponentConversion(toface, fromFace=True, toEdge=True)
                        getBorderEdges = mc.ls(toEdge,fl=1)
                        inner = mc.sets('innerLoop', query=True)
                        inner = mc.ls(inner,fl=1)
                        newSel = list(set(inner) & set(getBorderEdges))
                        mc.delete('innerLoop','oldSelLoop')                   
                        getCircleState, initialVerts = vtxLoopOrderCheck(newSel) 
                        getCircleState, listVtx = vtxLoopOrderCheck(inner)   
                        segments, segments_pos = segmentsPositions(listVtx, initialVerts)
                    else:
                        getCircleState, initialVerts = vtxLoopOrderCheck(selEdge) 
                        getCircleState, listVtx = vtxLoopOrderCheck(fullPossibleLoop)  
                        segments, segments_pos = segmentsPositions(listVtx, initialVerts)
            else:
                amount = len(selEdge)
                if amount % 2 == 1:
                    short_edge, short_len = get_shortest_edge(selEdge)
                    mc.polyExtrudeEdge(constructionHistory=0, keepFacesTogether=1, divisions=1, twist=0, taper=1, offset=short_len/2, thickness=0, smoothingAngle=30)
                    mc.sets(name='innerLoop', text='innerLoop')
                    inner = mc.ls(selection=True, flatten=True) or []
                    getCircleState, listVtx = vtxLoopOrderCheck(inner)  
                    segments, segments_pos, corner_verts, corner_pos = segmentsPositions_adaptive(listVtx,similarity_threshold=5.0,corner_threshold=30.0)
                    short_edge, short_len = get_shortest_edge(inner)
                    #edge_comp = short_edge if short_edge.startswith("|") else "|" + short_edge
                    verts = mc.polyListComponentConversion(short_edge, fromEdge=True, toVertex=True)
                    verts = mc.ls(verts, l=1,fl=1) or []  
                    matches = set(verts) & set(corner_verts)
                    if matches:
                        pointB = set(verts) - set(matches)
                        if pointB:
                            target_pos = mc.xform(matches, q=True, t=True, ws=True)
                            mc.xform(pointB, t=target_pos, ws=True)
                    mc.polyCollapseEdge(short_edge,ch=0)
                    selEdge = mc.sets('innerLoop', query=True)
                    selEdge = mc.ls(selEdge,fl=1)
                    mc.delete('innerLoop')
                getCircleState, listVtx = vtxLoopOrderCheck(selEdge)  
                segments, segments_pos, corner_verts, corner_pos = segmentsPositions_adaptive(listVtx,similarity_threshold=35.0,corner_threshold=55.0)
        curves = create_segment_curves(segments_pos, degree=1, close_loop=False)
        if curves:
            mc.boundary(curves[0], curves[1], curves[2], curves[3],ch=0,ep=0,po=1,order=0)
            mc.delete(curves)
            mc.select(selGeo, add=True)
            mc.polyUnite(ch=0, mergeUVSets=1, name=selGeo[0])
            newName = mc.ls(selection=True)
            mc.polyMergeVertex(distance= 0.001, am=True, ch=0)
            mc.rename(newName[0], selGeo[0])
            mc.polyNormal(selGeo[0],normalMode=2, userNormalMode=0, ch=0)
            mc.SetToFaceNormals()
            mc.select(selGeo[0], replace=True)

def instantQPatchUI():
    cleanList = ('innerLoop','oldSelLoop')
    for c in cleanList:
        if mc.objExists(c):
            mc.delete(c)
    selEdge = mc.filterExpand(sm = 32)
    if mc.window("iconWin", exists=True):
        mc.deleteUI("iconWin")
    win = mc.window("iconWin", title="QPatch V0.48", mxb = False, mnb = False, s = 1 )
    mc.columnLayout(adjustableColumn=True)
    mc.text(l='')
    mc.rowColumnLayout(nc=5, cw=[ (1,20),(2,60),(3,10),(4,60),(5,20)])
    mc.text(l='')
    mc.iconTextButton(style='iconOnly',image1='polyConvertToFace.png',width=64, command='instantQPatch()')
    mc.iconTextButton(style='iconOnly',image1='UVEditorVAxis.png',en=0,h=32)
    #mc.text(l='|')
    mc.iconTextButton(style='iconOnly',image1='polyConvertToFacePath.png',width=64,command='instantQPatchOpen()')
    #mc.checkBox('QPatchAutoMode', label='Auto' ,v=1)
    mc.text(l='')
    mc.text(l='')
    mc.setParent( '..' )
    mc.showWindow(win)
instantQPatchUI()


