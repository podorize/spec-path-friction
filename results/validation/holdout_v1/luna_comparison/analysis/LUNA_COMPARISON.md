# GPT-6 Luna architecture comparison

## Reference set

The primary binary analysis uses **42 stable decisive human cases**: 6 problematic and 36 nonproblematic. The small positive count makes recall and F1 estimates highly uncertain.

## Primary unweighted results

| Metric | Deterministic + Luna | Luna only |
| --- | ---: | ---: |
| Coverage | 64.3% | 90.5% |
| Precision | 100.0% | 100.0% |
| End-to-end recall | 16.7% | 16.7% |
| End-to-end specificity | 63.9% | 94.4% |
| End-to-end F1 | 28.6% | 28.6% |
| End-to-end accuracy | 57.1% | 83.3% |
| Selective accuracy | 88.9% | 92.1% |

Wilson 95% confidence intervals for the most consequential proportions:

| Metric | Deterministic + Luna | Luna only |
| --- | ---: | ---: |
| Coverage | [49.2%, 77.0%] | [77.9%, 96.2%] |
| Precision | [20.7%, 100.0%] | [20.7%, 100.0%] |
| End-to-end recall | [3.0%, 56.4%] | [3.0%, 56.4%] |
| End-to-end accuracy | [42.2%, 70.9%] | [69.4%, 91.7%] |

The apparent 100% precision is based on only **one** stable true-positive prediction and zero stable false positives for each architecture. Its interval is therefore very wide and must not be read as evidence of near-perfect precision.

Confusion and abstention counts:

- Hybrid: TP=1, FP=0, TN=23, FN=3, positive abstentions=2, negative abstentions=13.
- Luna only: TP=1, FP=0, TN=34, FN=3, positive abstentions=2, negative abstentions=2.

## Hybrid-stage diagnosis

- **Deterministic classifications:** 23 stable decisive cases (3 positive, 20 negative). The rules correctly classified 20 cases, but all 3 stable positives routed here were labeled nonproblematic.
- **Deterministic abstentions:** 11 stable decisive cases, all human-stable nonproblematic. These safe abstentions explain much of the hybrid coverage loss.
- **Luna semantic-review stage:** 8 stable decisive cases. It classified 4 and abstained on 4; all classified cases were correct, including the single detected stable positive.

The hybrid's main positive-class failure is therefore not merely LLM uncertainty. Three of the six stable positives were intercepted by deterministic lifecycle rules and labeled nonproblematic before Luna could inspect them.

## Paired comparison

- Both correct: 22
- Hybrid only correct: 2
- Luna only correct: 13
- Both incorrect: 5
- Exact McNemar p-value: 0.0074
- Hybrid minus Luna end-to-end accuracy: -26.2%, bootstrap 95% CI [-42.9%, -9.5%]
- Hybrid minus Luna end-to-end recall: 0.0%, bootstrap 95% CI [0.0%, 0.0%]

## Resource use

- Hybrid: 18 Luna calls, estimated API token cost **US$0.0323**.
- Luna only: 92 attempts for 90 final cases, estimated API token cost **US$0.1092**.

The estimate applies GPT-6 Luna standard text-token prices of US$0.10 per million uncached input tokens, US$0.01 per million cached input tokens, and US$0.50 per million output tokens. It excludes subscription accounting and any platform-specific overhead.

## Interpretation limits

The same human performed both rounds, so stable agreement measures repeatability rather than independent validity. Human and model evidence were not perfectly equivalent: the model used frozen repository evidence, while the human experienced live GitHub availability, including temporary failures. The primary reference contains only six stable positive cases. Results therefore support architecture triage and cost comparison, not a definitive claim of superiority.
