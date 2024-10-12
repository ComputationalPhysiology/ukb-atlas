# # Example with dolfinx

import subprocess
from pathlib import Path
from mpi4py import MPI
import pyvista
import dolfinx
import gmsh


# First we try to generate the mean shape from the UK Biobank atlas

folder = Path("data")
subdir = "mean"
subprocess.run(["ukb-atlas", str(folder), "--mesh", "--subdir", subdir])

comm = MPI.COMM_WORLD
msh_file = folder / subdir / "ED.msh"
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
subdir = "mode_1"
subprocess.run(
    ["ukb-atlas", str(folder), "--mesh", "--mode", "1", "--std", "1.5", "--subdir", subdir]
)

comm = MPI.COMM_WORLD
msh_file = folder / subdir / "ED.msh"
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
    figure = p.screenshot("facet_tags_biv.png")
