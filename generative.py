
#
# Blender 3.0/3.1
# Author: Lovro Bosnar
#

import bpy

import bmesh

import mathutils

from numpy.random import default_rng

import math
import copy

# https://blender.stackexchange.com/questions/220072/check-using-name-if-a-collection-exists-in-blend-is-linked-to-scene
def create_collection_if_not_exists(collection_name):
    if collection_name not in bpy.data.collections:
        new_collection = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(new_collection) #Creates a new collection

def create_instance(base_obj,
                    translate=mathutils.Vector((0,0,0)), 
                    scale=1.0,
                    rotate=("Z", 0.0),
                    basis=mathutils.Matrix.Identity(4),
                    tbn=mathutils.Matrix.Identity(4),
                    collection_name=None):
    # Create instance.
    inst_obj = bpy.data.objects.new(base_obj.name+"_inst", base_obj.data)
    # Perform translation, rotation, scaling and moving to target coord system for instance.
    mat_rot = mathutils.Matrix.Rotation(math.radians(rotate[1]), 4, rotate[0])
    mat_trans = mathutils.Matrix.Translation(translate)
    mat_sca = mathutils.Matrix.Scale(scale, 4) # TODO: figure out how to scale in given vector direction
    # TODO: If I am using `tbn` as basis then it sould go last, If I use `matrix_basis` as basis then it should go first.
    # `tbn` matrix is usually constructed for samples on base geometry using triangle normal. Therefore, it only contains
    # information about rotation.
    inst_obj.matrix_basis = basis @ mat_trans @ mat_rot @ mat_sca @ tbn  # TODO: is matrix_basis correct to be used for this?
    # Store to collection.
    if collection_name == None:
        bpy.context.collection.objects.link(inst_obj)
    else:
        create_collection_if_not_exists(collection_name)
        bpy.data.collections[collection_name].objects.link(inst_obj)
    return inst_obj

# https://graphics.pixar.com/library/OrthonormalB/paper.pdf
def pixar_onb(n):
    t = mathutils.Vector((0,0,0))
    b = mathutils.Vector((0,0,0))
    if(n[2] < 0.0):
        a = 1.0 / (1.0 - n[2])
        b = n[0] * n[1] * a
        t = mathutils.Vector((1.0 - n[0] * n[0] * a, -b, n[0]))
        b = mathutils.Vector((b, n[1] * n[1] * a - 1.0, -n[1]))
    else:
        a = 1.0 / (1.0 + n[2])
        b = -n[0] * n[1] * a
        t = mathutils.Vector((1.0 - n[0] * n[0] * a, b, -n[0]))
        b = mathutils.Vector((b, 1 - n[1] * n[1] * a, -n[1]))
    return t, b

def select_activate_only(objects=[]):
    for obj in bpy.data.objects:
        obj.select_set(False)
    bpy.context.view_layer.objects.active = None 
    for obj in objects:
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

# https://docs.blender.org/api/current/bpy.ops.uv.html
# uv_projection_type = {"cube, "sphere", "smart"}
def create_uv(base_obj, uv_projection_type="cube"):
    # Select object.
    select_activate_only([base_obj])
    # Move from object mode to edit mode.
    bpy.ops.object.mode_set(mode='EDIT')
    # Peform UV unwrap.
    bpy.ops.mesh.select_all(action='SELECT')
    if uv_projection_type == "cube":
        bpy.ops.uv.cube_project()
    if uv_projection_type == "sphere":
        bpy.ops.uv.sphere_project()
    if uv_projection_type == "smart":
        bpy.ops.uv.smart_project()
    # Move from edit mode to object mode.
    bpy.ops.object.mode_set(mode='OBJECT')


def remove_list(list_of_objects):
    for curr_object in list_of_objects:
        bpy.data.objects.remove(curr_object, do_unlink=True)

def boolean_difference(with_object):
    bpy.ops.object.modifier_add(type="BOOLEAN")
    bpy.context.object.modifiers["Boolean"].operation = "DIFFERENCE"
    bpy.context.object.modifiers["Boolean"].object = with_object
    bpy.context.object.modifiers["Boolean"].solver = "EXACT" # TODO: approx?
    bpy.context.object.modifiers["Boolean"].use_self = False
    bpy.ops.object.modifier_apply(modifier="Boolean")

def create_icosphere(radius=1.0):
    bm = bmesh.new()
    # Create icosphere.
    # https://docs.blender.org/api/current/bmesh.ops.html#bmesh.ops.create_icosphere
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1, matrix=mathutils.Matrix.Identity(4), calc_uvs=False)
    object_mesh = bpy.data.meshes.new("ico_sphere_mesh")
    bm.to_mesh(object_mesh)
    obj = bpy.data.objects.new("ico_sphere_obj", object_mesh)
    bpy.context.collection.objects.link(obj)
    bm.free()
    return obj

# Create shader for given material.
# https://vividfax.github.io/2021/01/14/blender-materials.html
# shader_type = {"glossy", "diffuse", "glass"}
def create_shader(dest_mat, shader_type="glossy", color=(0.8, 0.54519, 0.224999, 1), roughness=0.2, ior=1.45):

    # Obtain shader nodes and links.
    nodes = dest_mat.node_tree.nodes
    links = dest_mat.node_tree.links
    # Create output (surface) node.
    output = nodes.new(type='ShaderNodeOutputMaterial')

    # Create BSDF.
    if shader_type == "glossy":
        shader = nodes.new(type='ShaderNodeBsdfGlossy')
        nodes["Glossy BSDF"].inputs[0].default_value = color
        nodes["Glossy BSDF"].inputs[1].default_value = roughness
    elif shader_type == "diffuse":
        shader = nodes.new(type='ShaderNodeBsdfDiffuse')
        nodes["Diffuse BSDF"].inputs[0].default_value = color
    elif shader_type == "glass":
        shader = nodes.new(type='ShaderNodeBsdfGlass')
        nodes["Glass BSDF"].inputs[0].default_value = color
        nodes["Glass BSDF"].inputs[1].default_value = roughness
        nodes["Glass BSDF"].inputs[2].default_value = ior

    # Create links.
    links.new(shader.outputs[0], output.inputs[0])

# Create material, create shader and assign it to the object.
def assign_new_material(base_obj, shader_type, color, roughness, ior, mat_name):
    # Create new material.
    mat = bpy.data.materials.new(name=mat_name)
    # Create Shader.
    mat.use_nodes = True
    if mat.node_tree:
        mat.node_tree.links.clear()
        mat.node_tree.nodes.clear()
    create_shader(mat, shader_type, color, roughness, ior)
    # Assign material to object.
    base_obj.data.materials.append(mat)

def create_penta_sphere(radius=1.0, location=mathutils.Vector((0,0,0)), name="penta_sphere", shader_type="glossy", color=(1,1,1,1), roughness=0.2, ior=1.45):
    bm = bmesh.new()
    # Create icosphere.
    # https://docs.blender.org/api/current/bmesh.ops.html#bmesh.ops.create_icosphere
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1, matrix=mathutils.Matrix.Identity(4), calc_uvs=False)
    # From icosphere create pentasphere.
    # https://blender.stackexchange.com/a/780
    # https://en.wikipedia.org/wiki/Dual_polyhedron
    # For icosphere of radius=1, edges must be beveled in range [0.29,0.3] so we obtain pentasphere!
    bmesh.ops.bevel(bm, geom=(bm.edges), offset=0.29, affect="EDGES")
    # Obtain "clean" pentasphere while bevel introduces additional vertices!
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.05)
    # TODO: remove close vertices!
    object_mesh = bpy.data.meshes.new(name + "_mesh")
    bm.to_mesh(object_mesh)
    bm.free()
    obj = bpy.data.objects.new(name + "_obj", object_mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    assign_new_material(base_obj=obj, shader_type=shader_type, color=color, roughness=roughness, ior=ior, mat_name=name+"_material")
    create_uv(obj, uv_projection_type="smart")
    return obj

# Create pentasphere with extruded faces.
# Create base element where main element of base element is scale=1
def create_penta_sphere_extruded(location=mathutils.Vector((0,0,0)), name="penta_sphere_extruded", shader_type="glossy", color=(1,1,1,1), roughness=0.2, ior=1.45):
    penta_sphere_main = create_penta_sphere(radius=1.0, name=name, location=mathutils.Vector((0,0,0)), shader_type=shader_type, color=color, roughness=roughness, ior=ior)
    # For penta sphere of radius = 1.0, we need to create icosphere of 0.93...
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.93, matrix=mathutils.Matrix.Identity(4), calc_uvs=False)
    # And bevel its edges for 0.22 to obtain penta mesh detail.
    bmesh.ops.bevel(bm, geom=(bm.edges), offset=0.22, affect="EDGES")
    # Finally, make a mesh object from bmesh.
    detail_mesh = bpy.data.meshes.new("detail_mesh")
    bm.to_mesh(detail_mesh)
    # TODO: assign material!
    detail_obj = bpy.data.objects.new("detail_obj", detail_mesh)
    bpy.context.collection.objects.link(detail_obj)
    bm.free()
    base_elem1_name = penta_sphere_main.name 
    select_activate_only([detail_obj, penta_sphere_main]) # join takes the name of the last selected and also its material!
    bpy.ops.object.join()
    obj = bpy.context.scene.objects[base_elem1_name]
    obj.location = location
    create_uv(obj, uv_projection_type="smart")
    return obj

# Create pentasphere with hollow faces.
# Create base element where main element of base element is scale=1
def create_penta_sphere_hollow(location=mathutils.Vector((0,0,0)), name="penta_sphere_hollow", shader_type="glossy", color=(1,1,1,1), roughness=0.2, ior=1.45):
    # Create main penta sphere.
    penta_sphere_main = create_penta_sphere(radius=1.0, location=mathutils.Vector((0,0,0)), name=name, shader_type=shader_type, color=color, roughness=roughness, ior=ior)
    # For main penta sphere of radius = 1.0, we need to create icosphere of 0.85...
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.85, matrix=mathutils.Matrix.Identity(4), calc_uvs=False)
    # And bevel its edges for 0.16 to obtain penta mesh detail.
    bmesh.ops.bevel(bm, geom=(bm.edges), offset=0.16, affect="EDGES")
    # Finally, make a mesh object from bmesh.
    detail_mesh = bpy.data.meshes.new("detail_mesh")
    bm.to_mesh(detail_mesh)
    detail_obj = bpy.data.objects.new("detail_obj", detail_mesh)
    bpy.context.collection.objects.link(detail_obj)
    bm.free()
    select_activate_only([penta_sphere_main])
    boolean_difference(detail_obj)
    bpy.data.objects.remove(detail_obj, do_unlink=True)
    penta_sphere_main.location = location
    create_uv(penta_sphere_main, uv_projection_type="smart")
    return penta_sphere_main

# https://blender.stackexchange.com/questions/115397/extrude-in-python
# https://docs.blender.org/api/current/bmesh.ops.html
# hollow_size [0,1]
def create_penta_sphere_hollow2(location=mathutils.Vector((0,0,0)), name="penta_sphere_hollow2", hole_size=0.5, hole_scale=0.1, shader_type="glossy", color=(1,1,1,1), roughness=0.2, ior=1.45):
    # NOTE: calculations of geometry are done in (0,0,0) with scale 1! Later object is transformed.
    # Create base pentasphere.
    base_obj=create_penta_sphere(radius=1.0, location=mathutils.Vector((0,0,0)), name=name, shader_type=shader_type, color=color, roughness=roughness, ior=ior)
    #  Create detail pentasphere.
    bm = bmesh.new()
    # Create icosphere.
    # https://docs.blender.org/api/current/bmesh.ops.html#bmesh.ops.create_icosphere
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1, matrix=mathutils.Matrix.Identity(4), calc_uvs=False)
    # From icosphere create pentasphere.
    # https://blender.stackexchange.com/a/780
    # https://en.wikipedia.org/wiki/Dual_polyhedron
    # For icosphere of radius=1, edges must be beveled in range [0.29,0.3] so we obtain pentasphere!
    bmesh.ops.bevel(bm, geom=(bm.edges), offset=0.3, affect="EDGES")
    # Obtain "clean" pentasphere while bevel introduces additional vertices!
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.05)
    # Extrude faces in normal direction
    efaces = bmesh.ops.extrude_discrete_faces(bm, faces=bm.faces)
    for eface in efaces["faces"]:
        bmesh.ops.translate(bm,verts=eface.verts,vec=eface.normal*6.0)
    # Scale faces in place.
    # https://blender.stackexchange.com/questions/121123/using-python-and-bmesh-to-scale-resize-a-face-in-place
    """
    for face in bm.faces:
        face_center = face.calc_center_median()
        for v in face.verts:
            #v.co = face_center + hole_scale * (v.co - face_center)
            v_offset_dir = (v.co - face_center)
            v_offset_dir.normalize()
            v.co = v.co + hole_scale * v_offset_dir
    """
    # Create mesh object from bmesh.
    detail_mesh = bpy.data.meshes.new("detail_mesh")
    bm.to_mesh(detail_mesh)
    detail_obj = bpy.data.objects.new("detail_obj", detail_mesh)
    detail_obj.scale = mathutils.Vector((hole_size,hole_size,hole_size)) # [0.1, 0.8] - see the extrude length
    bpy.context.collection.objects.link(detail_obj)
    bm.free()
    # Perform boolean difference.
    select_activate_only([base_obj])
    boolean_difference(detail_obj)
    bpy.data.objects.remove(detail_obj, do_unlink=True)
    base_obj.location = location
    create_uv(base_obj, uv_projection_type="smart")
    return base_obj

def create_point_light(location=mathutils.Vector((0,0,0)), color=mathutils.Vector((0.823102, 0.285278, 0.118767)), intensity=20.0):
    # Create new light datablock.
    light_data = bpy.data.lights.new(name="point_light_data", type='POINT')
    # Create new object with our light datablock.
    light_object = bpy.data.objects.new(name="point_light_object", object_data=light_data)
    # Link to the scene.
    bpy.context.collection.objects.link(light_object)
    # Place light to a specified location.
    light_object.location = location
    # Specify color
    light_object.data.color = color
    # Specify intensity
    light_object.data.energy = intensity
    return light_object

# triangulate using bmesh.
def triangulate(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.triangulate(bm, faces=bm.faces, quad_method="BEAUTY", ngon_method="BEAUTY")
    bm.to_mesh(obj.data)
    bm.free()  # free and prevent further access

#
# barycentric sampling of triangulated mesh using object.data (mesh)
# object.data (mesh) has extensive info on vertices (e.g. weight, color, etc.)
#
# NOTE: base_obj must be triangulated!
#
def vertex_weighted_barycentric_sampling(base_obj, n_samples):
    samples = [] # (p, N, w, tbn)
    for polygon in base_obj.data.polygons: # must be triangulated mesh!
        triangle_vertices = []
        triangle_vertex_weights = []
        for v_idx in polygon.vertices:
            v = base_obj.data.vertices[v_idx]
            triangle_vertices.append(v.co)
            if len(v.groups) < 1:
                triangle_vertex_weights.append(0.0)
            else:
                triangle_vertex_weights.append(v.groups[0].weight) # TODO: only one group? Investigate! float in [0, 1], default 0.0
        for i in range(n_samples):
            # Find sample using barycentric sampling.
            a = mathutils.noise.random()
            b = mathutils.noise.random()
            c = mathutils.noise.random()
            s = a + b + c
            un = (a / s)
            vn = (b / s)
            wn = (c / s)
            w = un * triangle_vertex_weights[0] + vn * triangle_vertex_weights[1] + wn * triangle_vertex_weights[2] # interpolate weight
            if w > 0.01: # an precision error otherwise?
                p = un * triangle_vertices[0] + vn * triangle_vertices[1] + wn * triangle_vertices[2]
                n = polygon.normal # TODO: vertex normals?
                # Calc tangent. NOTE: use most distant point from barycentric coord to evade problems with 0
                t = mathutils.Vector(triangle_vertices[0] - p)
                t = t.normalized()
                bt = n.cross(t)
                bt = bt.normalized()
                tbn = mathutils.Matrix((t, bt, n)) # NOTE: using pixar_onb()?
                tbn = tbn.transposed() # TODO: why transposing?
                tbn.resize_4x4()
                samples.append((p,n,w,tbn))
    return samples 


# n_iter - scalar, int e.g. n=1
# starting_elem - pentasphere from which growth starts.
# scale_range - vector, float e.g. (min=0.1, max=0.8)
# base_elements - list of objects representing base elements that will be instances
# lights - list of lights that will be instances
def grow(starting_elem=None, n_iter=3, scale_range=(0.8, 1.0), base_elements=[], lights=[], face_grow_factor_per_iter=0.7):
    rng = default_rng()
    # Create starting computation element.
    # NOTE: computational elements are simplest pentaspheres. Those elements are used for grow logic. Later they are replaced with more 
    # interesting basic elements.
    comp_instancing_elem = None
    if starting_elem:
        comp_instancing_elem = starting_elem
    else:
        comp_instancing_elem = create_penta_sphere() # NOTE: if starting_elem is not given, then pentasphere in the center of world orign will be used.
    # TODO: Also create display element at that position.
    rand_elem_idx = rng.integers(len(base_elements), size=1)[0]
    base_elem = base_elements[rand_elem_idx]
    display_elem = create_instance(base_elem, translate=mathutils.Vector((0,0,0)), scale=1.0, rotate=("Z", 0.0), basis=comp_instancing_elem.matrix_basis, tbn=mathutils.Matrix.Identity(4))
    list_of_all_comp_objects = []
    curr_comp_list = []
    curr_comp_list.append(comp_instancing_elem)
    list_of_all_comp_objects.append(comp_instancing_elem)
    face_grow_factor = 1.0 # First iteration starts with the default value. Each next can have smaller or larger factor
    for iter_i in range(n_iter):
        new_comp_list = []
        for curr_comp_elem in curr_comp_list:
            #done_for_curr_comp_elem = False
            for polygon in curr_comp_elem.data.polygons:
                if mathutils.noise.random() < face_grow_factor and polygon.area > 0.1: # NOTE: now computational/logical pentaspheres have merges vertices, so only large faces exist!
                    # Calculate tranformation for base element for the current face.
                    p = polygon.center
                    n = polygon.normal
                    if n[2] < 0.1: # NOTE: normal is local and it is not always pointing in world +z!
                        continue
                    t, b = pixar_onb(n)
                    tbn = mathutils.Matrix((t, b, n)) # NOTE: using pixar_onb()?
                    tbn = tbn.transposed() # TODO: why transposing?
                    tbn.resize_4x4()
                    scale = max(curr_comp_elem.scale) * ((scale_range[1] - scale_range[0]) * mathutils.noise.random() + scale_range[0]) # NOTE: max(curr_comp_elem.dimensions) vs max(curr_comp_elem.scale)
                    translate = p + n * scale / 1.5 # touch with faces! 
                    # Create display elem in according collection for face.
                    # Choose random base element.
                    rand_elem_idx = rng.integers(len(base_elements), size=1)[0]
                    base_elem = base_elements[rand_elem_idx]
                    display_elem = create_instance(base_elem, translate=translate, scale=scale, rotate=(n, 0.0), basis=curr_comp_elem.matrix_basis, tbn=tbn, collection_name=base_elem.name)
                    if len(lights) > 0 and "hollow" in display_elem.name: # add point lights in pentaspheres with holes
                        if mathutils.noise.random() < 0.1: # randomly choose if light will be added or not.
                            rand_light_idx = rng.integers(len(lights), size=1)[0]
                            light = lights[rand_light_idx]
                            create_instance(light, translate=display_elem.location, scale=1, rotate=(n, 0.0), basis=mathutils.Matrix.Identity(4), tbn=mathutils.Matrix.Identity(4), collection_name=base_elem.name)
                    # Create computational elem per face.
                    new_comp_elem = create_instance(comp_instancing_elem, translate=translate, scale=scale, rotate=(n, 0.0), basis=curr_comp_elem.matrix_basis, tbn=tbn)
                    new_comp_list.append(new_comp_elem)
                    list_of_all_comp_objects.append(new_comp_elem)
                    #if iter_i % 2 == 0:
                    #    done_for_curr_comp_elem = True
                    #    break
            #if iter_i % 2 == 0 and done_for_curr_comp_elem:
            #    break
        curr_comp_list = new_comp_list
        face_grow_factor = face_grow_factor * face_grow_factor_per_iter
        if face_grow_factor < 0.2:
            face_grow_factor = 0.2
    remove_list(list_of_all_comp_objects)

def main():
    starting_elems = bpy.context.selected_objects
    """
    base_obj = None
    base_obj = bpy.context.selected_objects[0]
    # Get starting elem.
    triangulate(base_obj)
    samples = vertex_weighted_barycentric_sampling(base_obj=base_obj, n_samples=1)
    ps = create_penta_sphere() # TODO: remove once it is not needed!
    starting_elems = []
    for sample in samples:
        starting_elem = create_instance(ps,
                        translate=sample[0], # p
                        scale=1.0,
                        rotate=("Z", 0.0),
                        basis=base_obj.matrix_basis,
                        tbn=sample[3], # tbn
                        collection_name=None)
        starting_elems.append(starting_elem)
    """
    # Create base elems that will be instanced.
    # Material parameters.
    roughness = 0.3
    color = (1,1,1, 1)
    shader_type = "diffuse"
    # Create base geometry.
    base_elements = []
    ps = create_penta_sphere(radius=1.0, location=mathutils.Vector((50,10,0)), name="penta_sphere", shader_type=shader_type, color=color, roughness=roughness, ior=1.45)
    #base_elements.append(ps)
    pse = create_penta_sphere_extruded(location=mathutils.Vector((50,20,0)), name="penta_sphere_extruded", shader_type=shader_type, color=color, roughness=roughness, ior=1.45)
    base_elements.append(pse)
    psh = create_penta_sphere_hollow(location=mathutils.Vector((50,30,0)), name="penta_sphere_hollow", shader_type=shader_type, color=color, roughness=roughness, ior=1.45)
    #base_elements.append(psh)
    hs21 = create_penta_sphere_hollow2(location=mathutils.Vector((50,40,0)), name="penta_sphere_hollow2", hole_size=0.1, hole_scale=0.1, shader_type=shader_type, color=color, roughness=roughness, ior=1.45)
    hs22 = create_penta_sphere_hollow2(location=mathutils.Vector((50,50,0)), name="penta_sphere_hollow2", hole_size=0.2, hole_scale=0.1, shader_type=shader_type, color=color, roughness=roughness, ior=1.45)
    hs23 = create_penta_sphere_hollow2(location=mathutils.Vector((50,60,0)), name="penta_sphere_hollow2", hole_size=0.3, hole_scale=0.1, shader_type=shader_type, color=color, roughness=roughness, ior=1.45)
    hs24 = create_penta_sphere_hollow2(location=mathutils.Vector((50,70,0)), name="penta_sphere_hollow2", hole_size=0.4, hole_scale=0.1, shader_type=shader_type, color=color, roughness=roughness, ior=1.45)
    base_elements.extend([hs21, hs22, hs23, hs24])
    # Create light point that will be instanced.
    lights = []
    light1 = create_point_light(location=mathutils.Vector((0,0,0)), color=mathutils.Vector((0.823102, 0.285278, 0.118767)), intensity=20.0)
    light2 = create_point_light(location=mathutils.Vector((0,0,0)), color=mathutils.Vector((0.823102, 0.285278, 0.118767)), intensity=10.0)
    light3 = create_point_light(location=mathutils.Vector((0,0,0)), color=mathutils.Vector((0.823102, 0.285278, 0.118767)), intensity=5.0)
    lights.append(light1)
    lights.append(light2)
    lights.append(light3)
    # Perfom growth.
    #for starting_elem in starting_elems:
    grow(starting_elem=None, n_iter=15, scale_range=(0.9, 1.0), base_elements=base_elements, lights=lights, face_grow_factor_per_iter=0.45)
    
if __name__ == "__main__":
    main()
