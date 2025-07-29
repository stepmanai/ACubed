---
language:
  - en
license: mit
size_categories:
  - 1K<n<10K
task_categories:
  - feature-extraction
extra_gated_prompt: >-
  ## Terms of Use for Flash Flash Revolution (FFR) Charts Dataset

  The Flash Flash Revolution Charts dataset is a curated collection of rhythm game stepfiles, metadata, and analysis used to train difficulty prediction models. Before accessing this dataset, please read and agree to the following terms:

  1. The dataset contains data derived from Flash Flash Revolution's API. Use of this dataset must comply with any original content licenses or terms of use from those source projects.

  2. The dataset may be updated periodically to correct issues, remove invalid data, or comply with content removal requests. By clicking "Access repository," you agree to keep your local copy in sync with the latest supported version.

  3. Redistribution of the dataset in part or in full must include this Terms of Use section and require users to agree to it before access is granted.

  By clicking on "Access repository" below, you agree that your contact information (email address and usernames) may be shared with the dataset maintainers for the purpose of dataset governance and responsible usage tracking.
extra_gated_fields:
  Email: text
  FFR Username: text
  I have read the License and agree with its terms: checkbox
tags:
  - music
  - code
  - rhythm-game
  - stepmania
  - ffr
dataset_info:
  features:
    - name: _id
      dtype: int64
    - name: name
      dtype: string
    - name: difficulty
      dtype: int64
    - name: chart
      list:
        - name: time
          dtype: float64
        - name: step
          dtype: string
pretty_name: FFR Stepfiles
---

<center>
  <img src="https://c10.patreonusercontent.com/4/patreon-media/p/campaign/4763745/1d85de6c3ed148e694aa2647c8895a3f/eyJ3IjoxMjAwLCJ3ZSI6MX0%3D/1.png?token-hash=SovVZQthKSgoKNy1TQpXBssi5g4tNAGYtfpWB84onbU%3D&token-time=1754265600" alt="FineVideo">
</center>

# 🕹️ **FFR Charts Dataset**

- [Description](#description)
  - [Revisions](#revisions)
  - [Dataset Distribution](#dataset-distribution)
- [How to download and use FineVideo](#how-to-download-and-use-finevideo)
  - [Using `datasets`](#using-datasets)
  - [Using `huggingface_hub`](#using-huggingface_hub)
  - [Load a subset of the dataset](#load-a-subset-of-the-dataset)
- [Dataset Structure](#dataset-structure)
  - [Data Instances](#data-instances)
  - [Data Fields](#data-fields)
- [Dataset Creation](#dataset-creation)
- [License CC-By](#license-cc-by)
- [Considerations for Using the Data](#considerations-for-using-the-data)
  - [Social Impact of Dataset](#social-impact-of-dataset)
  - [Discussion of Biases](#discussion-of-biases)
- [Additional Information](#additional-information)
  - [Credits](#credits)
  - [Future Work](#future-work)
  - [Opting out of FineVideo](#opting-out-of-finevideo)
  - [Citation Information](#citation-information)
- [Terms of use for FineVideo](#terms-of-use-for-finevideo)

## Description

### 📄 Dataset Overview

The **FFR Charts** dataset provides structured, symbolic representations of rhythm game stepfiles. It supports research into **difficulty modeling**, **pattern recognition**, and **chart analysis** using objectively defined features and time-aligned step sequences.

Each data point includes:

- A full stepchart with timestamped actions (`time`, `step`)
- Metadata such as chart title and manually assigned difficulty level

These charts originate from _Flash Flash Revolution (FFR)_ — a long-running, community-driven rhythm game known for its vast library of user-submitted charts.

### 🧠 Ideal For:

- **Training machine learning models** for:
  - Difficulty prediction
  - Procedural stepchart generation
  - Sequence learning on symbolic time series
- **Evaluating** various difficulty systems in open-source rhythm games
- **Conducting analysis** of musical structure and gameplay patterns in rhythm-based content

Unlike traditional datasets with audio/video, **FFR Charts** is fully symbolic — making it highly suited for environments where clean input structure and deterministic behavior are essential.

### Revisions

| Date     | Changes                       |
| -------- | ----------------------------- |
| July '25 | Initial release of FFR Charts |

### Dataset Distribution

This dataset consists of:

- Over 4,000 unique stepcharts
- Average chart length of ~1,500 steps
- A range of difficulty levels, covering beginner to expert-level gameplay
- Charts mapped to a wide variety of music genres and tempos

The charts were originally sourced from the community-driven rhythm game _Flash Flash Revolution (FFR)_, and curated from publicly available files. All data is distributed under the MIT License, and no copyrighted audio is included.

## How to download and use FineVideo (TODO)

### Using `datasets`

```python
from datasets import load_dataset

dataset = load_dataset("stepmanai/ffr_charts", split="train")
```

### Using `huggingface_hub`

```python
from huggingface_hub import snapshot_download
folder = snapshot_download('stepmanai/ffr_charts',
                           repo_type='dataset',
                           local_dir='datasets/ffr/charts')
```

## Dataset Structure

### Data Instances

Each chart is stored in JSONL format with the following structure:

- `_id`: A unique identifier for the chart.
- `name`: The chart/song title.
- `difficulty`: A numerical difficulty score.
- `chart`: A list of timed step events. Each step has:
  - `time`: Timestamp in seconds.
  - `step`: A 4-character binary string indicating directional input.

Example:

```json
{
    "_id": 1111,
    "name":"song_name",
    "difficulty":111,
    "chart":[
        {"time":0, "step":"0001"},
        {"time":0.111, "step":"0110"},
    ...]
}
```

## Dataset Creation

The FFR Charts dataset was curated from community-contributed stepfiles originally created for the rhythm game _Flash Flash Revolution (FFR)_. From a larger archive of available charts, we selected those with valid structure, consistent formatting, and playable metadata to ensure compatibility with parsing tools and AI modeling tasks.

<center>
  <img src="https://huggingface.co/datasets/stepmanai/ffr_charts/resolve/main/ffr_dataset_creation.png" alt="Dataset Creation">
</center>

## License: MIT

This dataset consists of open-source chart data and does **not** include any copyrighted audio.

All stepfiles are released under the MIT License and are intended for open research, development, and educational purposes. The dataset is derived from publicly shared chart files, and we encourage proper attribution where applicable.

## Considerations for Using the Data

### Purpose and Impact

The FFR Charts dataset was created to support research on symbolic music modeling, rhythm game AI, and pattern analysis. While many strong sequence modeling benchmarks exist in NLP and code, datasets for music-based symbolic timing and gameplay reasoning are rare. This collection enables training and evaluation of models on structured time-aligned rhythm data.

We hope the dataset lowers barriers for researchers interested in musical reasoning and game AI, and promotes further innovation in symbolic sequence modeling.

### Discussion of Biases

Since the dataset consists of human-authored rhythm game charts, it inherently reflects the style, difficulty, and musical biases of FFR chart authors. Some charts may favor specific playstyles or music genres, and the difficulty annotations are not standardized across all files.

We recommend treating difficulty and genre metadata as subjective and using additional filtering or annotation for research tasks requiring strict consistency.

## Additional Information

### Credits

Created by:

The [StepmanAI](https://github.com/stepmanai) team

With contributions from:

- Community chart authors from the Flash Flash Revolution forums
- Open-source maintainers of tools for Stepmania/FFR parsing and playback

### Future Work

Future versions of the dataset may include:

- Audio fingerprint metadata (excluding the audio itself)
- Chart similarity clusters
- Standardized difficulty ratings
- Alignment with note timing engines for ML-friendly formats

We welcome contributions and feedback from the community to improve this dataset.

### Citation

```bibtex
@misc{stepmanai2024ffrcharts,
  title={FFR Charts Dataset},
  author={StepmanAI Contributors},
  year={2024},
  howpublished={\url{https://huggingface.co/datasets/stepmanai/ffr_charts}},
}
```

### Curation Rationale

Created to support research and development in rhythm game AI and sequence modeling tasks, this dataset allows exploration of human-designed rhythmic patterns across varying difficulty levels.

### Source Data

#### Data Collection and Processing

Stepfiles were collected or created by community members familiar with the rhythm game format. JSONL formatting was applied for machine learning compatibility.

#### Who are the source data producers?

Chart creators are hobbyist and semi-professional rhythm game mappers. Chart difficulty and quality vary by contributor.

### Annotations

No additional annotations are included. The `difficulty` field is subjective but commonly used to filter charts.

#### Personal and Sensitive Information

No personally identifiable information is included. All data is synthetic and game-based.

## Bias, Risks, and Limitations

- Difficulty ratings are not standardized across charts.
- No associated audio files included, which may limit rhythm-related accuracy.
- Charts were created for entertainment purposes, not data consistency.

### Recommendations

Users should normalize difficulty levels and validate step timing if comparing charts. Consider combining this dataset with audio files for deeper rhythm analysis.

## Citation

**BibTeX:**

```bibtex
@misc{ffr_stepfiles,
  title={FFR Stepfiles Dataset},
  author={Stepman.AI Developers and Maintainers},
  year={2024},
  url={https://huggingface.co/datasets/[repo_name]},
  note={MIT License}
}
```

**APA:**
Stepman.AI Developers and Maintainers. (2024). _FFR Stepfiles Dataset_. https://huggingface.co/datasets/[repo_name]

## Glossary

- **Stepfile**: A time-encoded sequence of directional arrows used in rhythm games.
- **Chart**: Synonym for stepfile.
- **Step**: A moment in time where one or more arrows are triggered.

## More Information

This dataset is part of a broader effort to study rhythm games and procedural generation. Audio-based versions or audio-aligned extensions may be released in the future.

## Dataset Card Authors

WirryWoo

## Dataset Card Contact

contact.acubed@gmail.com

- **Curated by:** Stepman.AI Developers and Maintainers
- **License:** MIT
- **Language(s):** English (used in song titles and metadata)

### Dataset Sources

- **Repository:** https://github.com/stepmanai/ACubed
- **Paper [optional]:** Coming soon...
- **Demo [optional]:** Coming soon...

## Uses

### Direct Use

- Feature extraction from rhythmic input patterns
- Training ML models for chart generation or gameplay analysis
- Studying temporal sequences and player skill modeling
- Educational tools for rhythm game development

### Out-of-Scope Use

- Not suitable for tasks requiring synchronized audio
- Not intended for evaluating natural language understanding

## Dataset Structure

Each line in the dataset represents one chart in JSON format. The core data field is `chart`, which contains a list of timestamped `step` entries. Each `step` is a 4-character string representing:

- `1` = active note
- `0` = inactive

The character positions correspond to:

1. Left
2. Down
3. Up
4. Right

No dataset splits are defined (e.g., train/test/validation), but users can generate splits based on difficulty or ID.
