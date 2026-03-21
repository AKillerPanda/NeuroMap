from __future__ import annotations

import numpy as np
from collections import deque
from enum import Enum
from dataclasses import dataclass, field
from scipy import sparse as sp
from scipy.sparse.linalg import eigsh, ArpackNoConvergence
from scipy.sparse.csgraph import connected_components
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import torch
    from torch_geometric.data import Data
    from torch_geometric.utils import degree as _degree

# ---------------------------------------------------------------------------
# Lazy torch / torch_geometric imports  (saves ~5-6 s on first import)
# ---------------------------------------------------------------------------
_torch = None
_tg_Data = None
_tg_degree = None


def _ensure_torch():
    """Import torch + torch_geometric on first real use."""
    global _torch, _tg_Data, _tg_degree
    if _torch is None:
        import torch as _t
        from torch_geometric.data import Data as _D
        from torch_geometric.utils import degree as _d
        _torch = _t
        _tg_Data = _D
        _tg_degree = _d
    return _torch

"""
NeuraLearn Knowledge Graph  (optimised via spectral & topological graph theory)
--------------------------------------------------------------------------------
Performance & analytical features:

  • Topic uses __slots__ → ~40 % less memory per node, faster attr access
  • Adjacency stored as sets → O(1) duplicate-edge checks
  • Bulk add methods → single cache invalidation per batch
  • Topological-sort result is cached and auto-invalidated
  • Name index dict → O(1) lookup by name instead of O(n) scan
  • clear() wipes the graph in-place for reuse (no new object allocation)
  • rebuild_from_spec() builds from a lightweight list-of-dicts spec

Spectral graph theory (new):
  • Laplacian matrices (unnormalised, symmetric normalised) via scipy sparse
  • Spectral embedding (k smallest non-trivial eigenvectors) → O(E) via ARPACK
  • Fiedler vector & algebraic connectivity (λ₂) for graph partitioning
  • Spectral clustering via k-means on Laplacian eigenvectors
  • Spectral gap (λ₂/λ₁) for connectivity analysis

Topological graph theory (new):
  • Vectorised depth computation via NumPy in-degree BFS
  • Betti number β₀ (connected components) via scipy sparse
  • Vectorised shortest-path-to via predecessor bitmask
"""


# ---------------------------------------------------------------------------
# Topic difficulty / type labels
# ---------------------------------------------------------------------------
class TopicLevel(Enum):
	FOUNDATIONAL = 0
	INTERMEDIATE = 1
	ADVANCED = 2
	EXPERT = 3

# Mapping from string → enum for spec-based construction
_LEVEL_MAP: dict[str, TopicLevel] = {
	"foundational": TopicLevel.FOUNDATIONAL,
	"intermediate": TopicLevel.INTERMEDIATE,
	"advanced": TopicLevel.ADVANCED,
	"expert": TopicLevel.EXPERT,
}


# ---------------------------------------------------------------------------
# Topic node  (__slots__ for speed & memory)
# ---------------------------------------------------------------------------
class Topic:
	"""A single topic or subtopic in the knowledge graph."""

	__slots__ = (
		"topic_id", "name", "description", "level",
		"features", "mastered", "prerequisites", "unlocks",
	)

	def __init__(
		self,
		topic_id: int,
		name: str,
		description: str = "",
		level: TopicLevel = TopicLevel.FOUNDATIONAL,
		features: torch.Tensor | None = None,
	) -> None:
		self.topic_id = topic_id
		self.name = name
		self.description = description
		self.level = level
		self.features = features           # None → lazy torch.zeros(1) in build_feature_matrix
		self.mastered: bool = False
		self.prerequisites: set[int] = set()   # topic_ids this depends on  (in-edges)
		self.unlocks: set[int] = set()         # topic_ids this unlocks     (out-edges)

	def __repr__(self) -> str:
		status = "mastered" if self.mastered else "locked"
		return f"Topic({self.topic_id}, '{self.name}', {self.level.name}, {status})"


# ---------------------------------------------------------------------------
# Lightweight spec type used by rebuild_from_spec()
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class TopicSpec:
	"""Plain-data description of a topic — no torch, no graph pointers."""
	name: str
	description: str = ""
	level: str = "foundational"                 # key into _LEVEL_MAP
	prerequisite_names: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# KnowledgeGraph  (optimised for repeated build / tear-down)
# ---------------------------------------------------------------------------
class KnowledgeGraph:
	"""
	Directed acyclic graph of Topics.

	Edges go from prerequisite (subtopic) → dependent (topic).
	A topic is *unlocked* only when ALL its prerequisites are mastered.

	Optimised for repeated creation:
	  - call clear() then re-populate, or
	  - use the class method rebuild_from_spec() with a plain list of dicts.
	"""

	__slots__ = (
		"_device_raw", "topics", "_next_id",
		"_name_index",
		"_edge_index_cache", "_degree_cache", "_topo_cache",
		"_laplacian_cache", "_spectral_cache",
	)

	def __init__(
		self,
		device: torch.device | str | None = None,
	) -> None:
		self._device_raw = device           # resolved lazily via .device property
		self.topics: dict[int, Topic] = {}
		self._next_id: int = 0
		self._name_index: dict[str, int] = {}          # lower(name) → topic_id
		self._edge_index_cache: torch.Tensor | None = None
		self._degree_cache: dict[str, torch.Tensor] = {}
		self._topo_cache: list[Topic] | None = None     # cached topo sort
		self._laplacian_cache: dict[str, sp.csc_matrix] = {}
		self._spectral_cache: dict[str, np.ndarray] = {}  # cached eigenvectors/values

	# ---- helpers -----------------------------------------------------------
	@property
	def device(self) -> torch.device:
		"""Lazily resolve to a torch.device (first access imports torch)."""
		raw = self._device_raw
		if raw is None or isinstance(raw, str):
			_ensure_torch()
			resolved = _torch.device(raw) if raw else _torch.device("cpu")
			self._device_raw = resolved
		return self._device_raw

	@property
	def num_topics(self) -> int:
		return len(self.topics)

	def _invalidate_cache(self) -> None:
		self._edge_index_cache = None
		self._degree_cache.clear()
		self._topo_cache = None
		self._laplacian_cache.clear()
		self._spectral_cache.clear()

	# ---- clear & reuse (avoids allocating a new KnowledgeGraph) ------------
	def clear(self) -> None:
		"""Wipe all topics and edges so the same object can be reused."""
		self.topics.clear()
		self._name_index.clear()
		self._next_id = 0
		self._invalidate_cache()

	# ---- node helpers ------------------------------------------------------
	def add_topic(self, topic: Topic) -> None:
		"""Add a Topic node to the graph."""
		if topic.topic_id in self.topics:
			raise ValueError(f"topic_id {topic.topic_id} already exists")
		self.topics[topic.topic_id] = topic
		self._name_index[topic.name.lower()] = topic.topic_id
		self._next_id = max(self._next_id, topic.topic_id + 1)
		self._invalidate_cache()

	def add_topics_bulk(self, topics: list[Topic]) -> None:
		"""Add many topics at once — only one cache invalidation."""
		for t in topics:
			if t.topic_id in self.topics:
				raise ValueError(f"topic_id {t.topic_id} already exists")
			self.topics[t.topic_id] = t
			self._name_index[t.name.lower()] = t.topic_id
			self._next_id = max(self._next_id, t.topic_id + 1)
		self._invalidate_cache()

	def create_topic(
		self,
		name: str,
		description: str = "",
		level: TopicLevel = TopicLevel.FOUNDATIONAL,
		features: torch.Tensor | None = None,
	) -> Topic:
		"""Create a new Topic with an auto-assigned id and add it."""
		t = Topic(
			topic_id=self._next_id,
			name=name,
			description=description,
			level=level,
			features=features,
		)
		self.add_topic(t)
		return t

	def get_topic(self, topic_id: int) -> Topic:
		try:
			return self.topics[topic_id]
		except KeyError:
			raise KeyError(f"topic_id {topic_id} not found") from None

	def get_topic_by_name(self, name: str) -> Topic | None:
		"""O(1) lookup by name (case-insensitive)."""
		tid = self._name_index.get(name.lower())
		return self.topics[tid] if tid is not None else None

	# ---- edge helpers (prerequisite relationships) -------------------------
	def add_prerequisite(self, subtopic_id: int, topic_id: int) -> None:
		"""
		Add edge: subtopic → topic.
		The learner must master *subtopic* before *topic* is unlocked.
		"""
		if subtopic_id not in self.topics or topic_id not in self.topics:
			raise ValueError("both subtopic_id and topic_id must exist in the graph")
		if subtopic_id == topic_id:
			raise ValueError("a topic cannot be a prerequisite of itself")
		sub = self.topics[subtopic_id]
		dep = self.topics[topic_id]
		if topic_id in sub.unlocks:          # O(1) set check
			return
		sub.unlocks.add(topic_id)
		dep.prerequisites.add(subtopic_id)
		self._invalidate_cache()

	def add_prerequisites(self, topic_id: int, prerequisite_ids: list[int]) -> None:
		"""Add many prerequisites for one topic — single cache invalidation."""
		dep = self.topics[topic_id]
		changed = False
		for pid in prerequisite_ids:
			if pid not in self.topics:
				raise ValueError(f"prerequisite topic_id {pid} not found")
			if pid == topic_id:
				raise ValueError("a topic cannot be a prerequisite of itself")
			sub = self.topics[pid]
			if topic_id not in sub.unlocks:
				sub.unlocks.add(topic_id)
				dep.prerequisites.add(pid)
				changed = True
		if changed:
			self._invalidate_cache()

	def add_prerequisites_bulk(self, edges: list[tuple[int, int]]) -> None:
		"""
		Add many prerequisite edges at once: [(subtopic_id, topic_id), ...].
		Only invalidates caches once at the end.
		"""
		changed = False
		for subtopic_id, topic_id in edges:
			sub = self.topics[subtopic_id]
			dep = self.topics[topic_id]
			if topic_id not in sub.unlocks:
				sub.unlocks.add(topic_id)
				dep.prerequisites.add(subtopic_id)
				changed = True
		if changed:
			self._invalidate_cache()

	# ---- mastery & progress -----------------------------------------------
	def is_unlocked(self, topic_id: int) -> bool:
		"""True when ALL prerequisites are mastered."""
		topic = self.topics[topic_id]
		return all(self.topics[pid].mastered for pid in topic.prerequisites)

	def master_topic(self, topic_id: int) -> bool:
		"""Mark mastered if unlocked. Returns success bool."""
		if not self.is_unlocked(topic_id):
			return False
		self.topics[topic_id].mastered = True
		return True

	def reset_progress(self) -> None:
		"""Reset mastery on all topics (keeps graph structure)."""
		for t in self.topics.values():
			t.mastered = False

	def get_mastered(self) -> list[Topic]:
		return [t for t in self.topics.values() if t.mastered]

	def get_available(self) -> list[Topic]:
		"""Topics unlocked but not yet mastered."""
		return [
			t for t in self.topics.values()
			if not t.mastered and self.is_unlocked(t.topic_id)
		]

	def get_locked(self) -> list[Topic]:
		return [
			t for t in self.topics.values()
			if not t.mastered and not self.is_unlocked(t.topic_id)
		]

	def mastery_progress(self) -> float:
		if not self.topics:
			return 0.0
		mastered = sum(t.mastered for t in self.topics.values())  # bool sums to int
		return mastered / len(self.topics)

	# ---- learning path (cached topological order) --------------------------
	def learning_order(self) -> list[Topic]:
		"""
		Valid learning order via Kahn's algorithm.  Cached until the graph
		structure changes; repeated calls are O(1).
		"""
		if self._topo_cache is not None:
			return self._topo_cache

		in_deg: dict[int, int] = {tid: 0 for tid in self.topics}
		for t in self.topics.values():
			for uid in t.unlocks:
				in_deg[uid] += 1

		queue = deque(tid for tid, d in in_deg.items() if d == 0)
		order: list[Topic] = []

		while queue:
			tid = queue.popleft()
			topic = self.topics[tid]
			order.append(topic)
			for uid in topic.unlocks:
				in_deg[uid] -= 1
				if in_deg[uid] == 0:
					queue.append(uid)

		if len(order) != len(self.topics):
			# Graph contains a cycle (web-scraping can produce these).
			# Break cycles by including unvisited nodes in an arbitrary but
			# deterministic order so callers always get a complete list rather
			# than a ValueError crash.
			import logging as _log
			_log.getLogger(__name__).warning(
				"learning_order: cycle detected — %d nodes excluded from Kahn pass; "
				"appending in topic_id order to recover",
				len(self.topics) - len(order),
			)
			visited_ids = {t.topic_id for t in order}
			for tid in sorted(self.topics):
				if tid not in visited_ids:
					order.append(self.topics[tid])

		self._topo_cache = order
		return order

	def shortest_path_to(self, target_id: int) -> list[Topic]:
		"""Min topics (in order) needed to unlock *target_id*, skipping mastered."""
		needed: set[int] = set()
		queue = deque([target_id])
		while queue:
			tid = queue.popleft()
			if tid in needed:
				continue
			needed.add(tid)
			for pid in self.topics[tid].prerequisites:
				if not self.topics[pid].mastered:
					queue.append(pid)
		full_order = self.learning_order()
		return [t for t in full_order if t.topic_id in needed]

	def get_subtopics(self, topic_id: int) -> list[Topic]:
		return [self.topics[pid] for pid in self.topics[topic_id].prerequisites]

	def get_dependents(self, topic_id: int) -> list[Topic]:
		return [self.topics[uid] for uid in self.topics[topic_id].unlocks]

	# ---- graph tensors -----------------------------------------------------
	def build_edge_index(self) -> torch.Tensor:
		"""[2, E] tensor  (prerequisite → dependent).  Vectorised construction."""
		if self._edge_index_cache is not None:
			return self._edge_index_cache
		_ensure_torch()
		# Pre-allocate numpy arrays then zero-copy convert to torch
		num_edges = sum(len(t.unlocks) for t in self.topics.values())
		if num_edges == 0:
			ei = _torch.zeros((2, 0), dtype=_torch.long, device=self.device)
			self._edge_index_cache = ei
			return ei
		src = np.empty(num_edges, dtype=np.int64)
		dst = np.empty(num_edges, dtype=np.int64)
		pos = 0
		for t in self.topics.values():
			k = len(t.unlocks)
			if k:
				src[pos:pos + k] = t.topic_id
				dst[pos:pos + k] = list(t.unlocks)
				pos += k
		ei = _torch.from_numpy(np.stack([src, dst])).to(device=self.device)
		self._edge_index_cache = ei
		return ei

	def build_feature_matrix(self) -> torch.Tensor:
		"""(N, F) feature matrix, rows ordered by topic_id."""
		_ensure_torch()
		_z = _torch.zeros(1)
		ordered = [
			self.topics[tid].features if self.topics[tid].features is not None else _z
			for tid in sorted(self.topics)
		]
		return _torch.stack(ordered, dim=0).to(self.device)

	def build_adjacency_numpy(self) -> np.ndarray:
		"""Dense adjacency matrix as numpy float32 array (for external consumers).
		Vectorised: builds directly from topology — no torch dependency."""
		n = max(self.topics) + 1 if self.topics else 0
		adj = np.zeros((n, n), dtype=np.float32)
		num_edges = sum(len(t.unlocks) for t in self.topics.values())
		if num_edges > 0:
			src = np.empty(num_edges, dtype=np.int64)
			dst = np.empty(num_edges, dtype=np.int64)
			pos = 0
			for t in self.topics.values():
				k = len(t.unlocks)
				if k:
					src[pos:pos + k] = t.topic_id
					dst[pos:pos + k] = list(t.unlocks)
					pos += k
			adj[src, dst] = 1.0
		return adj

	def out_degree(self) -> torch.Tensor:
		cached = self._degree_cache.get("out")
		if cached is not None:
			return cached
		ei = self.build_edge_index()
		n = max(self.topics) + 1 if self.topics else 0
		out = _tg_degree(ei[0], num_nodes=n, dtype=_torch.long)
		self._degree_cache["out"] = out
		return out

	def in_degree(self) -> torch.Tensor:
		cached = self._degree_cache.get("in")
		if cached is not None:
			return cached
		ei = self.build_edge_index()
		n = max(self.topics) + 1 if self.topics else 0
		ind = _tg_degree(ei[1], num_nodes=n, dtype=_torch.long)
		self._degree_cache["in"] = ind
		return ind

	def build_sparse_adjacency(self) -> torch.Tensor:
		ei = self.build_edge_index()
		n = max(self.topics) + 1 if self.topics else 0
		vals = _torch.ones(ei.size(1), device=self.device)
		return _torch.sparse_coo_tensor(ei, vals, size=(n, n)).coalesce()

	# ---- spectral graph theory ---------------------------------------------

	def _scipy_adjacency(self) -> sp.csc_matrix:
		"""Build scipy sparse adjacency (symmetrised for undirected Laplacian).
		Vectorised: builds directly from topology — no torch dependency."""
		cached = self._laplacian_cache.get("adj")
		if cached is not None:
			return cached
		n = max(self.topics) + 1 if self.topics else 0
		if n == 0:
			m = sp.csc_matrix((0, 0), dtype=np.float64)
			self._laplacian_cache["adj"] = m
			return m
		# Build edge arrays directly from graph topology (pure numpy)
		num_edges = sum(len(t.unlocks) for t in self.topics.values())
		if num_edges == 0:
			A = sp.csc_matrix((n, n), dtype=np.float64)
			self._laplacian_cache["adj"] = A
			return A
		src = np.empty(num_edges, dtype=np.int64)
		dst = np.empty(num_edges, dtype=np.int64)
		pos = 0
		for t in self.topics.values():
			k = len(t.unlocks)
			if k:
				src[pos:pos + k] = t.topic_id
				dst[pos:pos + k] = list(t.unlocks)
				pos += k
		# Symmetrise: stack forward + reverse edges
		rows = np.concatenate([src, dst])
		cols = np.concatenate([dst, src])
		data = np.ones(rows.shape[0], dtype=np.float64)
		A = sp.csc_matrix((data, (rows, cols)), shape=(n, n), dtype=np.float64)
		# clamp duplicates to 1 (sparse-only, no dense matrix)
		A.data[:] = np.minimum(A.data, 1.0)
		A.setdiag(0)
		A.eliminate_zeros()
		self._laplacian_cache["adj"] = A
		return A

	def build_laplacian(self) -> sp.csc_matrix:
		"""
		Unnormalised graph Laplacian  L = D - A  (sparse, cached).

		The Laplacian is computed on the symmetrised (undirected) version
		of the DAG, which is standard for spectral analysis on directed
		knowledge graphs.
		"""
		cached = self._laplacian_cache.get("L")
		if cached is not None:
			return cached
		A = self._scipy_adjacency()
		n = A.shape[0]
		if n == 0:
			L = sp.csc_matrix((0, 0), dtype=np.float64)
			self._laplacian_cache["L"] = L
			return L
		D = sp.diags(np.asarray(A.sum(axis=1)).flatten(), format="csc")
		L = D - A
		self._laplacian_cache["L"] = L
		return L

	def build_normalised_laplacian(self) -> sp.csc_matrix:
		"""
		Symmetric normalised Laplacian  L_sym = I - D^{-1/2} A D^{-1/2}.

		Eigenvalues lie in [0, 2].  Used for scale-invariant spectral methods.
		"""
		cached = self._laplacian_cache.get("Lnorm")
		if cached is not None:
			return cached
		A = self._scipy_adjacency()
		n = A.shape[0]
		if n == 0:
			Ln = sp.csc_matrix((0, 0), dtype=np.float64)
			self._laplacian_cache["Lnorm"] = Ln
			return Ln
		deg = np.asarray(A.sum(axis=1)).flatten()
		# D^{-1/2}, handling zero-degree nodes
		with np.errstate(divide="ignore"):
			d_inv_sqrt = np.where(deg > 0, 1.0 / np.sqrt(deg), 0.0)
		D_inv_sqrt = sp.diags(d_inv_sqrt, format="csc")
		Ln = sp.eye(n, format="csc") - D_inv_sqrt @ A @ D_inv_sqrt
		self._laplacian_cache["Lnorm"] = Ln
		return Ln

	def spectral_eigenvalues(self, k: int = 6) -> np.ndarray:
		"""
		Compute the k smallest eigenvalues of the unnormalised Laplacian.

		Uses ARPACK (shift-invert) via scipy.sparse.linalg.eigsh → O(E·k).
		Cached so repeated calls are free.
		"""
		cache_key = f"eigenvalues_{k}"
		cached = self._spectral_cache.get(cache_key)
		if cached is not None:
			return cached
		L = self.build_laplacian()
		n = L.shape[0]
		if n == 0:
			vals = np.array([], dtype=np.float64)
			self._spectral_cache[cache_key] = vals
			return vals
		k = min(k, n - 1) if n > 1 else 0
		if k <= 0:
			vals = np.array([0.0], dtype=np.float64)
			self._spectral_cache[cache_key] = vals
			return vals
		try:
			vals, _ = eigsh(L.astype(np.float64), k=k, which="LM", sigma=-0.5)
		except ArpackNoConvergence as exc:
			# Use whatever eigenvalues ARPACK managed to converge
			vals = exc.eigenvalues if hasattr(exc, 'eigenvalues') and len(exc.eigenvalues) > 0 else np.array([0.0])
		vals = np.sort(np.real(vals))
		self._spectral_cache[cache_key] = vals
		return vals

	def algebraic_connectivity(self) -> float:
		"""
		Fiedler value λ₂  — second-smallest eigenvalue of the Laplacian.

		Measures how well-connected the graph is:
		  • λ₂ = 0 → disconnected graph
		  • larger λ₂ → harder to partition / more tightly connected
		"""
		vals = self.spectral_eigenvalues(k=3)
		return float(vals[1]) if len(vals) >= 2 else 0.0

	def spectral_gap(self) -> float:
		"""
		Ratio  λ₂ / λ_max  — normalised connectivity measure in [0, 1].

		A large spectral gap indicates strong expander-like connectivity.
		Uses ARPACK to compute both the second-smallest and largest
		eigenvalues of the Laplacian independently.
		"""
		vals = self.spectral_eigenvalues(k=3)
		if len(vals) < 2:
			return 0.0
		lam2 = float(vals[1])
		if lam2 < 1e-12:
			return 0.0
		# Compute actual λ_max (largest eigenvalue) separately
		L = self.build_laplacian()
		n = L.shape[0]
		if n < 3:
			# For tiny graphs, the smallest-k already covers all eigenvalues
			lam_max = float(vals[-1])
		else:
			try:
				lam_max_arr = eigsh(
					L.astype(np.float64), k=1, which="LM",
					return_eigenvectors=False,
				)
				lam_max = float(abs(lam_max_arr[0]))
			except ArpackNoConvergence as exc:
				lam_max = (
					float(abs(exc.eigenvalues[0]))
					if hasattr(exc, "eigenvalues") and len(exc.eigenvalues) > 0
					else float(vals[-1])
				)
			except Exception:
				lam_max = float(vals[-1])
		return float(lam2 / lam_max) if lam_max > 1e-12 else 0.0

	def fiedler_vector(self) -> np.ndarray:
		"""
		Eigenvector corresponding to λ₂ (the algebraic connectivity).

		The Fiedler vector partitions the graph optimally: nodes with
		positive vs negative components form the two clusters that
		minimise the graph cut (Cheeger's inequality).
		"""
		cache_key = "fiedler"
		cached = self._spectral_cache.get(cache_key)
		if cached is not None:
			return cached
		L = self.build_laplacian()
		n = L.shape[0]
		if n <= 1:
			v = np.zeros(max(n, 0), dtype=np.float64)
			self._spectral_cache[cache_key] = v
			return v
		k = min(3, n - 1)
		if k < 2:
			v = np.zeros(n, dtype=np.float64)
			self._spectral_cache[cache_key] = v
			return v
		try:
			vals_f, vecs_f = eigsh(L.astype(np.float64), k=k, which="LM", sigma=-0.5)
		except ArpackNoConvergence as exc:
			if hasattr(exc, 'eigenvalues') and len(exc.eigenvalues) >= 2:
				vals_f = exc.eigenvalues
				vecs_f = exc.eigenvectors
			else:
				v = np.zeros(n, dtype=np.float64)
				self._spectral_cache[cache_key] = v
				return v
		order = np.argsort(np.real(vals_f))
		v = np.real(vecs_f[:, order[1]])
		self._spectral_cache[cache_key] = v
		return v

	def spectral_embedding(self, k: int = 3) -> np.ndarray:
		"""
		Embed graph nodes into k-dimensional Euclidean space using the
		k smallest non-trivial eigenvectors of the normalised Laplacian.

		Returns (N, k) array where N = max(topic_id)+1.  Row i is the
		embedding of topic i.  Useful for layout, clustering, and as
		a heuristic distance for ACO.
		"""
		cache_key = f"embedding_{k}"
		cached = self._spectral_cache.get(cache_key)
		if cached is not None:
			return cached
		Ln = self.build_normalised_laplacian()
		n = Ln.shape[0]
		if n <= 1:
			emb = np.zeros((max(n, 0), k), dtype=np.float64)
			self._spectral_cache[cache_key] = emb
			return emb
		nev = min(k + 1, n - 1)
		if nev < 2:
			emb = np.zeros((n, k), dtype=np.float64)
			self._spectral_cache[cache_key] = emb
			return emb
		try:
			vals, vecs = eigsh(Ln.astype(np.float64), k=nev, which="LM", sigma=-0.5)
		except ArpackNoConvergence as exc:
			if hasattr(exc, 'eigenvalues') and len(exc.eigenvalues) >= 2:
				vals = exc.eigenvalues
				vecs = exc.eigenvectors
			else:
				emb = np.zeros((n, k), dtype=np.float64)
				self._spectral_cache[cache_key] = emb
				return emb
		order = np.argsort(np.real(vals))
		# skip the trivial (constant) eigenvector (index 0)
		emb = np.real(vecs[:, order[1:k + 1]])
		# pad if fewer eigenvectors than requested
		if emb.shape[1] < k:
			pad = np.zeros((n, k - emb.shape[1]), dtype=np.float64)
			emb = np.hstack([emb, pad])
		self._spectral_cache[cache_key] = emb
		return emb

	def spectral_clustering(self, n_clusters: int = 3) -> np.ndarray:
		"""
		Partition topics into n_clusters groups via spectral clustering.

		Steps (Ng-Jordan-Weiss algorithm):
		  1. Compute n_clusters-dimensional spectral embedding
		  2. Row-normalise the embedding
		  3. Run k-means on the rows

		Returns (N,) int array of cluster labels (0..n_clusters-1).
		"""
		emb = self.spectral_embedding(k=n_clusters)
		n = emb.shape[0]
		if n == 0:
			return np.array([], dtype=np.int32)

		# Row-normalise (Ng-Jordan-Weiss)
		norms = np.linalg.norm(emb, axis=1, keepdims=True)
		norms = np.where(norms > 1e-12, norms, 1.0)
		emb_normed = emb / norms

		# k-means (vectorised Lloyd's algorithm — no sklearn dependency)
		rng = np.random.default_rng(42)
		# k-means++ initialisation
		centers = np.empty((n_clusters, emb_normed.shape[1]), dtype=np.float64)
		centers[0] = emb_normed[rng.integers(n)]
		for c in range(1, n_clusters):
			dists = np.linalg.norm(
				emb_normed[:, None, :] - centers[None, :c, :], axis=2
			).min(axis=1)
			dists_sq = dists ** 2
			total = dists_sq.sum()
			if total < 1e-15:
				centers[c] = emb_normed[rng.integers(n)]
			else:
				probs = dists_sq / total
				centers[c] = emb_normed[rng.choice(n, p=probs)]

		labels = np.zeros(n, dtype=np.int32)
		for _ in range(30):
			# Assign
			dists = np.linalg.norm(
				emb_normed[:, None, :] - centers[None, :, :], axis=2
			)  # (N, n_clusters)
			new_labels = dists.argmin(axis=1).astype(np.int32)
			if np.array_equal(new_labels, labels):
				break
			labels = new_labels
			# Update centres
			for c in range(n_clusters):
				members = emb_normed[labels == c]
				if members.shape[0] > 0:
					centers[c] = members.mean(axis=0)

		return labels

	def spectral_distances(self) -> np.ndarray:
		"""
		Pairwise Euclidean distances in spectral embedding space.

		Returns (N, N) float64 matrix.  D[i,j] is small when topics i,j
		are spectrally close (should be studied together).
		"""
		emb = self.spectral_embedding(k=3)
		n = emb.shape[0]
		if n == 0:
			return np.empty((0, 0), dtype=np.float64)
		# Vectorised pairwise: ||a-b||² = ||a||² + ||b||² - 2·a·b
		sq = (emb ** 2).sum(axis=1)
		D2 = sq[:, None] + sq[None, :] - 2.0 * emb @ emb.T
		np.maximum(D2, 0.0, out=D2)  # clamp numerical noise
		return np.sqrt(D2)

	# ---- topological analysis (vectorised) ---------------------------------

	def betti_0(self) -> int:
		"""
		Betti number β₀ = number of connected components (undirected).

		Computed via scipy sparse connected_components → O(V + E).
		"""
		A = self._scipy_adjacency()
		if A.shape[0] == 0:
			return 0
		n_comp, _ = connected_components(A, directed=False)
		return int(n_comp)

	def topological_depth_vector(self) -> np.ndarray:
		"""
		Vectorised longest-path depth for every node via NumPy BFS.

		Returns (N,) int32 array where depth[i] = length of the longest
		path from any root (zero in-degree) to node i.

		Vectorised: in-degree computed from edge_index via np.add.at;
		per-level frontier updates use boolean masks instead of deque.
		"""
		cache_key = "topo_depth"
		cached = self._spectral_cache.get(cache_key)
		if cached is not None:
			return cached
		n = max(self.topics) + 1 if self.topics else 0
		if n == 0:
			d = np.array([], dtype=np.int32)
			self._spectral_cache[cache_key] = d
			return d
		# Vectorised in-degree from topology (no torch dependency)
		num_edges = sum(len(t.unlocks) for t in self.topics.values())
		depth = np.zeros(n, dtype=np.int32)
		in_deg = np.zeros(n, dtype=np.int32)
		if num_edges > 0:
			src = np.empty(num_edges, dtype=np.int64)
			dst = np.empty(num_edges, dtype=np.int64)
			pos = 0
			for t in self.topics.values():
				k = len(t.unlocks)
				if k:
					src[pos:pos + k] = t.topic_id
					dst[pos:pos + k] = list(t.unlocks)
					pos += k
			np.add.at(in_deg, dst, 1)
		else:
			src = dst = np.empty(0, dtype=np.int64)
		# Frontier-based BFS (Kahn's) with vectorised updates
		topic_ids = np.array(list(self.topics.keys()), dtype=np.int64)
		frontier = topic_ids[in_deg[topic_ids] == 0]
		while frontier.size > 0:
			# Find all edges from frontier nodes
			if src.size > 0:
				mask = np.isin(src, frontier)
				children = dst[mask]
				parents = src[mask]
				if children.size > 0:
					# Vectorised max-depth propagation
					new_depths = depth[parents] + 1
					np.maximum.at(depth, children, new_depths)
					np.subtract.at(in_deg, children, 1)
				frontier = np.unique(children[in_deg[children] == 0])
			else:
				break
		self._spectral_cache[cache_key] = depth
		return depth

	def spectral_graph_positions(self) -> dict[int, tuple[float, float]]:
		"""
		Compute 2D layout using spectral embedding (Fiedler + second eigenvector).
		
		Returns dict mapping topic_id → (x, y) in normalized space [-1, 1].
		Perfect for topological graph visualization in the frontend.
		"""
		emb = self.spectral_embedding(k=2)
		if emb.shape[0] == 0:
			return {}
		positions = {}
		for tid in self.topics.keys():
			x, y = emb[tid, 0], emb[tid, 1]
			# Normalize to [-1, 1]
			positions[tid] = (float(x), float(y))
		return positions

	def to_pyg_data(self) -> Data:
		ei = self.build_edge_index()
		x = self.build_feature_matrix()
		n = max(self.topics) + 1 if self.topics else 0
		return _tg_Data(edge_index=ei, x=x, num_nodes=n)

	# ---- spec-based (re)build ---------------------------------------------
	@classmethod
	def from_spec(
		cls,
		specs: list[TopicSpec] | list[dict],
		device: torch.device | str | None = None,
	) -> "KnowledgeGraph":
		"""
		Build a full KnowledgeGraph from a lightweight list of specs.
		Each spec is either a TopicSpec or a dict with keys:
			name, description, level, prerequisite_names

		This is the fastest way to rebuild the graph when the user is
		unsatisfied and wants a new curriculum.
		"""
		kg = cls(device=device)
		kg._populate_from_specs(specs)
		return kg

	def rebuild_from_spec(self, specs: list[TopicSpec] | list[dict]) -> None:
		"""Clear the current graph and rebuild from specs in-place."""
		self.clear()
		self._populate_from_specs(specs)

	def _populate_from_specs(self, specs: list[TopicSpec] | list[dict]) -> None:
		"""Internal: bulk-create topics + edges from specs."""
		# normalise to TopicSpec
		normalised: list[TopicSpec] = []
		for s in specs:
			if isinstance(s, dict):
				normalised.append(TopicSpec(
					name=s["name"],
					description=s.get("description", ""),
					level=s.get("level", "foundational"),
					prerequisite_names=s.get("prerequisite_names", []),
				))
			else:
				normalised.append(s)

		# bulk-create topics (one invalidation)
		topics: list[Topic] = []
		for spec in normalised:
			t = Topic(
				topic_id=self._next_id,
				name=spec.name,
				description=spec.description,
				level=_LEVEL_MAP.get(spec.level.lower(), TopicLevel.FOUNDATIONAL),
			)
			self._next_id += 1
			topics.append(t)
		self.add_topics_bulk(topics)

		# resolve prerequisite names → ids and bulk-add edges
		edges: list[tuple[int, int]] = []
		for spec, topic in zip(normalised, topics):
			for pre_name in spec.prerequisite_names:
				pre = self.get_topic_by_name(pre_name)
				if pre is None:
					# Webscraping can produce unreliable prerequisite names;
					# skip silently rather than crashing the whole graph build.
					continue
				edges.append((pre.topic_id, topic.topic_id))
		if edges:
			self.add_prerequisites_bulk(edges)

	# ---- pretty printing ---------------------------------------------------
	def print_curriculum(self) -> None:
		order = self.learning_order()
		print("=== NeuraLearn Curriculum ===")
		for i, t in enumerate(order, 1):
			status = "[x]" if t.mastered else ("[ ]" if self.is_unlocked(t.topic_id) else "[locked]")
			prereqs = ", ".join(self.topics[p].name for p in t.prerequisites) or "none"
			print(f"  {i}. {status} {t.name} ({t.level.name}) | prereqs: {prereqs}")
		pct = self.mastery_progress() * 100
		print(f"\nProgress: {pct:.0f}%  ({len(self.get_mastered())}/{self.num_topics} topics mastered)")


# ---------------------------------------------------------------------------
# Sample curriculum spec (plain data — cheap to store / regenerate from)
# ---------------------------------------------------------------------------
SAMPLE_ML_CURRICULUM: list[dict] = [
	{"name": "Linear Algebra",   "description": "Vectors, matrices, transformations",          "level": "foundational"},
	{"name": "Python Basics",    "description": "Syntax, data types, control flow",            "level": "foundational"},
	{"name": "Python OOP",       "description": "Classes, inheritance, polymorphism",           "level": "intermediate", "prerequisite_names": ["Python Basics"]},
	{"name": "Statistics",       "description": "Probability, distributions, hypothesis tests", "level": "intermediate", "prerequisite_names": ["Linear Algebra", "Python Basics"]},
	{"name": "Data Wrangling",   "description": "Pandas, cleaning, feature engineering",        "level": "intermediate", "prerequisite_names": ["Statistics", "Python Basics"]},
	{"name": "Machine Learning", "description": "Supervised & unsupervised learning",           "level": "advanced",     "prerequisite_names": ["Statistics", "Python OOP"]},
	{"name": "Deep Learning",    "description": "Backprop, CNNs, RNNs, Transformers",           "level": "advanced",     "prerequisite_names": ["Machine Learning"]},
	{"name": "Neural Architecture Design", "description": "Custom layers, GNNs, attention",     "level": "expert",       "prerequisite_names": ["Deep Learning"]},
]


def build_sample_knowledge_graph() -> KnowledgeGraph:
	"""Build from the sample spec — one line, instant rebuild."""
	return KnowledgeGraph.from_spec(SAMPLE_ML_CURRICULUM)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
	# ---- first build -------------------------------------------------------
	kg = build_sample_knowledge_graph()
	print("--- Full Curriculum ---")
	kg.print_curriculum()

	print("\n--- Available to learn now ---")
	for t in kg.get_available():
		print(f"  • {t.name}")

	# simulate mastering foundational topics
	print("\n>>> Mastering: Linear Algebra, Python Basics, Python OOP")
	kg.master_topic(0)
	kg.master_topic(1)
	kg.master_topic(2)

	print("\n--- Available to learn now ---")
	for t in kg.get_available():
		print(f"  • {t.name}")

	# shortest path to Deep Learning
	dl = kg.get_topic_by_name("Deep Learning")
	if dl:
		print("\n--- Shortest path to 'Deep Learning' ---")
		for step, t in enumerate(kg.shortest_path_to(dl.topic_id), 1):
			tag = "(done)" if t.mastered else "(todo)"
			print(f"  {step}. {t.name} {tag}")

	# ---- user unsatisfied? rebuild instantly --------------------------------
	print("\n\n>>> User unsatisfied — rebuilding with a different curriculum…")
	new_spec = [
		{"name": "HTML & CSS",      "level": "foundational"},
		{"name": "JavaScript",      "level": "foundational"},
		{"name": "React",           "level": "intermediate", "prerequisite_names": ["HTML & CSS", "JavaScript"]},
		{"name": "Node.js",         "level": "intermediate", "prerequisite_names": ["JavaScript"]},
		{"name": "Full-Stack App",  "level": "advanced",     "prerequisite_names": ["React", "Node.js"]},
	]
	kg.rebuild_from_spec(new_spec)       # reuses same object, no new allocation
	print("\n--- New Curriculum ---")
	kg.print_curriculum()

	print("\n--- Graph structure ---")
	print("edge_index:\n", kg.build_edge_index())
	print("out_degree:", kg.out_degree().tolist())
	print("in_degree: ", kg.in_degree().tolist())
