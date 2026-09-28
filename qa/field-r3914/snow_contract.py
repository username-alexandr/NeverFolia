"""Source snowy carts vary snow thickness on the stepped roof at local Y=3/4.
These are existing minecraft:snow states, not arbitrary voxel changes. Keep the
complete selected source roof and report every decorative difference separately.
All non-snow fields, positions, supports, joints and profession data remain exact.
"""

def compare(actual, reference, biome, differences):
    valid_layers=frozenset(str(i) for i in range(1,9))
    for operation,path,before,after in differences:
        if not (biome=='snowy' and operation=='replace' and len(path)==7
                and path[0]=='blocks' and isinstance(path[1],tuple)
                and len(path[1])==3 and path[1][1] in (3,4)
                and path[2:]==('state','Properties',1,'layers',1)
                and before in valid_layers and after in valid_layers):
            raise ValueError('Unreviewed role-dependent biome difference: '+repr((operation,path,before,after)))
        position=path[1]
        for model in (actual,reference):
            if model['blocks'][position]['state'].get('Name')!=(8,'minecraft:snow'):
                raise ValueError('Non-snow block passed to snow-layer comparison')
    return {'exact_serialized_model_equal':not differences,
            'roof_snow_layer_variations':[{'pos':list(path[1]),'chosen_armorer_layers':before,'reference_layers':after}
                for operation,path,before,after in differences],
            'other_typed_NBT_and_placement_mask_equal':True}
