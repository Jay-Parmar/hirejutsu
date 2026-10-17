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

## Resume

hirejutsu reads `.pdf`, `.docx`, `.txt` and `.md` resumes. A scanned PDF has no text to read, so
export a text PDF from your editor or use a `.docx` or `.txt` file instead.

```
hirejutsu resume           # show the skills, titles and years of experience found
hirejutsu resume --text    # show the text that was read
```

Skills are matched against a built-in list of common skills, technical and non-technical.
Anything you set under `profile` in the config wins: `skills` are added to the ones found,
while `titles` and `years` replace the ones detected.

## Fetching jobs

```
hirejutsu sources          # list sources, whether they are on, and their last fetch
hirejutsu fetch            # download jobs from every enabled source
hirejutsu fetch -s lever   # just one source
```

Jobs are saved in `hirejutsu.db` inside the data folder, so each fetch only adds what is new.
A source that fails is reported and skipped, the others still run.

## Daily picks

```
hirejutsu run              # fetch, then pick today's best jobs for your resume
hirejutsu today            # show today's picks again
hirejutsu today --day 2026-10-16
hirejutsu top -n 30        # rank everything saved without recording picks
```

`run` picks `ranking.top` jobs (10 by default) and never shows a job again on a later day.
Each day's picks are also saved as a Markdown file in the `reports` folder.

## Development

```
pip install -e ".[dev]"
pytest
```
