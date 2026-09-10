# Generating mesh from a custom atlas

There is also support for generating a mesh from the atlas generated from the study in https://www.sciencedirect.com/science/article/pii/S109766472500081X#sec0135.

To make this work you need to download the atlas from some source and then you can generate the surfaces using the following command

```bash
ukb-atlas surf folder --burns-path path_to_burns_file.mat
```
where `folder` is the folder where you want to save the surfaces and `path_to_burns_file.mat` is the path to the Burns atlas file. Passing `--burns-path` is what selects the Burns atlas; when it is omitted the UK Biobank atlas is downloaded and used instead. The `--mode` and `--std` options work the same way as for the UK Biobank atlas.

Next you can generate the mesh as normal using the command

```bash
ukb-atlas mesh folder
```
