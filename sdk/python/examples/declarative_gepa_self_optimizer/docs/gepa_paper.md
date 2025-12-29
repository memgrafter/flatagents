# GEPA Core Implementation Extract

## Algorithm 1: Main Loop
```
Inputs: System Φ, dataset D_train, metric μ, feedback μ_f, budget B
Hyperparams: minibatch_size b, pareto_set_size n_pareto

1. Split D_train into D_feedback, D_pareto (|D_pareto| = n_pareto)
2. Initialize candidates P ← [Φ], parents A ← [None]
3. Evaluate base system on D_pareto → S[Φ]
4. While budget B not exhausted:
   a. k ← SelectCandidate(P, S)  # Pareto sampling
   b. j ← SelectModule(Φ_k)      # Round-robin
   c. M ← sample minibatch of size b from D_feedback
   d. Execute Φ_k on M, gather traces and feedback via μ_f
   e. π'_j ← ReflectiveUpdate(π_j, feedbacks, traces)
   f. Φ' ← copy Φ_k with module j updated to π'_j
   g. If score improved on M:
      - Add Φ' to P, record parent k in A
      - Evaluate Φ' on full D_pareto → S[Φ']
5. Return candidate maximizing average score on D_pareto
```

## Algorithm 2: Pareto-Based Candidate Selection
```
function SelectCandidate(P, S):
  # Find best candidates per instance
  for each instance i:
    s*[i] ← max_k S[P[k]][i]
    P*[i] ← {P[k] : S[P[k]][i] = s*[i]}
  
  # Collect Pareto frontier
  C ← unique candidates in ∪_i P*[i]
  
  # Remove dominated candidates
  Remove Φ from C if ∃Φ' in C that dominates Φ
  
  # Sample by frequency
  f[Φ] ← count of instances where Φ achieves best
  Sample Φ_k with probability ∝ f[Φ_k]
  return k
```

## Reflective Prompt Mutation Meta-Prompt
```
I provided an assistant with the following instructions:
'''
{current_instruction}
'''

Examples of task inputs, assistant responses, and feedback:
'''
{inputs_outputs_feedbacks}
'''

Your task: Write a new instruction for the assistant.

- Identify input format and detailed task description
- Extract all domain-specific factual information from feedback
- Include any generalizable strategies the assistant used
- Provide new instructions within ''' blocks
```

## Key Design Principles

1. **Feedback Function μ_f**: Extends metric μ to return (score, feedback_text). Feedback includes execution traces, error messages, intermediate results.

2. **Module Selection**: Round-robin across modules ensures all receive updates.

3. **Minibatch Evaluation**: New candidates first tested on minibatch; only promoted to full evaluation if improved.

4. **Pareto Illumination**: Maintains diversity by sampling from candidates that achieve best score on *any* instance, avoiding local optima.

5. **Ancestry Tracking**: Each candidate records parent, enabling accumulated learning across genetic tree.
