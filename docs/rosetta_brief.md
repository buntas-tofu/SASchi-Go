# Rosetta: Migrating off SAS, with Proof

*A method for translating SAS programs into modern open languages (Python, R, and
others) that proves each translation reproduces SAS's results, rather than asking
anyone to trust that it does.*

## The situation

The SAS license is not being renewed. A large body of production statistical code has
to move to open languages before it lapses. The obvious plan, hand the code to
contractors and get Python back, carries a quiet and serious risk: a translation can
compile, run, and still disagree with SAS on the numbers, at exactly the places where
the numbers decide something. The disagreement does not announce itself. It has to be
hunted, and manual review does not reliably find it.

## Why SAS is hard to leave

SAS is proprietary not only as software but as behavior. How it rounds, how it counts
date intervals, how it orders missing values, how a procedure handles an edge case,
these are defined only inside a closed system. There is no open specification to
translate against. That is the real lock-in: not the syntax, which is readable, but the
exact behavior, which is undocumented and load-bearing.

## What Rosetta does

Rosetta translates SAS into open languages and, for every piece it translates, produces
evidence that the translation reproduces SAS's own output. It does this without
reverse-engineering SAS. The insight is to stop trying to prove a translation correct by
reading it, and instead prove it by running it against SAS's answers. Four parts:

1. **Use SAS while it lasts.** The license still exists, so SAS is still the authority on
   its own behavior. Rosetta runs SAS on a battery of controlled test cases and captures
   its exact outputs. That becomes the answer key, produced by SAS itself, before it goes
   away.
2. **Write the behavior down.** The specific quirks that make SAS SAS, its rounding rule,
   its date math, its missing-value handling, its truncation rules, are captured as
   small, plain, inspectable reference implementations, each checked against the captured
   SAS outputs. The proprietary behavior stops being a black box and becomes a
   documented, version-controlled artifact.
3. **Translate mechanically where the code allows, carefully where it does not.** Most
   constructs map by fixed rules with no judgment involved, and every translated line
   records where it came from. The minority that need interpretation get a drafted
   translation, but a drafted translation is never trusted on anyone's word.
4. **Verify by execution, every time.** Each translated unit is run against generated
   test data and must match the behavior reference numerically. As an independent second
   check, the Python and R versions must also agree with each other. Nothing is accepted
   without a passing run.

## Why this is deterministic, and why the word is earned

Determinism means the same input always yields the same output, and that output matches
SAS. Rosetta does not put that guarantee in the translation step, where it would depend
on judgment. It puts it in the verification step, where it depends only on execution and
comparison. A translated program is accepted because it was run and its numbers matched
SAS's numbers, not because it looked right. That is the difference between "we rewrote
it" and "we reproduced it and proved the reproduction."

A concrete case from the first week of work: SAS rounds a half-unit up, away from zero,
while Python and R by default round a half to the nearest even number. In a
disclosure-related rounding rule, that single difference flips the result at every
half-unit boundary, and the boundary is the whole point of the rule. The translated code
compiled, ran, and was wrong. The verification gate caught it. A manual review would not
have.

## How a data scientist would use it

The intended experience is simple. A data scientist submits a SAS program, selects the
target language, and receives back the translated code together with its verification
report, the evidence that it matches SAS. The submission, language selection, and
results-return workflow is the next component to be engineered, and it is deliberately
kept separate from the translation-and-verification core, which already works.

## Where it stands

The architecture is built and proven on real, in-domain material. An initial corpus of
Census disclosure-avoidance tool scripts was inventoried cleanly, and roughly three
quarters of its procedural surface maps mechanically. A first program was translated into
both Python and R and verified across hundreds of generated test cases in each language,
with the two languages required to agree. Two distinct silent-divergence traps, one per
target language, were found and documented in that first pass, both caught by the gate
rather than by eye.

What has proven the method so far is documented behavior plus cross-language agreement.
The step that seals the full guarantee is the one named in part one above: run the
calibration battery against the live SAS license and capture its outputs as the
reference's ground truth, before decommission. That is what turns proven-against-our-
reference into proven-against-SAS, and it is available only while the licensed
runtime is still reachable.

## The short version

Rosetta is not a rewrite of SAS. It is a way to reproduce SAS's behavior in open
languages and to prove, program by program and number by number, that the reproduction
holds. The proof is mechanical, the evidence travels with the code, and the one thing it
depends on, SAS's own output, is captured while SAS is still here to provide it.
