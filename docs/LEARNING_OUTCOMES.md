# Learning outcomes

Page views, XP and streaks measure activity, not learning. A learner can earn
XP for wrong answers, retries and page loads without getting better at
anything. The measures on the profile page and `GET /api/outcomes` answer a
narrower question instead: **can this learner answer questions more accurately
and more independently than before?**

## What is measured

All measures are computed from the attempt history the app already keeps
(`submissions`, `mistakes`, `coding_submissions`, `user_progress`). There is
no new tracking and no schema change. Implementation: `engineverse/outcomes.py`.

| Measure | Definition | Unlocks at |
|---|---|---|
| First-attempt accuracy | Share of questions answered correctly the first time they were met. Retries cannot inflate it. | 1 question attempted |
| Accuracy trend | First-half vs second-half accuracy over the learner's own chronological attempts. A positive delta means later answers are better than earlier ones. | 8 attempts |
| Retry success | Of the questions ever answered wrong, the share later answered right. | 3 ever-wrong questions |
| Independent-correct share | Of all correct answers, the share given on the first attempt, before the learner saw the explanation. | 1 correct answer |
| Mistakes open / resolved | Rows in the mistake notebook by resolution state. | immediately |
| Coding solve rate | Judged problems solved out of judged problems attempted. Refusals (`unsupported_language`, `sandbox_unavailable`, `internal_error`) are not attempts. | 1 judged problem |
| First-submission accept rate | Share of attempted problems accepted on the first executed submission. | 1 judged problem |
| Median submissions to solve | Median judged attempts needed per solved problem. Lower is better. | 3 solved problems |
| Topics mastered | `user_progress` rows by status band, plus average mastery. | immediately |

Below the threshold a measure reports `null` (blank on the page) rather than
a noisy percentage. The thresholds are constants at the top of `outcomes.py`.

## What this does not claim

- **No causal inference.** A rising trend shows a learner improving while
  using Meridian; it does not prove Meridian caused the improvement.
  There is no control group, no pre-registration, and no adjustment for
  question difficulty or self-selection.
- **No cross-learner ranking.** First-attempt accuracy depends on which
  questions a learner chose. Comparing two learners' percentages is
  meaningless unless they answered the same items under the same conditions.
- **No independence proof.** "Unaided" means "before seeing this app's
  explanation". It says nothing about textbooks, classmates or search engines.
- **XP is still activity.** XP rewards attempts, including wrong ones, by
  design. Do not report XP as a learning gain.

## Evaluating with these measures

The honest unit of analysis is the **within-learner trend**: compare a
learner's recent first-attempt accuracy and retry success against their own
early baseline. For a cohort, report the distribution of per-learner deltas
(median, quartiles), the share of learners with a positive delta, and the
sample sizes - never a single average without them. Exclude learners below
the reporting thresholds rather than filling in zeroes.

`GET /api/outcomes` returns the signed-in learner's own report only. There is
no staff endpoint aggregating other learners' outcomes; cohort analysis runs
against the operator's own database, under the operator's privacy policy.
