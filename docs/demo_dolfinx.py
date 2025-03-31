# # Example with dolfinx

import subprocess
from pathlib import Path
from mpi4py import MPI
import pyvista
import gmsh
import dolfinx


# Let us first list the help menu

subprocess.run(["ukb-atlas", "--help"])

# We will first use the `surf` command

subprocess.run(["ukb-atlas", "surf", "--help"])

# First we try to generate the surfaces for mean shape from the UK Biobank atlas end-diastole

folder = Path("data-mean")
mode = "-1"  # -1 refers to mean shape (otherwise you can choice a value between 0 and 200)
std = "1.5"  # Standard deviation to scale the mode by, by default 1.5
subprocess.run(["ukb-atlas", "surf", str(folder), "--mode", mode, "--std", std, "--case", "ED"])

# Let us now see which files that was generated

subprocess.run(["ls", str(folder)])

# We will now generate the mesh for the mean shape, but let us first look at the help menu

subprocess.run(["ukb-atlas", "mesh", "--help"])

# Note that this command uses `gmsh`, which is not part of the default dependencies so this needs to be installed. You can do this using either
# ```
# python3 -m pip install gmsh
# ```
# or use
# ```
# python3 -m pip install ukb-atlas[gmsh]
# ```
#
# Now we will generate the mesh for the mean shape (let us pick the rest of the parameters as default)

subprocess.run(["ukb-atlas", "mesh", str(folder)])

# Note that by decreasing the values of `char_length_max`and `char_length_min` you will get a finer mesh. We can now load the mesh with dolfinx and plot it with pyvista

comm = MPI.COMM_WORLD
msh_file = folder / "ED.msh"
gmsh.initialize()
gmsh.model.add("Mesh from file")
gmsh.merge(str(msh_file))
mesh, ct, ft = dolfinx.io.gmshio.model_to_mesh(gmsh.model, comm, 0)
markers = {
    gmsh.model.getPhysicalName(*v): tuple(reversed(v)) for v in gmsh.model.getPhysicalGroups()
}
print(markers)
gmsh.finalize()


pyvista.start_xvfb()
vtk_mesh = dolfinx.plot.vtk_mesh(mesh, mesh.topology.dim)
grid = pyvista.UnstructuredGrid(*vtk_mesh)
plotter = pyvista.Plotter()
plotter.add_mesh(grid, show_edges=True)
plotter.view_xy()
if not pyvista.OFF_SCREEN:
    plotter.show()
else:
    figure = plotter.screenshot("mesh.png")


vtk_bmesh = dolfinx.plot.vtk_mesh(mesh, ft.dim, ft.indices)
bgrid = pyvista.UnstructuredGrid(*vtk_bmesh)
bgrid.cell_data["Facet tags"] = ft.values
bgrid.set_active_scalars("Facet tags")
p = pyvista.Plotter(window_size=[800, 800])
p.add_mesh(bgrid, show_edges=True)
if not pyvista.OFF_SCREEN:
    p.show()
else:
    figure = p.screenshot("facet_tags_biv.png")


# Now lets us perturb the mean shape with the second mode

folder_mode_1 = Path("data-mode-1")
subprocess.run(
    ["ukb-atlas", "surf", str(folder_mode_1), "--mode", "1", "--std", "1.5", "--case", "ED"]
)

# And create the mesh

subprocess.run(["ukb-atlas", "mesh", str(folder_mode_1)])

comm = MPI.COMM_WORLD
msh_file = folder_mode_1 / "ED.msh"
gmsh.initialize()
gmsh.model.add("Mesh from file")
gmsh.merge(str(msh_file))
mesh2, ct2, ft2 = dolfinx.io.gmshio.model_to_mesh(gmsh.model, comm, 0)
markers = {
    gmsh.model.getPhysicalName(*v): tuple(reversed(v)) for v in gmsh.model.getPhysicalGroups()
}
print(markers)
gmsh.finalize()

pyvista.start_xvfb()
vtk_mesh2 = dolfinx.plot.vtk_mesh(mesh2, mesh2.topology.dim)
grid2 = pyvista.UnstructuredGrid(*vtk_mesh2)
plotter2 = pyvista.Plotter()
plotter2.add_mesh(grid2, show_edges=False)
plotter2.add_mesh(grid, style="wireframe", color="k")
plotter2.view_xy()
if not pyvista.OFF_SCREEN:
    plotter2.show()
else:
    figure = plotter.screenshot("mesh.png")


vtk_bmesh2 = dolfinx.plot.vtk_mesh(mesh2, ft2.dim, ft2.indices)
bgrid2 = pyvista.UnstructuredGrid(*vtk_bmesh2)
bgrid2.cell_data["Facet tags"] = ft2.values
bgrid2.set_active_scalars("Facet tags")
p2 = pyvista.Plotter(window_size=[800, 800])
p2.add_mesh(bgrid2, show_edges=True)
if not pyvista.OFF_SCREEN:
    p2.show()
else:
    figure = p2.screenshot("facet_tags_biv.png")


# ## Clipping the mesh
#
# Let us now show how to clip the mesh. First let us just clip the first mesh using `pyvista` to see how we can the mesh to look like. This is also a good way to figure out what should be the origin and normal for the clip plane. (Note that the default values are the ones given below which works well for the mean shape of the ED mesh)

origin = (-13.612554383622273, 18.55767189380559, 15.135103714006394)
normal = (-0.7160843664428893, 0.544394641424108, 0.4368725838557541)
p3 = pyvista.Plotter()
p3.add_mesh_clip_plane(grid, normal=normal, origin=origin, invert=True)
if not pyvista.OFF_SCREEN:
    p3.show()
else:
    figure = p3.screenshot("mesh_clip.png")

# There is a command called `clip`, so let us first look at the help section

subprocess.run(["ukb-atlas", "clip", "--help"])

# Note that this command uses `pyvista`, which is not part of the default dependencies so this needs to be installed. You can do this using either
# ```
# python3 -m pip install pyvista
# ```
# or use
# ```
# python3 -m pip install ukb-atlas[pyvista]
# ```
#
# To create the mesh we pass the origin and normal, we will also smooth the RV endocardium because the original surface has some very sharp transistions

subprocess.run(
    [
        "ukb-atlas",
        "clip",
        str(folder),
        "--smooth",
        "--case",
        "ED",
        "-ox",
        str(origin[0]),
        "-oy",
        str(origin[1]),
        "-oz",
        str(origin[2]),
        "-nx",
        str(normal[0]),
        "-ny",
        str(normal[1]),
        "-nz",
        str(normal[2]),
    ]
)

# Let us again see which files we have

subprocess.run(["ls", str(folder)])

# There are now some new `.ply` files that represents the clipped surfaces. We can for example take a look at one of them

# +
lv_clipped = pyvista.read(folder / "lv_clipped.ply")

p4 = pyvista.Plotter()
p4.add_mesh(lv_clipped)
if not pyvista.OFF_SCREEN:
    p4.show()
else:
    figure = p4.screenshot("lv_clipped.png")
# -

# To mesh to three surfaces togeher we repeat the mesh command but pass the `--clipped` flag

subprocess.run(["ukb-atlas", "mesh", str(folder), "--clipped"])

# We can now load the new clipped mesh into dolfinx

comm = MPI.COMM_WORLD
msh_file = folder / "ED_clipped.msh"
gmsh.initialize()
gmsh.model.add("Mesh from file")
gmsh.merge(str(msh_file))
mesh_clipped, ct_clipped, ft_clipped = dolfinx.io.gmshio.model_to_mesh(gmsh.model, comm, 0)
markers_clipped = {
    gmsh.model.getPhysicalName(*v): tuple(reversed(v)) for v in gmsh.model.getPhysicalGroups()
}
print(markers_clipped)
gmsh.finalize()

# and visualize it

pyvista.start_xvfb()
vtk_mesh_clipped = dolfinx.plot.vtk_mesh(mesh_clipped, mesh_clipped.topology.dim)
grid_clipped = pyvista.UnstructuredGrid(*vtk_mesh_clipped)
p5 = pyvista.Plotter()
p5.add_mesh(grid_clipped, show_edges=True)
# p5.add_mesh(grid, style="wireframe", color="k")
p5.view_xy()
if not pyvista.OFF_SCREEN:
    p5.show()
else:
    figure = p5.screenshot("mesh_clipped.png")

vtk_bmesh_clipped = dolfinx.plot.vtk_mesh(mesh_clipped, ft_clipped.dim, ft_clipped.indices)
bgrid_clipped = pyvista.UnstructuredGrid(*vtk_bmesh_clipped)
bgrid_clipped.cell_data["Facet tags"] = ft_clipped.values
bgrid_clipped.set_active_scalars("Facet tags")
p6 = pyvista.Plotter(window_size=[800, 800])
p6.add_mesh(bgrid_clipped, show_edges=True)
if not pyvista.OFF_SCREEN:
    p6.show()
else:
    figure = p6.screenshot("facet_tags_biv_clipped.png")
