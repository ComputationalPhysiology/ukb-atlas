[![DOI](https://zenodo.org/badge/846706235.svg)](https://doi.org/10.5281/zenodo.13927883)

# UK Biobank atlas - mesh generation

Generate meshes using the UK Biobank atlas (https://www.cardiacatlas.org/biventricular-modes/)

## Install
Install with `pip`
```
python3 -m pip install git+https://github.com/ComputationalPhysiology/ukb-atlas
```
or with [`pipx`](https://github.com/pypa/pipx)
```
pipx install git+https://github.com/ComputationalPhysiology/ukb-atlas.git
```

## Usage
```
$ ukb-atlas --help
usage: ukb-atlas [-h] [-a] [-m MODE] [-s STD] [--mesh] [--char_length_max CHAR_LENGTH_MAX] [--char_length_min CHAR_LENGTH_MIN] outdir

Generate surfaces and meshes from UK Biobank atlas.

positional arguments:
  outdir                Directory to save the generated surfaces and meshes.

options:
  -h, --help            show this help message and exit
  -a, --all             Download the PCA atlas derived from all 4,329 subjects from the UK Biobank Study.
  -m MODE, --mode MODE  Mode to generate points from. If -1, generate points from the mean shape. If between 0 and the number of modes, generate points from the
                        specified mode. By default -1
  -s STD, --std STD     Standard deviation to scale the mode by, by default 1.5
  --mesh                Create gmsh mesh files from the generated surfaces.
  --char_length_max CHAR_LENGTH_MAX
                        Maximum characteristic length of the mesh elements.
  --char_length_min CHAR_LENGTH_MIN
                        Minimum characteristic length of the mesh elements.
```
For example, by running the following command
```
ukb-atlas data --mesh
```
The tool will generate the following files
```
data
├── AV_ED.stl
├── AV_ES.stl
├── ED.msh
├── EPI_ED.stl
├── EPI_ES.stl
├── ES.msh
├── LV_ED.stl
├── LV_ES.stl
├── MV_ED.stl
├── MV_ES.stl
├── PV_ED.stl
├── PV_ES.stl
├── RVFW_ED.stl
├── RVFW_ES.stl
├── RV_ED.stl
├── RV_ES.stl
├── TV_ED.stl
├── TV_ES.stl
├── UKBRVLV.h5
└── parameters.json
```
Which are surfaces for both the end diastolic (ED) and the end systolic (ES) shapes, the PCA atlas (`UKBRVLV.h5`) and the parameters used to generate the surfaces.

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
