# hirejutsu

Finds the best job openings for your resume every morning, so you can apply to them yourself.

## Requirements

- Python 3.10 or newer
- Windows, macOS or Linux

## Install

```
git clone https://github.com/Jay-Parmar/hirejutsu.git
cd hirejutsu
py -m venv .venv
.venv\Scripts\activate
pip install -e .
```

On macOS or Linux use `python3 -m venv .venv` and `source .venv/bin/activate`.

Check that it works:

```
hirejutsu --version
```

`hj` is a short alias for `hirejutsu`.

## Setup

```
hirejutsu init
```

This creates a data folder with a starter `config.yaml`. By default the folder is `~/.hirejutsu`
(`C:\Users\<you>\.hirejutsu` on Windows). Use `--home <folder>` or the `HIREJUTSU_HOME`
environment variable to keep it somewhere else.

Copy your resume into the data folder and open the config:

```
hirejutsu config --edit
```

## Development

```
pip install -e ".[dev]"
pytest
```
