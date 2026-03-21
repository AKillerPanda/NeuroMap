"""
Stochastic Diffusion Search (SDS) — Fully Vectorised
-----------------------------------------------------
Two modes:
  1. Classic substring search  (stochastic_diffusion_search)
  2. Spell-correction / fuzzy word match  (spell_correct)
     Loads a dictionary from the CSV word-files in  ``words in english/``,
     filters out offensive / violent words, then uses SDS agents to find
     the closest dictionary words to a (possibly misspelled) input.

All agent operations are vectorised with NumPy — zero Python loops over agents.
"""
from __future__ import annotations
import csv
import os
from pathlib import Path

import numpy as np


# ═══════════════════════════════════════════════════════════════════════
# Offensive-word blocklist  (expand as needed)
# ═══════════════════════════════════════════════════════════════════════
_BLOCKED: frozenset[str] = frozenset({
	# violence
	"kill", "kills", "killed", "killer", "killing", "killings",
	"murder", "murders", "murdered", "murderer", "murdering",
	"death", "deaths", "die", "died", "dies", "dying",
	"suicide", "suicidal",
	"slaughter", "slaughtered", "slaughtering",
	"assassin", "assassinate", "assassinated", "assassination",
	"execute", "executed", "execution", "executioner",
	"massacre", "massacred",
	"homicide", "homicidal",
	"manslaughter",
	"strangle", "strangled", "strangulation",
	"suffocate", "suffocated", "suffocation",
	"decapitate", "decapitated", "decapitation",
	"mutilate", "mutilated", "mutilation",
	"torture", "tortured", "torturing",
	"stab", "stabbed", "stabbing",
	"shoot", "shooting",
	"genocide",
	# hate / slurs  (small representative set — extend as needed)
	"rape", "raped", "rapist", "raping",
	# weapons as primary meaning
	"bomb", "bombs", "bombing", "bomber",
})


# ═══════════════════════════════════════════════════════════════════════
# Dictionary loader  (cached after first call)
# ═══════════════════════════════════════════════════════════════════════
_DICT_CACHE: tuple[Path, list[str]] | None = None
_DICT_DIR: Path = Path(__file__).resolve().parent / "words in english"


def load_dictionary(directory: Path | str | None = None) -> list[str]:
	"""
	Load all words from the A–Z CSV files, strip whitespace, lower-case,
	de-duplicate, and filter out blocked words.

	The result is cached globally so subsequent calls with the same directory
	are free. Different directories produce different cached results.
	"""
	global _DICT_CACHE
	d = Path(directory) if directory is not None else _DICT_DIR
	
	# Return cached result only if the directory matches
	if _DICT_CACHE is not None and _DICT_CACHE[0] == d:
		return _DICT_CACHE[1]

	words: set[str] = set()

	for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
		csv_path = d / f"{letter}word.csv"
		if not csv_path.exists():
			continue
		with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
			reader = csv.reader(f)
			for row in reader:
				if row:
					w = row[0].strip().lower()
					if (
						w
						and w.isascii()
						and len(w) >= 2
						and w not in _BLOCKED
					):
						words.add(w)

	result = sorted(words)
	_DICT_CACHE = (d, result)
	return result


def clear_dictionary_cache() -> None:
	"""Force reload on next ``load_dictionary()`` call."""
	global _DICT_CACHE
	_DICT_CACHE = None


# ═══════════════════════════════════════════════════════════════════════
# 1.  Classic SDS — exact substring search  (original algorithm)
# ═══════════════════════════════════════════════════════════════════════
def stochastic_diffusion_search(
	search_space: str,
	model: str,
	n_agents: int = 10,
	max_iter: int = 30,
	*,
	seed: int | None = None,
	verbose: bool = True,
) -> tuple[int, float]:
	"""
	Run SDS to find *model* in *search_space*.

	Returns
	-------
	best_position  : int    index where model was found (−1 if not found)
	final_activity : float  fraction of active agents in [0, 1]
	"""
	S = len(search_space)
	M = len(model)
	N = n_agents
	max_pos = S - M + 1

	if max_pos <= 0:
		raise ValueError("model is longer than search_space")
	if M == 0:
		raise ValueError("model must be non-empty")

	# Validate that inputs contain only ASCII characters
	if not search_space.isascii():
		raise ValueError(
			f"search_space contains non-ASCII characters. "
			f"Only ASCII characters are supported. "
			f"Invalid character at position: {next(i for i, c in enumerate(search_space) if ord(c) > 127)}"
		)
	if not model.isascii():
		raise ValueError(
			f"model contains non-ASCII characters. "
			f"Only ASCII characters are supported. "
			f"Invalid character at position: {next(i for i, c in enumerate(model) if ord(c) > 127)}"
		)

	ss_arr = np.frombuffer(search_space.encode("ascii"), dtype=np.uint8)
	md_arr = np.frombuffer(model.encode("ascii"), dtype=np.uint8)

	rng = np.random.default_rng(seed)
	hypo = rng.integers(max_pos, size=N)
	status = np.zeros(N, dtype=bool)

	for _itr in range(max_iter):
		# ---- TEST PHASE (vectorised) ----
		micro = rng.integers(M, size=N)
		status = ss_arr[hypo + micro] == md_arr[micro]
		active_count = int(status.sum())

		# ---- DIFFUSION PHASE (vectorised) ----
		inactive = ~status
		partners = rng.integers(N, size=N)
		partner_active = status[partners]

		copy_mask = inactive & partner_active
		hypo[copy_mask] = hypo[partners[copy_mask]]

		random_mask = inactive & ~partner_active
		n_random = int(random_mask.sum())
		if n_random:
			hypo[random_mask] = rng.integers(max_pos, size=n_random)

		active_idx = np.flatnonzero(status)
		if active_idx.size > 0:
			micro2 = rng.integers(M, size=active_idx.size)
			status[active_idx] = (
				ss_arr[hypo[active_idx] + micro2] == md_arr[micro2]
			)

		if verbose:
			pct = active_count * 100.0 / N
			found_str = search_space[hypo[0] : hypo[0] + M]
			print(f"Active agents: {pct:5.1f}%  ... found: {found_str}")

	activity = float(status.sum()) / N
	best = int(hypo[np.flatnonzero(status)[0]]) if activity > 0 else -1
	return best, activity


# ═══════════════════════════════════════════════════════════════════════
# 2.  SDS spell-corrector — fuzzy dictionary matching (vectorised)
# ═══════════════════════════════════════════════════════════════════════
def _pad_words(words: list[str], max_len: int) -> np.ndarray:
	"""
	Convert a list of strings into a (W, max_len) uint8 matrix,
	padding shorter words with 0.  Fully vectorised after the initial
	encode pass.
	"""
	W = len(words)
	mat = np.zeros((W, max_len), dtype=np.uint8)
	for i, w in enumerate(words):
		encoded = w.encode("ascii", errors="replace")
		L = min(len(encoded), max_len)
		mat[i, :L] = np.frombuffer(encoded[:L], dtype=np.uint8)
	return mat


def spell_correct(
	word: str,
	*,
	top_k: int = 5,
	n_agents: int = 200,
	max_iter: int = 60,
	seed: int | None = None,
	dictionary: list[str] | None = None,
	verbose: bool = False,
) -> list[tuple[str, float]]:
	"""
	Use SDS to find the closest dictionary words to *word*.

	Pipeline:
	  1. Vectorised pre-filter — character-frequency + bigram overlap
	     narrows ~100 k words → ~150 candidates  (all in NumPy).
	  2. SDS refines that shortlist — agents cluster on the best matches
	     using per-character micro-feature testing.

	Parameters
	----------
	word       : str           the (possibly misspelled) input word
	top_k      : int           number of suggestions to return
	n_agents   : int           population size  (more → better quality)
	max_iter   : int           SDS iterations
	seed       : int|None      RNG seed for reproducibility
	dictionary : list[str]|None  custom word list (default: load from CSVs)
	verbose    : bool          print per-iteration status

	Returns
	-------
	list of (word, score) tuples sorted best-first.
	Score is in [0, 1] — fraction of character positions that matched.
	"""
	word = word.strip().lower()
	if not word:
		return []

	words = dictionary if dictionary is not None else load_dictionary()
	if not words:
		return []

	M = len(word)

	# ==================================================================
	# STAGE 1 — Vectorised pre-filter (cheap, runs over full dictionary)
	# ==================================================================

	# 1a. Length filter: keep words within ±3 of input length
	all_lens = np.array([len(w) for w in words], dtype=np.int32)
	len_ok = np.abs(all_lens - M) <= 3
	candidate_idx = np.flatnonzero(len_ok)

	if candidate_idx.size == 0:
		# fallback: relax to ±5
		len_ok = np.abs(all_lens - M) <= 5
		candidate_idx = np.flatnonzero(len_ok)
	if candidate_idx.size == 0:
		candidate_idx = np.arange(len(words))

	cand_words = [words[i] for i in candidate_idx]
	n_cand = len(cand_words)

	# 1b. Character-frequency similarity (fully vectorised via padded matrix)
	#     Build a (n_cand, 26) letter-count matrix and compare to input
	cand_max_len = max((len(w) for w in cand_words), default=1)
	cand_padded = _pad_words(cand_words, cand_max_len)     # (n_cand, cand_max_len) uint8
	# Vectorised char-freq: bin each row's characters into 26 buckets
	# Shift ASCII a=97..z=122 to 0..25; chars outside get clipped out
	def _vectorised_char_freq(padded_mat: np.ndarray) -> np.ndarray:
		"""(W, L) uint8 -> (W, 26) int16 letter frequency matrix, fully vectorised."""
		W, L = padded_mat.shape
		shifted = padded_mat.astype(np.int16) - 97  # a=0, z=25
		valid = (shifted >= 0) & (shifted < 26)
		freq = np.zeros((W, 26), dtype=np.int16)
		# Flatten and use np.add.at for vectorised bincount per row
		row_idx = np.broadcast_to(np.arange(W)[:, None], (W, L)).ravel()
		col_idx = np.clip(shifted, 0, 25).ravel()
		mask = valid.ravel()
		np.add.at(freq, (row_idx[mask], col_idx[mask]), 1)
		return freq

	cand_freq = _vectorised_char_freq(cand_padded)          # (n_cand, 26)
	# Input frequency vector
	input_padded = _pad_words([word], max(M, 1))             # (1, M)
	input_freq = _vectorised_char_freq(input_padded)          # (1, 26)

	# Similarity = sum of min(input_count, cand_count) / max_len
	freq_overlap = np.minimum(cand_freq, input_freq).sum(axis=1).astype(np.float64)
	freq_score = freq_overlap / max(M, 1)                      # (n_cand,)

	# 1c. Bigram overlap (vectorised via set hashing)
	def _bigrams(s: str) -> set[str]:
		return {s[i:i+2] for i in range(len(s) - 1)} if len(s) >= 2 else set()

	input_bg = _bigrams(word)
	if input_bg:
		# Vectorised bigram overlap using padded matrix
		# Build bigram pairs from padded matrix columns
		if cand_max_len >= 2:
			bg_left = cand_padded[:, :-1]   # (n_cand, L-1)
			bg_right = cand_padded[:, 1:]   # (n_cand, L-1)
			# Encode bigrams as uint16: left*256 + right
			cand_bg_encoded = bg_left.astype(np.uint16) * 256 + bg_right.astype(np.uint16)
			# Only count where both chars are non-zero (not padding)
			bg_valid = (bg_left > 0) & (bg_right > 0)
			# Encode input bigrams the same way
			input_bg_encoded = set()
			for bg in input_bg:
				if len(bg) == 2:
					input_bg_encoded.add(ord(bg[0]) * 256 + ord(bg[1]))
			input_bg_arr = np.array(list(input_bg_encoded), dtype=np.uint16)
			# Count matches: for each candidate, how many of its bigrams are in input
			# Use broadcasting: (n_cand, L-1, 1) == (1, 1, n_input_bg)
			if input_bg_arr.size > 0:
				matches = np.isin(cand_bg_encoded, input_bg_arr) & bg_valid
				bg_scores = matches.sum(axis=1).astype(np.float64) / max(len(input_bg), 1)
			else:
				bg_scores = np.zeros(n_cand, dtype=np.float64)
		else:
			bg_scores = np.zeros(n_cand, dtype=np.float64)
	else:
		bg_scores = np.zeros(n_cand, dtype=np.float64)

	# Vectorised prefix scoring via padded matrix
	word_bytes = word.encode("ascii", errors="replace")
	prefix_scores = np.zeros(n_cand, dtype=np.float64)
	if M >= 1 and cand_max_len >= 1:
		first_match = cand_padded[:, 0] == word_bytes[0]
		prefix_scores[first_match] += 0.3
		if M >= 2 and cand_max_len >= 2:
			second_match = first_match & (cand_padded[:, 1] == word_bytes[1])
			prefix_scores[second_match] += 0.3

	pre_score = freq_score * 0.4 + bg_scores * 0.4 + prefix_scores * 0.2

	# Keep top 200 candidates (or fewer if not enough)
	shortlist_size = min(200, n_cand)
	top_pre = np.argpartition(pre_score, -shortlist_size)[-shortlist_size:]
	candidates = [cand_words[i] for i in top_pre]
	pre_scores_kept = pre_score[top_pre]

	W = len(candidates)
	if W == 0:
		return []

	# ==================================================================
	# STAGE 2 — SDS refinement over the shortlist
	# ==================================================================
	N = n_agents
	max_len = max(max(len(w) for w in candidates), M)
	dict_mat = _pad_words(candidates, max_len)  # (W, max_len)

	model_arr = np.zeros(max_len, dtype=np.uint8)
	enc = word.encode("ascii", errors="replace")[:max_len]
	model_arr[: len(enc)] = np.frombuffer(enc, dtype=np.uint8)

	word_lens = np.array([len(w) for w in candidates], dtype=np.int32)

	rng = np.random.default_rng(seed)
	hypo = rng.integers(W, size=N)
	status = np.zeros(N, dtype=bool)
	hit_counts = np.zeros(W, dtype=np.float64)

	for _itr in range(max_iter):
		# ---- TEST PHASE (fuzzy: char at pos p matches if it appears ----
		#       in the candidate at positions p-1, p, or p+1)
		effective_len = np.maximum(np.minimum(word_lens[hypo], M), 1)
		micro = (rng.random(N) * effective_len).astype(np.int64)
		model_chars = model_arr[micro]

		# Check pos p, p-1, p+1 — "fuzzy" micro-feature test
		match_center = dict_mat[hypo, micro] == model_chars
		micro_left = np.maximum(micro - 1, 0)
		match_left = dict_mat[hypo, micro_left] == model_chars
		micro_right = np.minimum(micro + 1, max_len - 1)
		match_right = dict_mat[hypo, micro_right] == model_chars
		status = match_center | match_left | match_right

		active_count = int(status.sum())

		if active_count > 0:
			np.add.at(hit_counts, hypo[status], 1.0)

		# ---- DIFFUSION PHASE ----
		inactive = ~status
		partners = rng.integers(N, size=N)
		partner_active = status[partners]

		copy_mask = inactive & partner_active
		hypo[copy_mask] = hypo[partners[copy_mask]]

		random_mask = inactive & ~partner_active
		n_random = int(random_mask.sum())
		if n_random:
			hypo[random_mask] = rng.integers(W, size=n_random)

		active_idx = np.flatnonzero(status)
		if active_idx.size > 0:
			elen2 = np.maximum(np.minimum(word_lens[hypo[active_idx]], M), 1)
			micro2 = (rng.random(active_idx.size) * elen2).astype(np.int64)
			mc2 = model_arr[micro2]
			mc_center = dict_mat[hypo[active_idx], micro2] == mc2
			mc_left   = dict_mat[hypo[active_idx], np.maximum(micro2 - 1, 0)] == mc2
			mc_right  = dict_mat[hypo[active_idx], np.minimum(micro2 + 1, max_len - 1)] == mc2
			status[active_idx] = mc_center | mc_left | mc_right

		if verbose:
			pct = active_count * 100.0 / N
			best_idx = int(hypo[0])
			print(f"  iter {_itr:>3}: active {pct:5.1f}%  hypo[0]={candidates[best_idx]}")

	# ---- Combine SDS hits + pre-filter score + direct overlap + length penalty ----
	compare_len = min(M, max_len)
	model_row = model_arr[:compare_len][np.newaxis, :]
	dict_rows = dict_mat[:, :compare_len]
	char_match = (dict_rows == model_row).sum(axis=1).astype(np.float64)
	max_possible = np.maximum(word_lens, M).astype(np.float64)
	char_similarity = char_match / np.maximum(max_possible, 1.0)

	# Length penalty: strongly prefer words of exact or very similar length
	len_diff = np.abs(word_lens - M).astype(np.float64)
	len_penalty = 1.0 / (1.0 + len_diff * len_diff)  # quadratic falloff

	combined = (
		hit_counts * 1.0
		+ char_similarity * max_iter * 3.5
		+ pre_scores_kept * max_iter * 1.5
		+ len_penalty * max_iter * 1.0
	)

	k = min(top_k, W)
	# Get a wider set of finalists, then re-rank by edit distance
	finalist_k = min(k * 3, W)
	if finalist_k < 1:
		finalist_k = 1
	finalist_indices = np.argpartition(combined, -finalist_k)[-finalist_k:]

	# ---- Lightweight Levenshtein for the finalists only (≤15 words) ----
	def _edit_distance(a: str, b: str) -> int:
		"""Optimised Levenshtein via single-row DP (O(min(m,n)) space)."""
		if len(a) < len(b):
			a, b = b, a
		if not b:
			return len(a)
		prev = list(range(len(b) + 1))
		for i, ca in enumerate(a):
			curr = [i + 1] + [0] * len(b)
			for j, cb in enumerate(b):
				curr[j + 1] = min(
					prev[j + 1] + 1,       # deletion
					curr[j] + 1,            # insertion
					prev[j] + (ca != cb),   # substitution
				)
			prev = curr
		return prev[-1]

	ed_scores = np.array(
		[_edit_distance(word, candidates[i]) for i in finalist_indices],
		dtype=np.float64,
	)
	# Normalise: lower distance → higher score
	max_ed = ed_scores.max() if ed_scores.max() > 0 else 1.0
	ed_bonus = (1.0 - ed_scores / (max_ed + 1.0)) * max_iter * 2.0

	# Re-rank finalists using combined + edit-distance bonus
	final_scores = combined[finalist_indices] + ed_bonus
	sorted_order = np.argsort(final_scores)[::-1][:k]
	top_indices = finalist_indices[sorted_order]

	results: list[tuple[str, float]] = []
	best_combined = combined[top_indices[0]] if top_indices.size else 1.0
	if best_combined <= 0:
		best_combined = 1.0
	for idx in top_indices:
		norm_score = float(combined[idx]) / best_combined
		results.append((candidates[idx], round(norm_score, 4)))

	return results


def correct_phrase(
	phrase: str,
	*,
	top_k: int = 3,
	n_agents: int = 200,
	max_iter: int = 50,
	seed: int | None = None,
	verbose: bool = False,
) -> list[list[tuple[str, float]]]:
	"""
	Spell-correct every word in a phrase.

	Returns a list (one per input word) of top-k suggestions.
	If a word is already in the dictionary it's returned as-is with score 1.0.
	"""
	dictionary = load_dictionary()
	dict_set = set(dictionary)
	results: list[list[tuple[str, float]]] = []

	for token in phrase.strip().split():
		clean = token.strip().lower()
		if not clean:
			continue
		if clean in dict_set:
			results.append([(clean, 1.0)])
		else:
			suggestions = spell_correct(
				clean,
				top_k=top_k,
				n_agents=n_agents,
				max_iter=max_iter,
				seed=seed,
				dictionary=dictionary,
				verbose=verbose,
			)
			results.append(suggestions)

	return results


# ═══════════════════════════════════════════════════════════════════════
# Interactive demo
# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
	import sys

	print("=" * 60)
	print("  NeuraLearn — SDS Spell Corrector")
	print("=" * 60)
	print(f"Loading dictionary from: {_DICT_DIR}")
	words = load_dictionary()
	print(f"  {len(words):,} words loaded (offensive words filtered)\n")

	# If arguments given, correct them and exit
	if len(sys.argv) > 1:
		phrase = " ".join(sys.argv[1:])
		print(f"Input: \"{phrase}\"\n")
		per_word = correct_phrase(phrase, top_k=5)
		for token, suggestions in zip(phrase.split(), per_word):
			print(f"  '{token}' →", end="")
			for w, sc in suggestions[:5]:
				print(f"  {w} ({sc:.2f})", end="")
			print()
		sys.exit(0)

	# Interactive mode
	print("Type a word or phrase to spell-check (or 'quit' to exit):\n")
	while True:
		try:
			user_input = input(">>> ").strip()
		except (EOFError, KeyboardInterrupt):
			print("\nBye!")
			break

		if not user_input or user_input.lower() in ("quit", "exit", "q"):
			print("Bye!")
			break

		per_word = correct_phrase(user_input, top_k=5)
		print()
		for token, suggestions in zip(user_input.split(), per_word):
			if len(suggestions) == 1 and suggestions[0][1] == 1.0:
				print(f"  '{token}' ✓  (in dictionary)")
			else:
				print(f"  '{token}' →  suggestions:")
				for w, sc in suggestions:
					bar = "█" * int(sc * 20)
					print(f"      {w:<25} {sc:.2f}  {bar}")
		print()
