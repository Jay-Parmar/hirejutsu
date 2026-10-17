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
Each day's picks are also saved in the `reports` folder, see below.

## Reports

`run` writes the day's picks to `reports/YYYY-MM-DD.md` and `reports/YYYY-MM-DD.html` in the
data folder. The HTML page works offline and loads nothing from the internet. Use
`hirejutsu run --open` to open it in your browser when the run is done.

```
hirejutsu report                          # rebuild today's report files
hirejutsu report --day 2026-10-16 --open  # rebuild another day and open it
hirejutsu report --format csv json        # write only CSV and JSON
```

The `report` section of the config sets the `formats` to write (md, html, csv, json), `open`
to open the HTML page after every run, and `keep_days`: reports older than that many days
(60 by default) are deleted when new ones are written, 0 keeps them all.

## Ranking

Each job gets a score from 0 to 1, a weighted mix of six parts:

- **skills**: which of your skills the job mentions. Skills that few of the day's jobs mention count
  more, and a skill in the job title counts double.
- **text**: how close the description is to your resume (TF-IDF cosine similarity).
- **title**: how close the job title is to the titles you want, after spelling out Sr, Jr, Eng, Dev
  and Mgr. Developer and engineer count as the same word.
- **seniority**: whether the level in the title (intern, junior, senior, staff, lead, manager and so
  on) and the years the description asks for fit `profile.years`.
- **freshness**: halves every `half_life_days` (3 by default) after the job was posted.
- **location**: remote, or in one of `profile.locations`. Bengaluru and Bangalore, Gurugram and
  Gurgaon, Mumbai and Bombay, NCR and Delhi count as the same place.

A part that can't be judged, like seniority when a job doesn't say, scores 0.5. Change the mix
under `ranking.weights`.

Jobs that mention none of your skills and have no close title are skipped. Jobs outside your
locations are skipped too, but jobs that give no location are kept. Set `location_mode: score` to
rank outside jobs lower instead. Jobs posted more than `max_age_days` ago are skipped (empty means
`search.max_age_days`). More filters are off until you set them: `exclude_keywords`,
`exclude_title_words`, `exclude_companies`, `require_keywords`, `min_score` and `min_salary` with
`salary_currency`.

Only the best 300 jobs by skills and title get the slower resume text comparison, so ranking stays
quick on big job lists.

To see how one job scored, which filters it passed and why it was picked:

```
hirejutsu explain 42
```

The id is shown by `run`, `today` and `top`.

## Development

```
pip install -e ".[dev]"
pytest
```
