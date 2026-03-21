import { Plus, Trash2, Network, Route, RotateCcw, Sparkles, Zap, Brain, Loader2, Bookmark, Compass } from "lucide-react";
import { Badge } from "../components/ui/badge";
import { NeuroMapLogo } from "../components/NeuroMapLogo";
import { toast } from "sonner";
import { useRef, useState, useEffect, type ChangeEvent } from "react";
import { Link, useNavigate } from "react-router";
import { useTopics } from "../context/TopicsContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Textarea } from "../components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { categories } from "../data/categories";
import { Download, Upload } from "lucide-react";

export function Workspace() {
  const {
    topics,
    addTopic,
    removeTopic,
    generateRelations,
    clearAll,
    loadDemoData,
    exportData,
    importData,
    savedGraphs,
    removeSavedGraph,
  } = useTopics();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("Computer Science");
  const [difficulty, setDifficulty] = useState<"beginner" | "intermediate" | "advanced">("beginner");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [aiSkill, setAiSkill] = useState("");
  const [spellSuggestions, setSpellSuggestions] = useState<string[]>([]);
  const [isCheckingSpelling, setIsCheckingSpelling] = useState(false);
  const [topicSpellSuggestions, setTopicSpellSuggestions] = useState<string[]>([]);
  const [isCheckingTopicSpelling, setIsCheckingTopicSpelling] = useState(false);
  
  // Multi-skill merge state
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [multiSkillInput, setMultiSkillInput] = useState("");
  const [isBuildingMulti, setIsBuildingMulti] = useState(false);
  const [savedFilter, setSavedFilter] = useState<"all" | "single" | "merged">("all");
  
  const navigate = useNavigate();
  const filteredSavedGraphs = savedGraphs.filter((g) =>
    savedFilter === "all" ? true : g.type === savedFilter
  );

  const buildCorrectionOptions = (
    originalText: string,
    results: Array<{ original: string; suggestions: Array<{ word: string; score: number }> }>
  ): string[] => {
    const originalTokens = originalText.trim().split(/\s+/).filter(Boolean);
    if (originalTokens.length === 0 || results.length !== originalTokens.length) return [];

    const same = (a: string, b: string) => a.trim().toLowerCase() === b.trim().toLowerCase();
    const options: string[] = [];

    // Primary full-phrase correction using best suggestion per token.
    const primaryTokens = results.map((r, i) => {
      const best = r.suggestions?.[0]?.word?.trim();
      return best || originalTokens[i];
    });
    const primary = primaryTokens.join(" ");
    if (!same(primary, originalText)) options.push(primary);

    // Additional candidates: vary one token at a time with top SDS suggestions.
    for (let i = 0; i < results.length; i++) {
      const suggestions = (results[i].suggestions || [])
        .map((s) => s.word?.trim())
        .filter((w): w is string => !!w)
        .slice(0, 3);

      for (const suggestion of suggestions) {
        if (same(suggestion, originalTokens[i])) continue;
        const tokens = [...originalTokens];
        tokens[i] = suggestion;
        const candidate = tokens.join(" ");
        if (!same(candidate, originalText)) options.push(candidate);
      }
    }

    return [...new Set(options)].slice(0, 6);
  };

  useEffect(() => {
    const text = aiSkill.trim();
    if (text.length < 2) {
      setSpellSuggestions([]);
      setIsCheckingSpelling(false);
      return;
    }

    const timer = window.setTimeout(async () => {
      setIsCheckingSpelling(true);
      try {
        const res = await fetch("/api/spell-check", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text, top_k: 5 }),
        });
        if (!res.ok) {
          setSpellSuggestions([]);
          return;
        }

        const data = await res.json();
        const results = Array.isArray(data?.results)
          ? data.results as Array<{ original: string; suggestions: Array<{ word: string; score: number }> }>
          : [];

        setSpellSuggestions(buildCorrectionOptions(text, results));
      } catch {
        setSpellSuggestions([]);
      } finally {
        setIsCheckingSpelling(false);
      }
    }, 260);

    return () => window.clearTimeout(timer);
  }, [aiSkill]);

  useEffect(() => {
    const text = name.trim();
    if (text.length < 2) {
      setTopicSpellSuggestions([]);
      setIsCheckingTopicSpelling(false);
      return;
    }

    const timer = window.setTimeout(async () => {
      setIsCheckingTopicSpelling(true);
      try {
        const res = await fetch("/api/spell-check", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text, top_k: 5 }),
        });
        if (!res.ok) {
          setTopicSpellSuggestions([]);
          return;
        }

        const data = await res.json();
        const results = Array.isArray(data?.results)
          ? data.results as Array<{ original: string; suggestions: Array<{ word: string; score: number }> }>
          : [];

        setTopicSpellSuggestions(buildCorrectionOptions(text, results));
      } catch {
        setTopicSpellSuggestions([]);
      } finally {
        setIsCheckingTopicSpelling(false);
      }
    }, 260);

    return () => window.clearTimeout(timer);
  }, [name]);

  const handleAddTopic = () => {
    if (!name.trim()) {
      toast.error("Please enter a topic name");
      return;
    }

    addTopic({
      name: name.trim(),
      description: description.trim(),
      category,
      difficulty,
      status: "not-started",
    });

    // Reset form
    setName("");
    setDescription("");
    toast.success(`Added "${name}" to your knowledge graph`);
  };

  const handleGenerateGraph = () => {
    if (topics.length < 2) {
      toast.error("Add at least 2 topics to generate a graph");
      return;
    }
    generateRelations();
    toast.success("Knowledge graph generated!");
  };

  const handleClearAll = () => {
    if (window.confirm("Are you sure you want to clear all topics?")) {
      clearAll();
      toast.success("All topics cleared");
    }
  };

  const handleLoadDemo = () => {
    if (topics.length > 0) {
      if (!window.confirm("This will replace your current topics. Continue?")) {
        return;
      }
    }
    loadDemoData();
    toast.success("Demo data loaded! Click 'Generate Knowledge Graph' to see connections.");
  };

  const handleExport = () => {
    if (topics.length === 0) {
      toast.error("No topics to export");
      return;
    }
    const data = exportData();
    const blob = new Blob([data], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `neuromap-graph-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Knowledge graph exported!");
  };

  const handleImport = () => {
    fileInputRef.current?.click();
  };

  const handleGenerateAiGraph = () => {
    const skill = aiSkill.trim();
    if (!skill) {
      toast.error("Enter a skill or subject to generate a graph");
      return;
    }
    navigate(`/graph/${encodeURIComponent(skill)}`);
  };

  const handleAddMultiSkill = () => {
    const skill = multiSkillInput.trim();
    if (!skill) return;
    if (selectedSkills.map(s => s.toLowerCase()).includes(skill.toLowerCase())) {
      toast.error("Skill already added");
      return;
    }
    setSelectedSkills([...selectedSkills, skill]);
    setMultiSkillInput("");
  };

  const handleRemoveMultiSkill = (skill: string) => {
    setSelectedSkills(selectedSkills.filter(s => s !== skill));
  };

  const handleBuildMultiSkillGraph = async () => {
    if (selectedSkills.length < 2) {
      toast.error("Select at least 2 skills to build a merged NeuroMap");
      return;
    }
    setIsBuildingMulti(true);
    try {
      const skillsEncoded = selectedSkills.map(s => encodeURIComponent(s)).join(",");
      navigate(`/graph-multi/${skillsEncoded}`);
    } catch (error) {
      toast.error("Failed to navigate to merged graph");
    } finally {
      setIsBuildingMulti(false);
    }
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      const success = importData(content);
      if (success) {
        toast.success("Knowledge graph imported successfully!");
      } else {
        toast.error("Invalid file format");
      }
    };
    reader.readAsText(file);
    
    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const getDifficultyColor = (diff: string) => {
    switch (diff) {
      case "beginner":
        return "bg-green-100 text-green-700";
      case "intermediate":
        return "bg-yellow-100 text-yellow-700";
      case "advanced":
        return "bg-red-100 text-red-700";
      default:
        return "bg-gray-100 text-gray-700";
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-violet-50 via-white to-blue-50">
      {/* Header */}
      <div className="bg-white border-b sticky top-0 z-10 shadow-sm">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <Link to="/" className="flex items-center gap-2">
              <NeuroMapLogo className="size-8" />
              <span className="font-bold">NeuroMap</span>
            </Link>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={handleLoadDemo}>
                <Sparkles className="size-4 mr-2" />
                Load Demo
              </Button>
              <Button variant="outline" size="sm" onClick={handleClearAll} disabled={topics.length === 0}>
                <RotateCcw className="size-4 mr-2" />
                Clear All
              </Button>
              <Link to="/graph">
                <Button variant="outline" size="sm" disabled={topics.length === 0}>
                  <Network className="size-4 mr-2" />
                  View Graph
                </Button>
              </Link>
              <Link to="/path">
                <Button variant="outline" size="sm" disabled={topics.length === 0}>
                  <Route className="size-4 mr-2" />
                  Learning Path
                </Button>
              </Link>
              <Button variant="outline" size="sm" onClick={handleExport} disabled={topics.length === 0}>
                <Download className="size-4 mr-2" />
                Export
              </Button>
              <Button variant="outline" size="sm" onClick={handleImport}>
                <Upload className="size-4 mr-2" />
                Import
              </Button>
              <input
                type="file"
                ref={fileInputRef}
                className="hidden"
                accept=".json"
                onChange={handleFileChange}
              />
            </div>
          </div>
        </div>
      </div>

      <div className="container mx-auto px-4 py-8">
        {/* AI-Powered Graph Generator */}
        <div className="bg-gradient-to-r from-violet-600 to-blue-600 rounded-2xl p-6 shadow-lg mb-8 text-white">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="size-5" />
            <h2 className="font-bold text-lg">AI-Powered Knowledge Graph</h2>
          </div>
          <p className="text-violet-100 text-sm mb-4">
            Enter any skill or subject and instantly generate a spectral knowledge graph with AI-predicted difficulty, personalized learning paths, and per-topic explanations.
          </p>
          <div className="flex gap-3">
            <div className="flex-1 relative">
              <Input
                className="bg-white/10 border-white/30 placeholder:text-violet-200 text-white"
                placeholder="e.g. Machine Learning, Calculus, React..."
                value={aiSkill}
                onChange={(e) => setAiSkill(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleGenerateAiGraph()}
              />

              {(isCheckingSpelling || spellSuggestions.length > 0) && (
                <div className="absolute left-0 right-0 mt-2 bg-white text-gray-800 rounded-lg shadow-xl border border-violet-100 z-20 overflow-hidden">
                  {isCheckingSpelling && (
                    <div className="px-3 py-2 text-xs text-gray-500">Checking spelling…</div>
                  )}

                  {!isCheckingSpelling && spellSuggestions.length > 0 && (
                    <>
                      <div className="px-3 pt-2 pb-1 text-[11px] uppercase tracking-wide text-violet-600 font-semibold">
                        Did you mean
                      </div>
                      {spellSuggestions.map((option) => (
                        <button
                          key={`spell-option-${option}`}
                          type="button"
                          className="w-full text-left px-3 py-2 text-sm hover:bg-violet-50"
                          onClick={() => setAiSkill(option)}
                        >
                          {option}
                        </button>
                      ))}
                    </>
                  )}
                </div>
              )}
            </div>
            <Button
              onClick={handleGenerateAiGraph}
              className="bg-white text-violet-700 hover:bg-violet-50 font-semibold px-5"
            >
              <Sparkles className="size-4 mr-2" />
              Generate Graph
            </Button>
          </div>
        </div>

        {/* Multi-Skill Merger */}
        <div className="bg-gradient-to-r from-blue-600 to-cyan-600 rounded-2xl p-6 shadow-lg mb-8 text-white">
          <div className="flex items-center gap-2 mb-2">
            <Network className="size-5" />
            <h2 className="font-bold text-lg">Build Combined NeuroMap</h2>
          </div>
          <p className="text-blue-100 text-sm mb-4">
            Merge 2+ skills into one graph. See how topics connect across domains, discover bridge concepts, and learn with optimal interleaved paths.
          </p>
          <div className="space-y-3">
            <div className="flex gap-3">
              <div className="flex-1">
                <Input
                  className="bg-white/10 border-white/30 placeholder:text-blue-200 text-white"
                  placeholder="e.g. Machine Learning, Linear Algebra, Python..."
                  value={multiSkillInput}
                  onChange={(e) => setMultiSkillInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleAddMultiSkill()}
                />
              </div>
              <Button
                onClick={handleAddMultiSkill}
                className="bg-white text-blue-700 hover:bg-blue-50 font-semibold px-5"
              >
                <Plus className="size-4 mr-2" />
                Add
              </Button>
            </div>
            
            {selectedSkills.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {selectedSkills.map((skill) => (
                  <div
                    key={skill}
                    className="bg-white/20 px-3 py-1.5 rounded-full flex items-center gap-2 text-sm border border-white/30"
                  >
                    <span>{skill}</span>
                    <button
                      onClick={() => handleRemoveMultiSkill(skill)}
                      className="text-white/70 hover:text-white ml-1"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}

            <Button
              onClick={handleBuildMultiSkillGraph}
              disabled={selectedSkills.length < 2 || isBuildingMulti}
              className="w-full bg-white text-blue-700 hover:bg-blue-50 font-semibold"
            >
              {isBuildingMulti ? (
                <>
                  <Loader2 className="size-4 mr-2 animate-spin" />
                  Building…
                </>
              ) : (
                <>
                  <Network className="size-4 mr-2" />
                  Merge {selectedSkills.length} Skills
                </>
              )}
            </Button>
          </div>
        </div>

        <div className="bg-white rounded-2xl p-6 shadow-lg mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-lg">Workspace Hub</h2>
            <Badge variant="outline" className="text-xs">{savedGraphs.length} saved graphs</Badge>
          </div>

          <Tabs defaultValue="saved" className="w-full">
            <TabsList className="grid grid-cols-2 h-9">
              <TabsTrigger value="saved" className="text-xs">Saved Graphs</TabsTrigger>
              <TabsTrigger value="guide" className="text-xs">Learning Guide</TabsTrigger>
            </TabsList>

            <TabsContent value="saved" className="mt-4 space-y-3">
              <div className="flex items-center gap-2">
                <Bookmark className="size-4 text-violet-600" />
                <p className="text-sm text-gray-700">Open saved AI graphs with full features</p>
              </div>

              <div className="flex gap-2">
                <Button size="sm" variant={savedFilter === "all" ? "default" : "outline"} className="h-7 text-[11px]" onClick={() => setSavedFilter("all")}>All</Button>
                <Button size="sm" variant={savedFilter === "single" ? "default" : "outline"} className="h-7 text-[11px]" onClick={() => setSavedFilter("single")}>Single</Button>
                <Button size="sm" variant={savedFilter === "merged" ? "default" : "outline"} className="h-7 text-[11px]" onClick={() => setSavedFilter("merged")}>Merged</Button>
              </div>

              {filteredSavedGraphs.length > 0 ? (
                <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                  {filteredSavedGraphs.map((graph) => (
                    <div key={graph.id} className="border rounded-lg p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="font-medium text-sm truncate">{graph.title}</p>
                          <div className="mt-1 flex items-center gap-2">
                            <Badge variant={graph.type === "merged" ? "default" : "secondary"} className="text-[10px]">
                              {graph.type === "merged" ? "Merged" : "Single"}
                            </Badge>
                            <span className="text-[11px] text-gray-500">{graph.topicCount} topics • {graph.edgeCount} edges</span>
                          </div>
                        </div>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 w-7 p-0"
                          onClick={() => removeSavedGraph(graph.id)}
                          title="Remove saved graph"
                        >
                          <Trash2 className="size-3.5 text-red-500" />
                        </Button>
                      </div>

                      <div className="mt-2">
                        <Link to={graph.route}>
                          <Button size="sm" className="h-7 text-[11px] bg-violet-600 hover:bg-violet-700 w-full">
                            Open Graph Tab
                          </Button>
                        </Link>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-500">No saved graphs yet. Generate an AI graph, then click Add to NeuroMap.</p>
              )}
            </TabsContent>

            <TabsContent value="guide" className="mt-4 space-y-3">
              <div className="flex items-center gap-2">
                <Compass className="size-4 text-blue-600" />
                <p className="text-sm text-gray-700">Suggested way to use NeuroMap effectively</p>
              </div>

              <div className="space-y-2">
                <div className="rounded-lg border bg-violet-50 p-3">
                  <p className="text-sm font-medium text-violet-800">1. Start with a single skill graph</p>
                  <p className="text-xs text-violet-700 mt-1">Build intuition in one subject and add it to NeuroMap.</p>
                </div>
                <div className="rounded-lg border bg-blue-50 p-3">
                  <p className="text-sm font-medium text-blue-800">2. Save merged graphs for cross-links</p>
                  <p className="text-xs text-blue-700 mt-1">Use merged graphs to discover bridges across subjects and strengthen transfer learning.</p>
                </div>
                <div className="rounded-lg border bg-emerald-50 p-3">
                  <p className="text-sm font-medium text-emerald-800">3. Use View Graph for the combined map</p>
                  <p className="text-xs text-emerald-700 mt-1">NeuroMap combines all added topics and links what can be connected from your history.</p>
                </div>
              </div>

              <div className="flex gap-2">
                <Link to="/graph" className="flex-1">
                  <Button size="sm" variant="outline" className="w-full">Open NeuroMap</Button>
                </Link>
                <Link to="/path" className="flex-1">
                  <Button size="sm" className="w-full bg-blue-600 hover:bg-blue-700">Open Learning Path</Button>
                </Link>
              </div>
            </TabsContent>
          </Tabs>
        </div>

        <div className="grid lg:grid-cols-2 gap-8">
          {/* Input Section */}
          <div>
            <div className="bg-white rounded-2xl p-6 shadow-lg mb-6">
              <h2 className="font-semibold mb-4">Add a Topic</h2>
              
              <div className="space-y-4">
                <div>
                  <Label htmlFor="name">Topic Name *</Label>
                  <div className="relative">
                    <Input
                      id="name"
                      placeholder="e.g., Linear Algebra, React Hooks, Quantum Mechanics"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleAddTopic()}
                    />

                    {(isCheckingTopicSpelling || topicSpellSuggestions.length > 0) && (
                      <div className="absolute left-0 right-0 mt-2 bg-white text-gray-800 rounded-lg shadow-xl border border-violet-100 z-20 overflow-hidden">
                        {isCheckingTopicSpelling && (
                          <div className="px-3 py-2 text-xs text-gray-500">Checking spelling…</div>
                        )}

                        {!isCheckingTopicSpelling && topicSpellSuggestions.length > 0 && (
                          <>
                            <div className="px-3 pt-2 pb-1 text-[11px] uppercase tracking-wide text-violet-600 font-semibold">
                              Did you mean
                            </div>
                            {topicSpellSuggestions.map((option) => (
                              <button
                                key={`topic-spell-option-${option}`}
                                type="button"
                                className="w-full text-left px-3 py-2 text-sm hover:bg-violet-50"
                                onClick={() => setName(option)}
                              >
                                {option}
                              </button>
                            ))}
                          </>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                <div>
                  <Label htmlFor="description">Description (optional)</Label>
                  <Textarea
                    id="description"
                    placeholder="Brief description of what this topic covers..."
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={3}
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="category">Category</Label>
                    <Select value={category} onValueChange={setCategory}>
                      <SelectTrigger id="category">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {categories.map((cat) => (
                          <SelectItem key={cat} value={cat}>
                            {cat}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div>
                    <Label htmlFor="difficulty">Difficulty</Label>
                    <Select value={difficulty} onValueChange={(v: any) => setDifficulty(v)}>
                      <SelectTrigger id="difficulty">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="beginner">Beginner</SelectItem>
                        <SelectItem value="intermediate">Intermediate</SelectItem>
                        <SelectItem value="advanced">Advanced</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <Button onClick={handleAddTopic} className="w-full bg-violet-600 hover:bg-violet-700">
                  <Plus className="size-4 mr-2" />
                  Add Topic
                </Button>
              </div>
            </div>

            {topics.length >= 2 && (
              <Button
                onClick={handleGenerateGraph}
                className="w-full bg-blue-600 hover:bg-blue-700"
                size="lg"
              >
                <Network className="size-5 mr-2" />
                Generate Knowledge Graph ({topics.length} topics)
              </Button>
            )}
          </div>

          {/* Topics List */}
          <div>
            <div className="bg-white rounded-2xl p-6 shadow-lg">
              <h2 className="font-semibold mb-4">Your Topics ({topics.length})</h2>
              
              {topics.length === 0 ? (
                <div className="text-center py-12 text-gray-500">
                  <Brain className="size-12 mx-auto mb-3 opacity-30" />
                  <p>No topics yet</p>
                  <p className="text-sm">Add your first topic to get started</p>
                </div>
              ) : (
                <div className="space-y-3 max-h-[600px] overflow-y-auto">
                  {topics.map((topic) => (
                    <div
                      key={topic.id}
                      className="border rounded-lg p-4 hover:border-violet-300 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-2">
                            <h3 className="font-medium truncate">{topic.name}</h3>
                            <Badge className={getDifficultyColor(topic.difficulty)} variant="secondary">
                              {topic.difficulty}
                            </Badge>
                            {topic.importedFromAi && (
                              <Badge className="bg-violet-100 text-violet-700" variant="secondary">
                                AI Imported
                              </Badge>
                            )}
                          </div>
                          {topic.description && (
                            <p className="text-sm text-gray-600 mb-2">{topic.description}</p>
                          )}
                          <p className="text-xs text-gray-500">{topic.category}</p>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => removeTopic(topic.id)}
                        >
                          <Trash2 className="size-4 text-red-500" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}