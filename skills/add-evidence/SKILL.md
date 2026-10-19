---
name: add-evidence
description: Add a verified scientific publication to COACH data/evidence with finding, limits and the rules it supports. Use when a rule needs a source or when reviewing the evidence base.
---

# Add a publication

The evidence base is only worth something if every entry is real and honestly summarised.

## Steps
1. **Open the source** (PubMed / Europe PMC / publisher). Read at least the abstract. If you cannot open it, do not add it. Never rely on memory for authors, numbers or DOI.
2. Add an entry to the right file in `data/evidence/*.yaml`:
   ```yaml
   - id: RUN-021            # family prefix + next number, unique
     topic: running
     citation: "Author A, Author B (YYYY). Title. Journal."
     year: 2020
     doi: "10.xxxx/..."
     pmid: "..."
     url: "https://pubmed.ncbi.nlm.nih.gov/.../"
     design: randomised controlled trial | meta-analysis | cohort | narrative review | …
     finding_fr: "What the abstract reports, with numbers as written."
     limits_fr: "Sample size, duration, population, what it does NOT show."
     applies_to: [C1]        # existing rule IDs only (validated at start-up)
     confidence: faible | moyenne | élevée
     verified_on: "YYYY-MM-DD"
   ```
3. Run `pytest tests/test_evidence.py -q`: it checks required fields, unique IDs and that `applies_to` rules exist.
4. State **limits plainly** (e.g. “elite athletes only”): the coach quotes them.

## Pitfalls
- Summaries come from abstracts; say so. Don’t upgrade “associated with” into “causes”.
- One strong trial ≠ a rule. Match `confidence` to the design and sample.
- Keep text in the product language (`*_fr` today; see `add-language` for translations).
- Preprints and blogs are not evidence entries.

## Verify
Click the DOI/URL. Reread the finding against the abstract. Ask: would I be comfortable if a user quoted this to a doctor?
