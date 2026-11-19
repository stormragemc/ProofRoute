# ProofRoute

ProofRoute helps a product engineer check a promise before making it to a customer. A question becomes a set of requirements. Each finding includes an exact passage from a retrieved source or a next step for resolving the uncertainty.

## Run your first question

Use Python 3.11 or newer. In the project directory, install the dependency, copy the example environment file, then fill in the two keys in your local copy.

```sh
python -m pip install -r requirements.txt
cp .env.example .env
```

On Windows PowerShell, use `Copy-Item .env.example .env`. Get an inference key from [Nebius Token Factory](https://tokenfactory.nebius.com/) and a search key from [Tavily](https://app.tavily.com/). Store them as `NEBIUS_API_KEY` and `TAVILY_API_KEY`. The default model is `moonshotai/Kimi-K3.1-Pro`. Set `NEBIUS_MODEL` to another chat model available to your account to change it.

```sh
python src/agent.py "Does the Web Speech API guarantee on-device speech recognition with its default settings?"
```

The console displays each requirement, its assessment, the quoted passage and the URL. To save the same run for inspection, add `--output research-run.json`. Add `--require-citation` to make a zero-citation run exit with a failure status.

## Run through GitHub Actions

Create your public project using the [organizer's repository template](https://github.com/odsc2015/nebius-research-agent-hackaton-template/generate). Place both keys in **Settings → Secrets and variables → Actions → New repository secret**. An optional `NEBIUS_MODEL` goes under **Variables**.

Open **Actions → ProofRoute research check → Run workflow** and enter a public research question. The workflow runs offline checks first and then calls both providers. The downloadable `research-run` artifact contains the question, findings, quotations, source links and a brief tool trace. People who can access workflow artifacts can read this report. Use public material for these runs.

The first push of the workflow to `main` also exercises it if both keys are available. If they are added afterward, start the workflow manually. The live check succeeds when a real run produces at least one checked source quotation. The logs identify a missing key or provider error.

## How a finding is made

1. Nebius plans up to ten testable requirements and one or two web queries. A private installation detail can remain an open requirement throughout a run.
2. Tavily returns up to four pages per query. ProofRoute selects passages from the extracted page text and assigns source IDs. Search snippets help rank passages. Only extracted page text can supply a citation.
3. Nebius assesses the requirements. For each cited finding, the application checks that the source exists and the quoted text occurs continuously in one retrieved passage, allowing whitespace normalization. Source URLs come directly from Tavily.
4. When a web search could resolve a gap, the agent can make one further query. It reassesses only when that query adds passages. A run uses at most three searches and three model calls.
5. The report retains each planned requirement. A missing quotation or omitted assessment leaves that requirement unverified. A Tavily failure appears separately in the trace. An unusable model response produces a visible error.

The model receives instructions separately from the untrusted page text and has no tools or credentials in its prompts. Exact quote matching checks provenance. Whether a quote justifies the finding still depends on the model's interpretation. Web documentation can establish a product capability. Confirming how a specific kiosk is configured requires evidence from that installation.

## Check locally

```sh
python -m unittest discover -s tests -v
```

The tests use synthetic provider responses and make no network calls. They cover fabricated quotations, missing passages, unverified requirements, conflicting findings, query limits, and the HTTP request formats. The GitHub live workflow is the separate check for account access and real model output.

This starter follows the ODSC × Nebius template. The [submission form](https://hackathon.odsc.ai/submit) requests the public repository and a demo video.
