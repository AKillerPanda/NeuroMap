import csv
import os
import bs4 as bs
import requests
import re
import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from urllib.parse import quote_plus, quote, unquote, urlparse, parse_qs


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

_REQUEST_TIMEOUT = float(os.getenv("SCRAPE_REQUEST_TIMEOUT_S", "5"))
_RETRY_DELAY = float(os.getenv("SCRAPE_RETRY_DELAY_S", "0.4"))
_MAX_RETRIES = int(os.getenv("SCRAPE_MAX_RETRIES", "0"))
_SOURCE_TIMEOUT = float(os.getenv("SCRAPE_SOURCE_TIMEOUT_S", "10"))


def _get(url: str, **kwargs) -> requests.Response | None:
	"""GET with bounded timeout and optional retry for transient failures."""
	for attempt in range(_MAX_RETRIES + 1):
		try:
			resp = _SESSION.get(url, timeout=_REQUEST_TIMEOUT, **kwargs)
			if resp.status_code == 429:
				time.sleep(_RETRY_DELAY * (attempt + 1))
				continue
			resp.raise_for_status()
			return resp
		except requests.exceptions.RequestException as e:
			if attempt < _MAX_RETRIES:
				time.sleep(_RETRY_DELAY * (attempt + 1))
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


def _extract_duckduckgo_redirect_url(href: str) -> str:
	"""Extract target URL from DuckDuckGo redirect links."""
	if not href:
		return ""
	if href.startswith("/l/?"):
		href = f"https://duckduckgo.com{href}"
	if href.startswith("//duckduckgo.com/l/?") or href.startswith("https://duckduckgo.com/l/?"):
		try:
			parsed = urlparse(href if href.startswith("http") else f"https:{href}")
			q = parse_qs(parsed.query)
			uddg = q.get("uddg", [""])[0]
			return unquote(uddg) if uddg else ""
		except Exception:
			return ""
	return href


def _search_duckduckgo_html(query: str, max_results: int = 15) -> list[dict]:
	"""Scrape DuckDuckGo HTML results for links and titles."""
	url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
	soup = get_soup(url)
	if soup is None:
		return []

	results: list[dict] = []
	for a in soup.select("a.result__a"):
		title = a.get_text(" ", strip=True)
		href = a.get("href", "")
		link = _extract_duckduckgo_redirect_url(href)
		if not title or not link.startswith("http"):
			continue
		results.append({"title": title[:180], "url": link})
		if len(results) >= max_results:
			break

	return results


def _playlist_quality_score(title: str, url: str) -> int:
	"""Heuristic ranking for playlist quality using trusted-source/title signals."""
	t = title.lower()
	u = url.lower()
	score = 0

	# Strongly prefer actual YouTube playlists
	if "youtube.com/playlist" in u:
		score += 40
	elif "youtube.com/watch" in u and "list=" in u:
		score += 30

	# Trusted content/channel signals
	trusted = [
		"mit", "stanford", "harvard", "oxford", "caltech", "coursera",
		"edx", "freecodecamp", "deeplearning.ai", "khan academy",
		"nptel", "university", "official", "open course",
	]
	for kw in trusted:
		if kw in t or kw in u:
			score += 6

	# Learning-utility signals
	for kw in ["playlist", "course", "full course", "series", "complete", "tutorial", "beginner"]:
		if kw in t:
			score += 3

	# Penalize clearly irrelevant/noisy results
	for bad in ["reaction", "meme", "shorts", "clips", "trailer"]:
		if bad in t:
			score -= 8

	return score


def _fetch_youtube_playlist_links(topic: str, max_results: int = 8) -> list[dict]:
	"""Extract direct YouTube playlist links by parsing playlist IDs from search results."""
	search_url = (
		"https://www.youtube.com/results?search_query="
		f"{quote_plus(topic + ' full course playlist')}"
	)
	resp = _get(search_url)
	if resp is None:
		return []

	playlist_ids = re.findall(r'"playlistId":"(PL[^"]+)"', resp.text)
	if not playlist_ids:
		return []

	# Preserve order and remove duplicates
	seen: set[str] = set()
	unique_ids: list[str] = []
	for pid in playlist_ids:
		if pid not in seen:
			seen.add(pid)
			unique_ids.append(pid)
		if len(unique_ids) >= max_results:
			break

	return [
		{
			"title": f"{topic} - YouTube Playlist {idx + 1}",
			"url": f"https://www.youtube.com/playlist?list={pid}",
		}
		for idx, pid in enumerate(unique_ids)
	]


def _fetch_playlist_resources(topic: str) -> list[dict]:
	"""
	Find high-quality playlist resources for a topic.
	Prioritises YouTube playlist URLs and ranked course-series results.
	"""
	queries = [
		f"{topic} best playlist youtube",
		f"{topic} full course playlist",
		f"{topic} university course playlist",
	]

	pool: list[dict] = []
	for q in queries:
		pool.extend(_search_duckduckgo_html(q, max_results=12))

	# Keep only likely playlist links
	playlist_candidates: list[dict] = []
	for item in pool:
		url = item.get("url", "")
		title = item.get("title", "")
		u = url.lower()
		t = title.lower()
		is_playlist = (
			"youtube.com/playlist" in u
			or ("youtube.com/watch" in u and "list=" in u)
			or ("playlist" in t and "youtube" in u)
		)
		if is_playlist and url:
			playlist_candidates.append({"title": title, "url": url})

	# De-duplicate by URL then rank by quality
	by_url: dict[str, dict] = {}
	for item in playlist_candidates:
		by_url[item["url"]] = item

	# Fallback: pull direct playlist IDs from YouTube search if sparse
	if len(by_url) < 3:
		for item in _fetch_youtube_playlist_links(topic, max_results=8):
			by_url[item["url"]] = item

	ranked = sorted(
		by_url.values(),
		key=lambda x: _playlist_quality_score(x.get("title", ""), x.get("url", "")),
		reverse=True,
	)

	return ranked[:8]


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
		futures = {
			pool.submit(_fetch_wikipedia_api, topic): "wiki",
			pool.submit(_scrape_geeksforgeeks, topic): "gfg",
			pool.submit(_scrape_github_awesome, topic): "gh",
			pool.submit(_fetch_duckduckgo, topic): "ddg",
			pool.submit(_fetch_playlist_resources, topic): "play",
		}

		# Collect what finishes within a global budget so one slow source does not
		# hold the whole response hostage.
		try:
			for fut in as_completed(futures, timeout=_SOURCE_TIMEOUT):
				src = futures[fut]
				try:
					result = fut.result()
				except Exception:
					continue

				if src == "wiki":
					wiki_summary, wiki_sections = result
				elif src == "gfg":
					gfg_items = result
				elif src == "gh":
					gh_items = result
				elif src == "ddg":
					ddg_items = result
				elif src == "play":
					playlist_items = result
		except Exception:
			# TimeoutError from as_completed is expected when a source exceeds budget.
			pass

		for fut in futures:
			if not fut.done():
				fut.cancel()

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
		[LearningResource(title=g["title"], url=g.get("url", ""), source="youtube", resource_type="playlist") for g in playlist_items]
		+ [LearningResource(title=g["title"], url=g.get("url", ""), source="geeksforgeeks", resource_type="tutorial") for g in gfg_items]
		+ [LearningResource(title=g["title"], url=g.get("url", ""), source="github", resource_type="curated list") for g in gh_items]
		+ [LearningResource(title=g["title"], url=g.get("url", ""), source="duckduckgo", resource_type="article") for g in ddg_items]
	)

	# De-duplicate resources by URL/title while preserving order
	seen_res: set[str] = set()
	deduped_resources: list[LearningResource] = []
	for res in all_resources:
		key = (res.url or res.title).strip().lower()
		if not key or key in seen_res:
			continue
		seen_res.add(key)
		deduped_resources.append(res)
	all_resources = deduped_resources

	# Build LearningStep objects with levels
	for i, name in enumerate(step_names):
		step = LearningStep(step_number=i + 1, subtopic=name, level=levels[i])
		plan.steps.append(step)

	# Distribute resources to the most relevant step by word overlap with the
	# step's subtopic name, falling back to round-robin for unmatched resources.
	if all_resources:
		unmatched = []
		for res in all_resources:
			res_words = set(res.title.lower().split())
			best_idx, best_score = 0, -1
			for idx, step in enumerate(plan.steps):
				step_words = set(step.subtopic.lower().split())
				score = len(res_words & step_words)
				if score > best_score:
					best_score, best_idx = score, idx
			if best_score > 0:
				plan.steps[best_idx].resources.append(res)
			else:
				unmatched.append(res)
		for idx, res in enumerate(unmatched):
			plan.steps[idx % len(plan.steps)].resources.append(res)

	# Ensure each step gets access to top playlist links for learning continuity
	top_playlists = [
		res for res in all_resources
		if res.resource_type == "playlist"
	][:2]
	if top_playlists:
		for step in plan.steps:
			if any(r.resource_type == "playlist" for r in step.resources):
				continue
			existing_urls = {r.url for r in step.resources if r.url}
			for p in top_playlists[:1]:
				if p.url and p.url not in existing_urls:
					step.resources.append(p)

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