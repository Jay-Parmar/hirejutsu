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

## Company career pages

hirejutsu reads jobs straight from company career pages on Greenhouse, Lever, Ashby,
SmartRecruiters, Recruitee, Workable, Workday, Personio, Breezy HR, BambooHR and Teamtailor.
Each of these is a source of its own, and 448 companies come built in.

```
hirejutsu companies                                 # companies per ATS, and the list
hirejutsu companies list --ats lever --search ai
hirejutsu companies add https://jobs.lever.co/acme  # any careers page or job link
hirejutsu companies add greenhouse:acme --name "Acme Inc"
hirejutsu companies remove greenhouse:stripe
hirejutsu companies check                           # find closed boards, --prune drops them
hirejutsu companies discover                        # add boards linked from jobs you have
```

Your changes go to `companies.yaml` in the data folder. Set `builtin: false` under `companies`
in the config to read only your own companies.

To keep the daily fetch to about two minutes, these sources keep only jobs posted within
`search.max_age_days` and, when you have keywords or target titles, jobs whose title shares a
word with them ("Backend Engineer" also keeps "Engineering Manager"). Set `title_filter: false`
for a source to keep every job. Greenhouse, SmartRecruiters, Workday and BambooHR need one more
request per job for its description. They read up to `max_details` (300) new jobs per fetch,
newest first, and the rest on the next fetch.

## Remote job boards

These sources read public job feeds and need no account or key. All are on except Arbeitnow.
Jobs posted more than `search.max_age_days` ago are skipped. Settings go under `sources:` in the
config, see the examples there.

| Source | Good for | Limits |
|---|---|---|
| `remoteok` | Remote OK: the newest 100 or so remote jobs, mostly tech | Few salaries |
| `remotive` | Remotive: a short list of hand-picked remote jobs | About 15 jobs, shown a day late. One call per run, Remotive allows 4 a day |
| `weworkremotely` | We Work Remotely: remote jobs in every field | Reads all 11 category feeds unless you set `categories` |
| `himalayas` | Himalayas: remote jobs that match your search keywords | 20 jobs a page, `max_pages` (3) for each keyword |
| `jobicy` | Jobicy: remote jobs of the last 7 days, many with salaries | 200 jobs a page, `max_pages` (5) |
| `workingnomads` | Working Nomads: about 50 recent remote jobs | No search |
| `hackernews` | Hacker News "Who is hiring?": startups posting their own jobs | Reads the newest monthly thread (`months`). Title and location come from the first line of each post, so they can be rough |
| `fourdayweek` | 4dayweek.io: jobs with a 4 day week or other good hours | Only remote jobs when your locations include `remote`. 100 jobs a page, `max_pages` (3) |
| `arbeitnow` | Arbeitnow: jobs in Germany and the rest of Europe | Off by default, as most jobs are onsite and many are in German. Up to 300 jobs a page, `max_pages` (3) |

The boards share their jobs on the condition that you credit them, link back to them and do not
republish the jobs. Every job keeps its link on the board (for Himalayas, the apply link it requires)
and everything stays on your computer, so keep your picks to yourself.

## LinkedIn, Indeed, Naukri and other big sites (optional)

hirejutsu can also search Indeed, Naukri, LinkedIn, Glassdoor and ZipRecruiter through
[python-jobspy](https://github.com/speedyapply/JobSpy). Install the extra:

```
pip install -e ".[jobspy]"
```

Then turn on the sites you want in `config.yaml`:

```yaml
sources:
  indeed: {enabled: true, country: India}
  naukri: {enabled: true}
  linkedin: {enabled: true}
```

Each site runs one search per keyword (`search.keywords`, or your titles) and city in
`profile.locations`. `remote` in your locations adds a search for remote jobs.

| Setting | Default | Meaning |
|---|---|---|
| `results` | Indeed 50, Glassdoor 30, LinkedIn 25, others 20 | jobs per search |
| `max_searches` | 3 | searches per site in one run |
| `delay_seconds` | 15, LinkedIn 30 | pause between searches |
| `descriptions` | on, LinkedIn off | load full descriptions, which takes extra requests |
| `country` | India | Indeed and Glassdoor only |

- LinkedIn has no remote filter when logged out, so it only searches your cities.
- Naukri wants plain city names such as `Bengaluru`.
- ZipRecruiter only lists jobs in the US and Canada.

These sites forbid scraping in their terms of use. That is why they stay off until you turn them
on, at your own risk. hirejutsu only reads job listings, a few searches a day, and never logs in
or applies for you. If a site starts refusing requests (usually a temporary rate limit on your
IP address), `hirejutsu fetch` shows the error and skips that site's other searches for the run.

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

## Tracking applications

Apply on the company's site, then record it here. A typical morning:

```
hirejutsu run              # fetch and pick today's jobs
hirejutsu review           # go through the picks: applied, skip, later or open
hirejutsu applied -t 1 3 7 # or mark picks #1, #3 and #7 as applied in one go
hirejutsu stats            # statuses, applications per week, response rate
```

Commands take job ids from the ID column, or today's pick numbers (the # column) with `-t`.

```
hirejutsu skip 12 15       # not for you
hirejutsu save -t 4        # apply later
hirejutsu status 12 interview --note "call on Tuesday"
hirejutsu note 12 recruiter called back
hirejutsu show 12          # details, notes, history and the description
hirejutsu open -t 2        # open the job link in your browser
hirejutsu list --status applied --since 7
hirejutsu export           # CSV of tracked jobs in the data folder
```

`status` takes new, saved, applied, interview, offer, rejected or skipped. Jobs you mark are left
out of later picks.

## Notifications

`run` can send the day's picks to you by email, Telegram, Discord, Slack or ntfy. Nothing is sent
until you set `enabled: true` on a channel under `notify` in the config.

Keep passwords, tokens and webhook URLs in environment variables. The config only holds the
variable's name (`password_env`, `bot_token_env`, `webhook_url_env`, `token_env`). Writing the
secret itself in the config works too, but hirejutsu warns you every time.

Gmail example: turn on 2-Step Verification for your Google account, create an app password at
https://myaccount.google.com/apppasswords and use it as `HIREJUTSU_SMTP_PASSWORD`.

```yaml
notify:
  email:
    enabled: true
    host: smtp.gmail.com
    security: starttls
    port: 587
    username: you@gmail.com
    password_env: HIREJUTSU_SMTP_PASSWORD
    to: [you@gmail.com]
    attach: true
```

Set the variable on Windows, then open a new terminal (`setx` does not change the one you are in):

```
setx HIREJUTSU_SMTP_PASSWORD abcdefghijklmnop
```

On macOS or Linux add this line to `~/.zshrc` or `~/.bashrc`, then open a new terminal:

```
export HIREJUTSU_SMTP_PASSWORD=abcdefghijklmnop
```

The other channels:

- Telegram: create a bot with @BotFather and put its token in `HIREJUTSU_TELEGRAM_TOKEN`. Send the
  bot a message, open `https://api.telegram.org/bot<token>/getUpdates` and copy `chat.id` into
  `chat_id`.
- Discord: Server Settings > Integrations > Webhooks. Put the webhook URL in `HIREJUTSU_DISCORD_WEBHOOK`.
- Slack: add an incoming webhook to your workspace and put its URL in `HIREJUTSU_SLACK_WEBHOOK`.
- ntfy: set `topic` to a name that is hard to guess and subscribe to it in the ntfy app.

```
hirejutsu notify --test              # send a test message to every enabled channel
hirejutsu notify                     # send today's picks again
hirejutsu notify --day 2026-10-16 --channel telegram
hirejutsu run --no-notify            # pick without sending anything
```

A channel that fails is reported and the others still get the picks.

## Run it every morning

```
hirejutsu schedule install                 # every day at 09:00
hirejutsu schedule install --time 07:30 --weekdays
hirejutsu schedule status                  # next and last run, and the end of the latest log
hirejutsu schedule remove
```

On Windows this adds a task named `hirejutsu` to Task Scheduler. It runs as you, only while you are
logged in, and needs no admin rights. If the PC is off or asleep at that time, the run happens as
soon as it is on again and you are logged in. Add `--wake` to wake a sleeping PC instead.
`hirejutsu schedule show` prints the task without adding it.

On macOS and Linux it adds a line to your crontab. Cron skips the run if the computer is off.

A scheduled run writes everything to `logs/run-YYYY-MM-DD.log` in the data folder, and the newest
30 logs are kept. It uses the Python you installed it with, so run `install` again if you move or
recreate your virtual environment.

## AI second opinion (optional)

hirejutsu can ask an AI model to score its best matches against your resume. The AI score is
mixed into the normal score (`weight`, 0.5 by default) and its reason comes first in the report,
as `AI: ...`. It is off by default.

**Privacy:** when this is on, your resume text and the job details are sent to the provider you
choose. For full privacy use a local model with Ollama (below), so nothing leaves your computer.

Providers, set with `ai.provider`:

- `anthropic` (default): Claude, model `claude-haiku-5-5`, key in `ANTHROPIC_API_KEY`.
- `openai`: any OpenAI compatible chat completions API. For OpenAI itself the model is
  `gpt-5-mini` and the key is in `OPENAI_API_KEY`. For Ollama, LM Studio, OpenRouter or Groq set
  `base_url`, `model` and, if the service needs a key, `api_key_env` (the variable's name).

Save your key on Windows, then open a new terminal:

```
setx ANTHROPIC_API_KEY "your-key"
```

On macOS or Linux add `export ANTHROPIC_API_KEY="your-key"` to your shell profile.

Set `enabled: true` in the `ai` section of the config, then check it:

```
hirejutsu ai test          # check the config with one tiny request
hirejutsu ai explain 42    # ask how well saved job 42 fits you
```

To keep the cost down, only the top `candidates` matches (30) are sent, `batch_size` (10) per
request, and each score is cached per job, model and resume, so a scored job is not paid for
again. A new resume or model scores them again. If a request fails, those jobs keep their normal
score.

Ollama example, free and fully local. Small local models do better with fewer jobs per request:

```yaml
ai:
  enabled: true
  provider: openai
  base_url: http://localhost:11434/v1
  model: llama3.1
  batch_size: 3
  timeout: 300
```

## Development

```
pip install -e ".[dev]"
pytest
```
