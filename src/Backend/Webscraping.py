import bs4 as bs
import requests
import re
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from urllib.parse import quote_plus, quote


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_SESSION = requests.Session()
_SESSION.headers.update({
	"User-Agent": (
		"NeuraLearn/1.0 (Educational learning-path builder; "
		"https://github.com/AKillerPanda/NeuraLearn) "
		"Python-requests"
	),
	"Accept-Language": "en-US,en;q=0.9",
})

_TIMEOUT = 15  # seconds
_RETRY_DELAY = 1.0  # seconds between retries


def _get(url: str, **kwargs) -> requests.Response | None:
	"""GET with one retry on transient failure."""
	for attempt in range(2):
		try:
			resp = _SESSION.get(url, timeout=_TIMEOUT, **kwargs)
			if resp.status_code == 429:
				time.sleep(_RETRY_DELAY * (attempt + 1))
				continue
			resp.raise_for_status()
			return resp
		except requests.exceptions.RequestException as e:
			if attempt == 0:
				time.sleep(_RETRY_DELAY)
			else:
				print(f"[scrape] error fetching {url}: {e}")
	return None


def get_soup(url: str) -> bs.BeautifulSoup | None:
	"""Fetch a URL and return a BeautifulSoup object, or None on failure."""
	resp = _get(url)
	if resp is None:
		return None
	return bs.BeautifulSoup(resp.text, "html.parser")


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class LearningResource:
	"""A single learning resource (article, video, course, etc.)."""
	title: str
	url: str = ""
	source: str = ""          # e.g. "wikipedia", "github", "geeksforgeeks"
	resource_type: str = ""   # e.g. "article", "video", "course", "tutorial"

	def __repr__(self) -> str:
		return f"{self.title}  ({self.source})"


@dataclass(slots=True)
class LearningStep:
	"""One step in a learning plan — a subtopic + its resources."""
	step_number: int
	subtopic: str
	description: str = ""
	level: str = "foundational"
	resources: list[LearningResource] = field(default_factory=list)

	def __repr__(self) -> str:
		return f"Step {self.step_number}: {self.subtopic} ({len(self.resources)} resources)"


@dataclass(slots=True)
class LearningPlan:
	"""Full learning plan for a skill / topic."""
	topic: str
	summary: str = ""
	steps: list[LearningStep] = field(default_factory=list)

	def print_plan(self) -> None:
		print(f"\n{'='*60}")
		print(f"  Learning Plan: {self.topic}")
		print(f"{'='*60}")
		if self.summary:
			print(f"\n  {self.summary}\n")
		for step in self.steps:
			print(f"\n  Step {step.step_number}: {step.subtopic}  [{step.level}]")
			if step.description:
				print(f"    {step.description}")
			for r in step.resources:
				tag = f"[{r.resource_type}]" if r.resource_type else ""
				print(f"      • {r.title} {tag}")
				if r.url:
					print(f"        {r.url}")
		print(f"\n{'='*60}")

	def to_dict_list(self) -> list[dict]:
		"""
		Export as a proper DAG spec (not a linear chain).

		Prerequisite logic by difficulty level:
		  - foundational  : no prerequisites (parallel entry points)
		  - intermediate  : depends on 1-2 foundational topics
		  - advanced       : depends on 1-2 intermediate topics
		  - expert         : depends on 1-2 advanced topics

		Within the same level, consecutive topics share one prerequisite
		so there's some horizontal connectivity too.  The result is a
		realistic graph with varying in-degree / out-degree.
		"""
		if not self.steps:
			return []

		# Group steps by level
		level_order = ["foundational", "intermediate", "advanced", "expert"]
		by_level: dict[str, list[LearningStep]] = {lv: [] for lv in level_order}
		for step in self.steps:
			lv = step.level if step.level in by_level else "foundational"
			by_level[lv].append(step)

		result: list[dict] = []

		# Track which names exist at each level for prerequisite assignment
		level_names: dict[str, list[str]] = {lv: [] for lv in level_order}

		for lv_idx, level in enumerate(level_order):
			steps_at_level = by_level[level]
			if not steps_at_level:
				continue

			# Find the previous level that actually has topics
			prev_level_names: list[str] = []
			for prev_idx in range(lv_idx - 1, -1, -1):
				prev_level_names = level_names[level_order[prev_idx]]
				if prev_level_names:
					break

			for i, step in enumerate(steps_at_level):
				entry: dict = {
					"name": step.subtopic,
					"description": step.description,
					"level": level,
					"resources": [
						{
							"title": r.title,
							"url": r.url,
							"source": r.source,
							"type": r.resource_type,
						}
						for r in step.resources
					],
				}

				prereqs: list[str] = []

				if prev_level_names:
					# Connect to 1-2 topics from the previous level
					# Spread connections evenly across the previous level
					n_prev = len(prev_level_names)
					# Primary prerequisite: map index into previous level
					primary_idx = (i * n_prev) // max(len(steps_at_level), 1)
					primary_idx = min(primary_idx, n_prev - 1)
					prereqs.append(prev_level_names[primary_idx])

					# Secondary prerequisite for fan-in (every other topic)
					if n_prev >= 2 and i % 2 == 1:
						secondary_idx = (primary_idx + 1) % n_prev
						if prev_level_names[secondary_idx] not in prereqs:
							prereqs.append(prev_level_names[secondary_idx])

				# Horizontal link: 2nd+ topic at same level shares a prereq
				# with the previous same-level topic (creates within-level edges)
				if i > 0 and level != "foundational" and not prev_level_names:
					prereqs.append(steps_at_level[i - 1].subtopic)

				if prereqs:
					entry["prerequisite_names"] = prereqs

				result.append(entry)
				level_names[level].append(step.subtopic)

		return result


# ---------------------------------------------------------------------------
# Assign difficulty levels based on position in the step list
# ---------------------------------------------------------------------------
def _assign_levels(n: int) -> list[str]:
	"""Return a list of n level strings spread across the difficulty curve."""
	if n <= 0:
		return []
	levels = []
	for i in range(n):
		ratio = i / max(n - 1, 1)
		if ratio < 0.25:
			levels.append("foundational")
		elif ratio < 0.55:
			levels.append("intermediate")
		elif ratio < 0.80:
			levels.append("advanced")
		else:
			levels.append("expert")
	return levels


# ---------------------------------------------------------------------------
# 1. Wikipedia MediaWiki API — grab summary + section names (no scraping)
# ---------------------------------------------------------------------------
def _fetch_wikipedia_api(topic: str) -> tuple[str, list[str]]:
	"""
	Use the MediaWiki Action API (designed for bots) to get:
	  - extract  : plain-text summary of the article
	  - sections : list of section headings (table of contents)
	Returns (summary, [section_heading, ...]).
	"""
	# --- summary via TextExtracts ----------------------------------------
	summary = ""
	params_extract = {
		"action": "query",
		"titles": topic,
		"prop": "extracts",
		"exintro": True,
		"explaintext": True,
		"redirects": 1,
		"format": "json",
	}
	resp = _get("https://en.wikipedia.org/w/api.php", params=params_extract)
	if resp is not None:
		data = resp.json()
		pages = data.get("query", {}).get("pages", {})
		for page in pages.values():
			text = page.get("extract", "")
			if text:
				summary = text[:350].rsplit(" ", 1)[0] + "…" if len(text) > 350 else text
				break

	# --- section headings via parse API -----------------------------------
	headings: list[str] = []
	params_sections = {
		"action": "parse",
		"page": topic,
		"prop": "sections",
		"redirects": 1,
		"format": "json",
	}
	resp = _get("https://en.wikipedia.org/w/api.php", params=params_sections)
	if resp is not None:
		data = resp.json()
		skip = {"see also", "references", "external links", "notes",
				"further reading", "bibliography", "contents", "gallery"}
		for sec in data.get("parse", {}).get("sections", []):
			heading = sec.get("line", "").strip()
			# only top-level (toclevel 1–2) and skip meta sections
			if heading and heading.lower() not in skip and sec.get("toclevel", 99) <= 2:
				headings.append(heading)

	return summary, headings


# ---------------------------------------------------------------------------
# 2. GeeksforGeeks — direct scrape of tutorial page (no Google needed)
# ---------------------------------------------------------------------------
def _scrape_geeksforgeeks(topic: str) -> list[dict]:
	"""
	Go directly to GfG's search/tutorial page for the topic
	and pull list items. Returns list of {title, url}.
	"""
	slug = topic.lower().replace(" ", "-")
	urls_to_try = [
		f"https://www.geeksforgeeks.org/{slug}-tutorial/",
		f"https://www.geeksforgeeks.org/{slug}/",
	]
	for url in urls_to_try:
		page = get_soup(url)
		if page is None:
			continue
		results: list[dict] = []
		for li in page.select("article li, .article-body li, .text li, .entry-content li"):
			a_tag = li.find("a")
			text = li.get_text(strip=True)[:120]
			if len(text) < 5:
				continue
			link = a_tag["href"] if a_tag and a_tag.get("href", "").startswith("http") else ""
			results.append({"title": text, "url": link})
			if len(results) >= 20:
				break
		if results:
			return results

	return []


# ---------------------------------------------------------------------------
# 3. GitHub — look for awesome-<topic> or roadmap repos
# ---------------------------------------------------------------------------
def _scrape_github_awesome(topic: str) -> list[dict]:
	"""
	Search GitHub for an 'awesome-<topic>' repo and pull resource links
	from its README. Returns list of {title, url}.
	"""
	candidates: list[str] = []

	# try the GitHub search API (unauthenticated)
	search_url = (
		f"https://api.github.com/search/repositories"
		f"?q=awesome+{quote_plus(topic)}+in:name&sort=stars&per_page=3"
	)
	resp = _get(search_url)
	if resp is not None and resp.ok:
		try:
			data = resp.json()
			for item in data.get("items", [])[:2]:
				html_url = item.get("html_url", "")
				if html_url:
					candidates.append(html_url)
		except (json.JSONDecodeError, KeyError):
			pass

	# fallback: try the topics page
	slug = topic.lower().replace(" ", "-")
	candidates.append(f"https://github.com/topics/{slug}")

	results: list[dict] = []
	for repo_url in candidates[:3]:
		soup = get_soup(repo_url)
		if soup is None:
			continue
		for li in soup.select("article li, .markdown-body li"):
			a_tag = li.find("a")
			if a_tag and a_tag.get("href", "").startswith("http"):
				title = a_tag.get_text(strip=True)[:120]
				if len(title) < 3:
					continue
				results.append({"title": title, "url": a_tag["href"]})
				if len(results) >= 15:
					return results

	return results


# ---------------------------------------------------------------------------
# 4. DuckDuckGo instant-answer API (no rate-limiting like Google)
# ---------------------------------------------------------------------------
def _fetch_duckduckgo(topic: str) -> list[dict]:
	"""
	Use the DuckDuckGo Instant Answer API for related topics.
	Returns [{title, url, snippet}].
	"""
	params = {"q": f"learn {topic} step by step", "format": "json", "no_html": 1}
	resp = _get("https://api.duckduckgo.com/", params=params)
	if resp is None:
		return []

	results: list[dict] = []
	try:
		data = resp.json()
	except (json.JSONDecodeError, ValueError):
		return []

	# related topics
	for item in data.get("RelatedTopics", []):
		if isinstance(item, dict):
			text = item.get("Text", "")
			url = item.get("FirstURL", "")
			if text and url:
				results.append({"title": text[:120], "url": url, "snippet": ""})
			# nested subtopics
			for sub in item.get("Topics", []):
				text = sub.get("Text", "")
				url = sub.get("FirstURL", "")
				if text and url:
					results.append({"title": text[:120], "url": url, "snippet": ""})
		if len(results) >= 10:
			break

	return results


# ---------------------------------------------------------------------------
# Master function: build a LearningPlan for any topic
# ---------------------------------------------------------------------------
def get_learning_plan(topic: str) -> LearningPlan:
	"""
	Scrape multiple sources and assemble a structured LearningPlan
	with ordered steps the user should follow to learn `topic`.

	Sources are fetched *concurrently* via ThreadPoolExecutor for 2-4x speedup:
	  1. Wikipedia MediaWiki API -> topic summary + section headings as subtopics
	  2. GeeksforGeeks -> direct tutorial page scrape
	  3. GitHub awesome lists -> curated resources
	  4. DuckDuckGo Instant Answer API -> related topics & links
	"""
	plan = LearningPlan(topic=topic)

	# --- Fetch all sources concurrently ------------------------------------
	gfg_items: list[dict] = []
	gh_items: list[dict] = []
	ddg_items: list[dict] = []

	with ThreadPoolExecutor(max_workers=4) as pool:
		future_wiki = pool.submit(_fetch_wikipedia_api, topic)
		future_gfg  = pool.submit(_scrape_geeksforgeeks, topic)
		future_gh   = pool.submit(_scrape_github_awesome, topic)
		future_ddg  = pool.submit(_fetch_duckduckgo, topic)

		# Collect results (with exception handling per source)
		try:
			wiki_summary, wiki_sections = future_wiki.result(timeout=30)
		except Exception:
			wiki_summary, wiki_sections = "", []

		try:
			gfg_items = future_gfg.result(timeout=30)
		except Exception:
			gfg_items = []

		try:
			gh_items = future_gh.result(timeout=30)
		except Exception:
			gh_items = []

		try:
			ddg_items = future_ddg.result(timeout=30)
		except Exception:
			ddg_items = []

	if wiki_summary:
		plan.summary = wiki_summary

	# --- Assemble steps -----------------------------------------------------
	step_names: list[str] = []

	if wiki_sections:
		step_names = wiki_sections[:15]
	elif gfg_items:
		step_names = [item["title"] for item in gfg_items[:12]]
	else:
		# comprehensive fallback learning phases
		step_names = [
			f"Introduction to {topic}",
			f"History & context of {topic}",
			f"Core concepts of {topic}",
			f"Essential tools & materials for {topic}",
			f"{topic} fundamentals — hands-on practice",
			f"Basic {topic} techniques",
			f"Intermediate {topic}",
			f"Common mistakes & how to fix them in {topic}",
			f"Advanced {topic} techniques",
			f"Developing your own {topic} style",
			f"Projects & real-world {topic} applications",
			f"Mastery — teaching & sharing {topic}",
		]

	# Assign difficulty levels
	levels = _assign_levels(len(step_names))

	# Collect all resources
	all_resources = (
		[LearningResource(title=g["title"], url=g.get("url", ""), source="geeksforgeeks", resource_type="tutorial") for g in gfg_items]
		+ [LearningResource(title=g["title"], url=g.get("url", ""), source="github", resource_type="curated list") for g in gh_items]
		+ [LearningResource(title=g["title"], url=g.get("url", ""), source="duckduckgo", resource_type="article") for g in ddg_items]
	)

	# Build LearningStep objects with levels
	for i, name in enumerate(step_names):
		step = LearningStep(step_number=i + 1, subtopic=name, level=levels[i])
		plan.steps.append(step)

	# Distribute resources round-robin across steps
	if all_resources:
		for idx, res in enumerate(all_resources):
			step_idx = idx % len(plan.steps)
			plan.steps[step_idx].resources.append(res)

	return plan


# ---------------------------------------------------------------------------
# Quick helper: topic → list of subtopic names (for KnowledgeGraph integration)
# ---------------------------------------------------------------------------
def get_subtopic_names(topic: str) -> list[str]:
	"""Return just the subtopic / step names for a topic (lightweight)."""
	plan = get_learning_plan(topic)
	return [step.subtopic for step in plan.steps]


def get_learning_spec(topic: str) -> list[dict]:
	"""
	Return a list-of-dicts spec that can be fed directly into
	KnowledgeGraph.from_spec() or kg.rebuild_from_spec().

	Each dict has: name, description, level, prerequisite_names, resources.
	"""
	plan = get_learning_plan(topic)
	return plan.to_dict_list()


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
	import sys

	topic = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Machine Learning"
	print(f"Fetching learning plan for: {topic}\n")

	plan = get_learning_plan(topic)
	plan.print_plan()

	print("\n--- As KnowledgeGraph spec ---")
	spec = plan.to_dict_list()
	for s in spec[:5]:
		print(f"  {s}")
	if len(spec) > 5:
		print(f"  ... ({len(spec)} total)")