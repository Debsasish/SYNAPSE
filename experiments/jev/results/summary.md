
## T = 300, seed = 1

| arm | hit@1 | with tag | no tag | gold in list | hit@1 when gold in list | abstain (real) | miss abstain |
|---|---:|---:|---:|---:|---:|---:|---:|
| synapse8 | 0.633 | 0.758 | 0.292 | 0.878 | 0.722 | 0.156 | 5/5 |
| synapse32 | 0.567 | 0.652 | 0.333 | 0.878 | 0.646 | 0.156 | 5/5 |
| lexical32 | 0.578 | 0.606 | 0.500 | 1.000 | 0.578 | 0.033 | 5/5 |
| synapse_only | 0.811 | 0.909 | 0.542 | 0.878 | 0.924 | 0.122 | 5/5 |

n = 90 real tasks + 5 should-miss tasks per arm.

Errors on real tasks where the gold capability WAS in the shortlist:

| arm | errors | look-alike | different capability | abstained |
|---|---:|---:|---:|---:|
| synapse8 | 22 | 11 | 8 | 3 |
| synapse32 | 28 | 18 | 7 | 3 |
| lexical32 | 38 | 23 | 12 | 3 |
| synapse_only | 6 | 0 | 6 | 0 |

## T = 1000, seed = 1

| arm | hit@1 | with tag | no tag | gold in list | hit@1 when gold in list | abstain (real) | miss abstain |
|---|---:|---:|---:|---:|---:|---:|---:|
| synapse8 | 0.411 | 0.530 | 0.083 | 0.900 | 0.457 | 0.122 | 5/5 |
| synapse32 | 0.389 | 0.515 | 0.042 | 0.900 | 0.432 | 0.122 | 5/5 |
| lexical32 | 0.100 | 0.136 | 0.000 | 0.233 | 0.429 | 0.200 | 5/5 |
| synapse_only | 0.822 | 0.909 | 0.583 | 0.900 | 0.914 | 0.100 | 5/5 |

n = 90 real tasks + 5 should-miss tasks per arm.

Errors on real tasks where the gold capability WAS in the shortlist:

| arm | errors | look-alike | different capability | abstained |
|---|---:|---:|---:|---:|
| synapse8 | 44 | 31 | 11 | 2 |
| synapse32 | 46 | 34 | 10 | 2 |
| lexical32 | 12 | 7 | 5 | 0 |
| synapse_only | 7 | 0 | 7 | 0 |
