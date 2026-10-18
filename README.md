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

## Development

```
pip install -e ".[dev]"
pytest
```
