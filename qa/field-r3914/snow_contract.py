"""Source snowy carts vary snow coverage/thickness on the roof at local Y=3/4.
A reconstruction uses one COMPLETE authored roof, not a new randomized pattern.
The comparison records AIR/SNOW decoration differences separately and never
permits a different support, workstation, connector, block entity or omitted cell.
"""

def decoration(state):
    if state=={'Name':(8,'minecraft:air')}:
        return {'block':'minecraft:air','layers':0}
    if set(state)=={'Name','Properties'} and state['Name']==(8,'minecraft:snow'):
        tag,properties=state['Properties']
        if tag==10 and set(properties)=={'layers'}:
            tag,layers=properties['layers']
            if tag==8 and layers in frozenset(str(i) for i in range(1,9)):
                return {'block':'minecraft:snow','layers':int(layers)}
    raise ValueError('Non-decorative/invalid block in roof comparison: '+repr(state))

def compare(actual, reference, biome, differences):
    positions=set()
    for operation,path,before,after in differences:
        if not (biome=='snowy' and len(path)>=3 and path[0]=='blocks'
                and isinstance(path[1],tuple) and len(path[1])==3
                and path[1][1] in (3,4) and path[2]=='state'):
            raise ValueError('Unreviewed role-dependent biome difference: '+repr((operation,path,before,after)))
        positions.add(path[1])
    variations=[]
    for position in sorted(positions):
        a=actual['blocks'][position];b=reference['blocks'][position]
        if {k:v for k,v in a.items() if k!='state'}!={k:v for k,v in b.items() if k!='state'}:
            raise ValueError('Roof comparison may not hide block-entity changes')
        before=decoration(a['state']);after=decoration(b['state'])
        variations.append({'pos':list(position),'chosen_authored_roof':before,'reference_roof':after})
    return {'exact_serialized_model_equal':not differences,
            'roof_snow_decoration_variations':variations,
            'other_typed_NBT_and_placement_mask_equal':True}
