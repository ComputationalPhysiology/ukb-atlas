[![DOI](https://zenodo.org/badge/846706235.svg)](https://doi.org/10.5281/zenodo.13927883)

# UK Biobank atlas - mesh generation

Generate meshes using the UK Biobank atlas (https://www.cardiacatlas.org/biventricular-modes/)

## Install
Install with `pip`
```
python3 -m pip install ukb-atlas
```
or (latest version)
```
python3 -m pip install git+https://github.com/ComputationalPhysiology/ukb-atlas
```
or similarly with [`pipx`](https://github.com/pypa/pipx)
```
pipx install ukb-atlas
```
or (latest version)
```
pipx install git+https://github.com/ComputationalPhysiology/ukb-atlas.git
```

## Quick start
To generate surfaces from the UK Biobank atlas, run the following command
```
$ ukb-atlas surf data --mode -1 --std 1.5 --case ED
INFO:ukb.atlas:Generating points from /root/.ukb/UKBRVLV.h5 using mode -1 and std 1.5
INFO:ukb.surface:Saved data/EPI_ED.stl
INFO:ukb.surface:Saved data/MV_ED.stl
INFO:ukb.surface:Saved data/AV_ED.stl
INFO:ukb.surface:Saved data/TV_ED.stl
INFO:ukb.surface:Saved data/PV_ED.stl
INFO:ukb.surface:Saved data/LV_ED.stl
INFO:ukb.surface:Saved data/RV_ED.stl
INFO:ukb.surface:Saved data/RVFW_ED.stl
```
Now we can generate a mesh from these surfaces
```
$ ukb-atlas mesh data
INFO:ukb.mesh:Creating mesh for ED with char_length_max=5.0, char_length_min=5.0
INFO:ukb.mesh:Created mesh data/ED.msh
```
![_](https://github.com/ComputationalPhysiology/ukb-atlas/blob/main/docs/_static/full.png)

Now we can also create a mesh without the outflow tracts using the `cilp` command
```
$ ukb-atlas clip data
ukb-atlas clip data
INFO:ukb.clip:Folder: data
INFO:ukb.clip:Case: ED
INFO:ukb.clip:Origin: [-13.612554383622273, 18.55767189380559, 15.135103714006394]
INFO:ukb.clip:Normal: [-0.7160843664428893, 0.544394641424108, 0.4368725838557541]
INFO:ukb.clip:Reading data/LV_ED.stl
Warning: PLY writer doesn't support multidimensional point data yet. Skipping Normals.
Warning: PLY doesn't support 64-bit integers. Casting down to 32-bit.
INFO:ukb.clip:Saved data/lv_clipped.ply
INFO:ukb.clip:Reading data/RV_ED.stl
INFO:ukb.clip:Reading data/RVFW_ED.stl
INFO:ukb.clip:Merging RV and RVFW
INFO:ukb.clip:Saving data/rv_clipped.ply
Warning: PLY writer doesn't support multidimensional point data yet. Skipping Normals.
Warning: PLY doesn't support 64-bit integers. Casting down to 32-bit.
INFO:ukb.clip:Reading data/EPI_ED.stl
INFO:ukb.clip:Saving data/epi_clipped.ply
Warning: PLY writer doesn't support multidimensional point data yet. Skipping Normals.
Warning: PLY doesn't support 64-bit integers. Casting down to 32-bit.
```
and then create a mesh from the clipped surfaces
```
$ ukb-atlas mesh data --clipped
INFO:ukb.mesh:Creating clipped mesh for ED with char_length_max=5.0, char_length_min=5.0
INFO:ukb.mesh:Created mesh data/ED_clipped.msh
```

![_](https://github.com/ComputationalPhysiology/ukb-atlas/blob/main/docs/_static/clipped.png)

## Usage
There are three main commands:
1. `surf` - Extract surfaces from the atlas and save them in the specified directory as STL files
2. `clip` - Clip the surfaces to remove e.g the outflow tracts
3. `mesh` - Generate mesh from the surfaces
```
usage: ukb-atlas [-h] {surf,clip,mesh} ...

UKB-atlas This is a command line interface for extracting surfaces and generating Bi-ventricular meshes from the UK Biobank atlas: https://www.cardiacatlas.org/biventricular-modes/

positional arguments:
  {surf,clip,mesh}
    surf            Extract surfaces from the atlas
    clip            Clip the surfaces
    mesh            Generate mesh from the surfaces

options:
  -h, --help        show this help message and exit
```

## Citing
If you use this tool to create meshes please cite
```
@software{Finsberg_fenics-beat_2024,
author = {Henrik Finsberg and Lisa R Pankewitz},
doi = {10.5281/zenodo.13927883},
title = {UK Biobank atlas - mesh generation},
url = {https://github.com/ComputationalPhysiology/ukb-atlas},
version = {0.1.0},
year = {2024}
}
```

The templates used to generate the meshes are described where developed as part of the following publication (so please cite this paper if you use the templates)
```
@article{PANKEWITZ2024103091,
title = {A universal biventricular coordinate system incorporating valve annuli: Validation in congenital heart disease},
journal = {Medical Image Analysis},
volume = {93},
pages = {103091},
year = {2024},
issn = {1361-8415},
doi = {https://doi.org/10.1016/j.media.2024.103091},
url = {https://www.sciencedirect.com/science/article/pii/S1361841524000161},
author = {Lisa R Pankewitz and Kristian G Hustad and Sachin Govil and James C Perry and Sanjeet Hegde and Renxiang Tang and Jeffrey H Omens and Alistair A Young and Andrew D McCulloch and Hermenegild J Arevalo},
keywords = {Cardiac geometry, Coordinates, Congenital Heart Disease, Mapping},
}
```

## License
MIT
