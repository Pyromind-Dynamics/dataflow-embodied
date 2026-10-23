# Changelog

## 0.1.3

- Add operator-specific bilingual descriptions including actual parameter defaults and field contracts.
- Reject existing output columns before model calls or external artifact writes; choose a fresh output_key.
- Verify default/custom compilation dependencies and preserve source rows in conversion paths.


## 0.1.2

- Add `EmbodiedSubtaskExporter` for standalone `subtasks.json` conversion from existing source labels and intervals.
- Preserve sensor-clock timing, source references and review status; refuse missing labels or overwriting output.
- This is deterministic conversion, not visual semantic task recognition.

## 0.1.1

Added fresh-run streaming episode pipelines and multi-episode equivalence, encoder failure cleanup, index corruption, and randomized alignment validation.

## 0.1.0

Independent operators, DataFlow pipelines, offline tests and source provenance.
