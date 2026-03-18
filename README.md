# Laboratory Work 1: Intro to Formal Languages, Regular Grammars, and Finite Automata

**Course:** Formal Languages & Finite Automata  
**Author:** Chiril  
**Variant:** 15  

---

## 1. Overview and Theory

A **Formal Language** is a set of strings of symbols that are constrained by rules specific to that language. It acts as the fundamental format used to convey information from a sender to a receiver. The core components of a formal language include:
- **The Alphabet ($V_T$ or $\Sigma$):** A finite, non-empty set of valid characters (terminals).
- **The Vocabulary ($V_N$):** A finite, non-empty set of non-terminal symbols used to generate patterns.
- **The Grammar ($G$):** A formal set of production rules that dictates how strings can be formed from the language's alphabet.

According to the **Chomsky Hierarchy**, grammars are classified into four types. This project focuses on **Type-3 Grammars (Regular Grammars)**, which can be expressed via regular expressions and parsed by Finite State Automata. Specifically, this implementation deals with a **Right-Linear Grammar**, where all production rules have at most one non-terminal, and it strictly appears at the rightmost end of the production.

## 2. Objectives

1. Understand the mathematical foundation of formal languages and regular grammars.
2. Establish a modular project structure in Java and a version control environment via GitHub.
3. Implement an object-oriented solution for a specific grammar variant (Variant 15) that can:
   - Encapsulate the grammar's state and rules.
   - Generate valid strings defined by the grammar.
   - Algorithmically convert the `Grammar` object into a `FiniteAutomaton` object.
   - Validate if arbitrary strings belong to the language using the constructed Finite Automaton.

---

## 3. Variant 15 Definition

This project is built around the following strictly defined parameters for Variant 15:

* **Non-terminals ($V_N$):** `{S, A, B}`
* **Terminals ($V_T$):** `{a, b, c}`
* **Start Symbol:** `S`
* **Production Rules ($P$):**
  1. `S → aS`
  2. `S → bS`
  3. `S → cA`
  4. `A → aB`
  5. `B → aB`
  6. `B → bB`
  7. `B → c`

### Mathematical Behavior
Analyzing the rules, the language allows an infinite sequence of `a`'s and `b`'s at the beginning (looping on state `S`). To progress, a `c` must be generated to reach state `A`. From `A`, an `a` is strictly required to reach `B`. Finally, in state `B`, another infinite loop of `a`'s and `b`'s can occur, but the string can *only* terminate when a final `c` is generated. 

---

## 4. Project Structure & Implementation Details

The project is written in **Java** and divided into three main components:

### `Grammar.java`
This class encapsulates the components of the formal language.
* **String Generation Algorithm (`generateString`):** Because the grammar is Right-Linear, the generation process is simplified. The algorithm uses a `StringBuilder` and a `while` loop. It examines the last character of the current string; if it is a Non-Terminal, it randomly selects one of the associated production rules and replaces it. The loop terminates naturally when the final character is a Terminal.
* **FA Conversion (`toFiniteAutomaton`):** This method maps the regular grammar directly to an FA. 
  - Every element in $V_N$ becomes a state in $Q$.
  - A new, explicit final state `X` is added to handle terminal-only productions.
  - Productions of the form `A → aB` are mapped as a transition from state `A` to state `B` via input `a`.
  - Productions of the form `B → c` are mapped as a transition from state `B` to the final state `X` via input `c`.

### `FiniteAutomaton.java`
This class represents the deterministic/non-deterministic finite automaton.
* **Validation Algorithm (`stringBelongToLanguage`):** It simulates the state machine. Starting from the initial state (`q0`), it iterates character by character through the input string. It maintains a `Set` of current active states. For each character, it looks up the transition table (`delta`) to find the next possible states. If the string is fully consumed and at least one of the active states is in the set of Final States ($F$), the string is accepted.

### `Main.java`
The client class that instantiates the `Grammar`, triggers the generation of 5 random valid words, converts the grammar to an FA, and tests both the valid words and an intentionally invalid word to prove the robustness of the FA.

---

