# COSMo - (C)oNLL-U (O)pen-(S)ource (M)erger

Simple GUI to help solve Git conflicts and adjudicate divergent annotation in CoNLL-U files

`python3 cosmo.py`

![COSMo Screenshot](https://github.com/alvelvis/conllu-merge-resolver/blob/main/screen.png?raw=true)

## Windows

See [releases](https://github.com/alvelvis/conllu-merge-resolver/releases).

## Distributing

```
pyinstaller cosmo.py --add-data "conllu-merge-resolver.css;." --add-data "conllu-merge-resolver.glade;." --add-data "estrutura_ud.py;." --add-data "interrogar_UD.py;." --noconfirm
```
