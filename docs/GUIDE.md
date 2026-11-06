# cc-review Guide

The complete guide to cc-review: what it does, how to use it, how the review pipeline works, and how to extend it with your own reviewers.

The guide is maintained as a [cc-guide](https://github.com/rhuss/cc-guide) project under [guide/](guide/). You can read it here on GitHub or download the PDF.

## Read the guide

Start at the [guide overview](guide/docs/README.md). The full table of contents is in [guide/docs/SUMMARY.md](guide/docs/SUMMARY.md).

- [Overview](guide/docs/README.md)
- [Using cc-review](guide/docs/using/index.md): install, run a review, triage PR comments, inbox and issue assessment
- [How it works](guide/docs/how-it-works/index.md): the review pipeline, reviewers, meta-review, gate and fix, measured results
- [Extending cc-review](guide/docs/extending/index.md): write prompt and command reviewers, trust and configuration
- [Reference](guide/docs/reference/index.md): CLI, configuration and finding schema, invocation across harnesses

## PDF

A rendered PDF of the guide is at [guide/dist/cc-review-guide.pdf](guide/dist/cc-review-guide.pdf).

## Build it yourself

The guide is built with pandoc and the cc-guide toolkit:

```bash
cd docs/guide
make preview   # serve the pages with live reload
make pdf       # render the PDF into dist/
```
