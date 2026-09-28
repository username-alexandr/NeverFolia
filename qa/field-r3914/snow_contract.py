"""The source snowy carts have different 1/2-layer roof decorations per role.
Only this exact decorative difference is permitted when validating a common
biome recipe. The chosen reconstruction retains the complete armorer roof;
no source reference is modified or reported as identical when it is not.
"""

def compare(actual, reference, biome, differences):
    for operation,path,before,after in differences:
        if not (biome=='snowy' and operation=='replace' and len(path)==7
                and path[0]=='blocks' and isinstance(path[1],tuple)
                and len(path[1])==3 and path[1][1]==4
                and path[2:]==('state','Properties',1,'layers',1)
                and before in ('1','2') and after in ('1','2')):
            raise ValueError('Unreviewed role-dependent biome difference: '+repr((operation,path,before,after)))
        position=path[1]
        for model in (actual,reference):
            if model['blocks'][position]['state'].get('Name')!=(8,'minecraft:snow'):
                raise ValueError('Non-snow block passed to snow-layer comparison')
    return {'exact_serialized_model_equal':not differences,
            'roof_snow_layer_variations':[{'pos':list(path[1]),'chosen_armorer_layers':before,'reference_layers':after}
                for operation,path,before,after in differences],
            'other_typed_NBT_and_placement_mask_equal':True}
