/**
 * EnhancedGraph.tsx — NeuroMap interactive knowledge graph
 *
 * Features:
 *  1. Interactive visualization — custom nodes with difficulty meters,
 *     cluster colours, mastery state, path-highlight rings
 *  2. Personalized learning paths — ACO + full + quick-start paths;
 *     selecting a path highlights its nodes on the graph in real time
 *  3. Click a node → AI summary panel with explanation, resources,
 *     difficulty meter, prerequisites, study tip, master button
 *  4. Dynamic topic addition — "Add Topic" scrapes a new topic and
 *     merges nodes/edges into the live graph without a page reload
 *  5. AI-generated summaries from /api/summary (GNN + structural analysis)
 */

import { useEffect, useState, useCallback, useMemo, type MouseEvent as ReactMouseEvent, type ReactNode } from "react";
import { useParams, Link } from "react-router";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  Node,
  Edge,
  NodeProps,
  useNodesState,
  useEdgesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { Button }   from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge }    from "../components/ui/badge";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Progress } from "../components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Input }    from "../components/ui/input";
import {
  Home, BarChart3, Zap, AlertTriangle, TrendingUp,
  Plus, X, BookOpen, ExternalLink, ChevronRight, CheckCircle2,
  Layers, ArrowRight, Loader2, Sparkles, Target, Clock, Network,
} from "lucide-react";
import { NeuroMapLogo } from "../components/NeuroMapLogo";
import { useTopics } from "../context/TopicsContext";
import { toast } from "sonner";

// ── Types ─────────────────────────────────────────────────────────────────────

interface TopicNodeData extends Record<string, unknown> {
  label: string;
  level: string;
  mastered: boolean;
  difficultyScore: number;
  cluster: number;
  isInPath: boolean;
  isBridge: boolean;
  estimatedMinutes?: number;
}

interface TopicSummary {
  topicId: string;
  name: string;
  level: string;
  difficultyScore: number;
  difficultyExplanation: string;
  description: string;
  keyPoints: string[];
  studyTip: string;
  resources: Array<{ title: string; url: string; source: string; type: string }>;
  depth: number;
  prerequisiteCount: number;
  unlocksCount: number;
  estimatedMinutes: number;
}

interface LearningPath {
  id: string;
  name: string;
  description: string;
  duration: string;
  difficulty: string;
  nodeIds: string[];
  steps: Array<{
    topicId: string;
    name: string;
    level: string;
    requires: string[];
    reason: string;
  }>;
}

interface CurriculumStats {
  numTopics: number;
  numEdges: number | null;
  algebraicConnectivity?: number;
  connectedComponents?: number;
  insights?: Record<
    string,
    | { rating: string; description: string; chokepoints?: string[] }
    | { type: string; description: string }
    | undefined
  >;
}

// ── Custom Node ───────────────────────────────────────────────────────────────

const CLUSTER_BORDER = [
  "border-blue-400",
  "border-emerald-400",
  "border-purple-400",
  "border-orange-400",
  "border-pink-400",
];
const CLUSTER_PATH_BG = [
  "bg-blue-50",
  "bg-emerald-50",
  "bg-purple-50",
  "bg-orange-50",
  "bg-pink-50",
];

interface TopicNodeComponentProps {
  data: Record<string, unknown>;
  selected?: boolean;
  isConnectable?: boolean;
  xPos?: number;
  yPos?: number;
  dragging?: boolean;
}

function TopicNodeComponent({ data, selected }: TopicNodeComponentProps) {
  const topicData = data as TopicNodeData;
  const score  = (topicData.difficultyScore as number) ?? 0.5;
  const pct    = Math.round(score * 100);
  const bar    = pct < 35 ? "bg-green-500" : pct < 65 ? "bg-amber-500" : "bg-red-500";
  const idx    = ((topicData.cluster as number) || 0) % CLUSTER_BORDER.length;

  return (
    <div
      className={[
        "w-44 rounded-xl border-2 overflow-hidden transition-all duration-200",
        topicData.mastered as boolean
          ? "border-emerald-500 bg-emerald-50 shadow-lg"
          : selected
          ? `ring-2 ring-violet-400 border-violet-600 bg-violet-50 shadow-xl`
          : (topicData.isInPath as boolean)
          ? `${CLUSTER_BORDER[idx]} ${CLUSTER_PATH_BG[idx]} shadow-md`
          : `${CLUSTER_BORDER[idx]} bg-white shadow-sm hover:shadow-md`,
      ].join(" ")}
    >
      <Handle type="target" position={Position.Top} style={{ background: "#9ca3af" }} />

      <div className="px-3 py-2.5">
        {/* Name */}
        <div className="font-semibold text-xs leading-tight mb-1.5 line-clamp-2" title={topicData.label as string}>
          {topicData.label as string}
        </div>

        {/* Badges */}
        <div className="flex flex-wrap gap-1 mb-2">
          <span className={[
            "text-[10px] px-1.5 py-0.5 rounded-full",
            topicData.level === "foundational" ? "bg-blue-100 text-blue-700"
            : topicData.level === "intermediate" ? "bg-yellow-100 text-yellow-700"
            : topicData.level === "advanced"     ? "bg-orange-100 text-orange-700"
            : "bg-red-100 text-red-700",
          ].join(" ")}>
            {topicData.level as string}
          </span>
          {(topicData.isBridge as boolean) && (
            <span className="text-[10px] bg-orange-100 text-orange-700 px-1.5 py-0.5 rounded-full font-medium">
              ⇌ bridge
            </span>
          )}
          {(topicData.mastered as boolean) && (
            <span className="text-[10px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded-full">
              ✓
            </span>
          )}
        </div>

        {/* Difficulty bar */}
        <div className="space-y-0.5">
          <div className="flex justify-between text-[9px] text-gray-400">
            <span>Difficulty</span>
            <span className={pct < 35 ? "text-green-600" : pct < 65 ? "text-amber-600" : "text-red-600"}>
              {pct}%
            </span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-1.5">
            <div className={`h-1.5 rounded-full ${bar}`} style={{ width: `${pct}%` }} />
          </div>
        </div>

        {/* Time estimate */}
        {topicData.estimatedMinutes != null && (
          <div className="text-[9px] text-gray-400 mt-1.5 flex items-center gap-0.5">
            <Clock className="size-2.5" />
            {topicData.estimatedMinutes as number}m
          </div>
        )}
      </div>

      <Handle type="source" position={Position.Bottom} style={{ background: "#9ca3af" }} />
    </div>
  );
}

const nodeTypes = { topicNode: TopicNodeComponent as any } as const;

// ── Helpers ───────────────────────────────────────────────────────────────────

function diffBar(score: number) {
  const pct = Math.round(score * 100);
  const col = pct < 35 ? "bg-green-500" : pct < 65 ? "bg-amber-500" : "bg-red-500";
  const text = pct < 35 ? "text-green-700" : pct < 65 ? "text-amber-700" : "text-red-700";
  return { pct, col, text };
}

function parseRequestedSkills(input: string): string[] {
  return input
    .split(/\s*(?:,|&|\+|\band\b|\bwith\b|\bin tandem\b)\s*/i)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

// ── Main Component ────────────────────────────────────────────────────────────

export function EnhancedGraph() {
  const { skill } = useParams<{ skill: string }>();
  const decoded   = skill ? decodeURIComponent(skill) : "";
  const requestedSkills = useMemo(() => parseRequestedSkills(decoded), [decoded]);
  const { addAiGraphToNeuroMap } = useTopics();

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  const [loading,      setLoading]      = useState(true);
  const [error,        setError]        = useState<string | null>(null);
  const [rawNodes,     setRawNodes]     = useState<any[]>([]);
  const [paths,        setPaths]        = useState<LearningPath[]>([]);
  const [stats,        setStats]        = useState<CurriculumStats | null>(null);
  const [selectedPath, setSelectedPath] = useState("path-aco");
  const [recs,         setRecs]         = useState<any[]>([]);
  const [progress,     setProgress]     = useState(0);
  const [mastered,     setMastered]     = useState<Set<string>>(new Set());
  const [isMastering,  setIsMastering]  = useState(false);
  const [activeSkillKey, setActiveSkillKey] = useState("");
  const [addedToNeuroMap, setAddedToNeuroMap] = useState(false);

  // Node detail panel
  const [selectedId,     setSelectedId]     = useState<string | null>(null);
  const [activeTab,      setActiveTab]      = useState("paths");
  const [summaryCache,   setSummaryCache]   = useState<Record<string, TopicSummary>>({});
  const [summaryLoading, setSummaryLoading] = useState(false);

  // Dynamic add-topic modal
  const [addOpen,      setAddOpen]      = useState(false);
  const [newTopic,     setNewTopic]     = useState("");
  const [addingTopic,  setAddingTopic]  = useState(false);

  // ── Build ReactFlow nodes ───────────────────────────────────────────────────

  const toFlowNodes = useCallback(
    (raws: any[], masteredSet: Set<string>, pathIds: Set<string>): Node[] =>
      raws.map((n) => ({
        id:       n.id,
        type:     "topicNode",
        position: n.position,
        data: {
          label:           n.data.originalName || n.data.label,
          level:           n.data.level,
          mastered:        masteredSet.has(n.id),
          difficultyScore: n.data.difficultyScore ?? 0.5,
          cluster:         n.data.cluster ?? 0,
          isInPath:        pathIds.has(n.id),
          isBridge:        n.data.isBridge ?? false,
          estimatedMinutes: n.data.estimatedMinutes,
          // kept for the detail panel
          _raw: n.data,
        } as TopicNodeData,
      })),
    []
  );

  // ── Fetch graph ─────────────────────────────────────────────────────────────

  const fetchGraph = useCallback(async () => {
    if (!decoded) return;
    setLoading(true);
    setError(null);
    try {
      const isParallel = requestedSkills.length > 1;
      const endpoint = isParallel ? "/api/generate-parallel" : "/api/generate";
      const payload = isParallel ? { skills: requestedSkills } : { skill: decoded };

      const res  = await fetch(endpoint, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();

      const skillKey = (data.skillKey ?? (isParallel
        ? requestedSkills.map((s) => s.toLowerCase()).join("+")
        : decoded.toLowerCase())) as string;
      setActiveSkillKey(skillKey);
      setSummaryCache({});

      // Fetch difficulty scores — must run after /api/generate stores the graph
      const dr = await fetch(`/api/difficulty/${encodeURIComponent(skillKey)}`);
      let diffScores: Record<string, number> = {};
      if (dr.ok) {
        const diffData = await dr.json();
        diffScores = diffData.difficulties ?? {};
        setRecs(diffData.recommendations ?? []);
      }

      // Merge GNN difficulty scores into raw node data
      const mergedNodes = (data.nodes as any[]).map((n: any) => ({
        ...n,
        data: { ...n.data, difficultyScore: diffScores[n.id] ?? 0.5 },
      }));

      setRawNodes(mergedNodes);
      setPaths(data.paths || []);
      setStats(data.stats);

      const defaultPathId = (data.paths as LearningPath[])?.find(p => p.id === "path-aco")?.id
        ?? data.paths?.[0]?.id
        ?? "path-full";
      setSelectedPath(defaultPathId);

      const pathIds    = new Set<string>(data.paths?.find((p: any) => p.id === defaultPathId)?.nodeIds ?? []);
      const masteredSet = new Set<string>(
        mergedNodes.filter((n: any) => n.data.mastered).map((n: any) => n.id as string)
      );
      setMastered(masteredSet);
      setProgress(masteredSet.size / Math.max(mergedNodes.length, 1));

      setNodes(toFlowNodes(mergedNodes, masteredSet, pathIds));
      setEdges(
        (data.edges as any[]).map(e => ({
          id: e.id, source: e.source, target: e.target,
          animated: e.animated, markerEnd: e.markerEnd,
        }))
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [decoded, requestedSkills, toFlowNodes, setNodes, setEdges]);

  useEffect(() => { fetchGraph(); }, [fetchGraph]);

  // ── Sync path highlights ────────────────────────────────────────────────────

  useEffect(() => {
    const pathIds = new Set<string>(paths.find(p => p.id === selectedPath)?.nodeIds ?? []);
    setNodes(nds => nds.map(n => ({
      ...n,
      data: { ...n.data, isInPath: pathIds.has(n.id) },
    })));
  }, [selectedPath, paths, setNodes]);

  // ── Node click → fetch summary ──────────────────────────────────────────────

  const onNodeClick = useCallback(async (_: ReactMouseEvent, node: Node) => {
    setSelectedId(node.id);
    setActiveTab("detail");
    if (!summaryCache[node.id] && activeSkillKey) {
      setSummaryLoading(true);
      try {
        const r = await fetch(`/api/summary/${encodeURIComponent(activeSkillKey)}/${node.id}`);
        if (r.ok) {
          const d: TopicSummary = await r.json();
          setSummaryCache(p => ({ ...p, [node.id]: d }));
        }
      } finally {
        setSummaryLoading(false);
      }
    }
  }, [activeSkillKey, summaryCache]);

  // ── Master topic ────────────────────────────────────────────────────────────

  const masterTopic = useCallback(async (topicId: string) => {
    // Prevent concurrent submissions
    if (isMastering) return;
    
    setIsMastering(true);
    try {
      const r = await fetch("/api/master", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ skill: activeSkillKey, topicId }),
      });
      if (!r.ok) { alert("Request failed"); return; }
      const d = await r.json();
      if (d.success) {
        setProgress(d.progress);
        setMastered(prev => new Set([...prev, topicId]));
        setNodes(nds => nds.map(n =>
          n.id === topicId ? { ...n, data: { ...n.data, mastered: true } } : n
        ));
        const dr = await fetch(`/api/difficulty/${encodeURIComponent(activeSkillKey)}`);
        if (dr.ok) {
          const diffData = await dr.json();
          setRecs(diffData.recommendations ?? []);
          const diffScores: Record<string, number> = diffData.difficulties ?? {};
          setNodes(nds => nds.map(n => ({
            ...n,
            data: { ...n.data, difficultyScore: diffScores[n.id] ?? (n.data.difficultyScore as number) },
          })));
        }
      } else {
        alert(`Cannot master yet: ${d.reason}`);
      }
    } finally {
      setIsMastering(false);
    }
  }, [activeSkillKey, setNodes, isMastering]);

  // ── Dynamic add topic ───────────────────────────────────────────────────────

  const handleAddTopic = useCallback(async () => {
    if (!newTopic.trim()) return;
    setAddingTopic(true);
    try {
      const r = await fetch("/api/sub-graph", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ topic: newTopic.trim() }),
      });
      if (!r.ok) throw new Error(`Nothing found for "${newTopic}"`);
      const d = await r.json();

      // Offset new nodes to the right of the existing graph
      const maxX  = rawNodes.reduce((m, n) => Math.max(m, n.position.x), 0);
      const shift = maxX + 450;
      const newRaw: any[] = d.nodes.map((n: any) => ({
        ...n, position: { x: n.position.x + shift, y: n.position.y },
      }));

      // Fetch difficulty scores for the newly added sub-graph
      let newDiffScores: Record<string, number> = {};
      const ndr = await fetch(`/api/difficulty/${encodeURIComponent(newTopic.trim())}`);
      if (ndr.ok) {
        const nd = await ndr.json();
        newDiffScores = nd.difficulties ?? {};
      }
      const newRawWithDiff = newRaw.map((n: any) => ({
        ...n,
        data: { ...n.data, difficultyScore: newDiffScores[n.id] ?? 0.5 },
      }));

      // Avoid duplicate raw nodes by filtering out IDs that already exist
      const existingRawIds = new Set(rawNodes.map((n: any) => n.id));
      const newRawFiltered = newRawWithDiff.filter((n: any) => !existingRawIds.has(n.id));
      
      setRawNodes(prev => [...prev, ...newRawFiltered]);
      
      // Compute current path IDs based on selectedPath
      const currentPathIds = new Set<string>(paths.find(p => p.id === selectedPath)?.nodeIds ?? []);
      
      // Avoid duplicate flow nodes
      const newFlowNodes = toFlowNodes(newRawFiltered, mastered, currentPathIds);
      const existingNodeIds = new Set(nodes.map((n) => n.id));
      const newNodesFiltered = newFlowNodes.filter((n) => !existingNodeIds.has(n.id));
      setNodes(prev => [...prev, ...newNodesFiltered]);
      
      // Avoid duplicate edges
      const existingEdgeIds = new Set(edges.map((e) => e.id));
      const newEdgesFiltered = (d.edges as any[]).filter((e: any) => !existingEdgeIds.has(e.id));
      setEdges(prev => [
        ...prev,
        ...newEdgesFiltered.map((e: any) => ({
          id: e.id, source: e.source, target: e.target,
          animated: e.animated, markerEnd: e.markerEnd,
        })),
      ]);
      
      // Avoid duplicate paths
      const existingPathIds = new Set(paths.map((p) => p.id));
      const newPathsFiltered = (d.paths ?? []).filter((p: any) => !existingPathIds.has(p.id));
      setPaths(prev => [...prev, ...newPathsFiltered]);
      
      setAddOpen(false);
      setNewTopic("");
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed");
    } finally {
      setAddingTopic(false);
    }
  }, [newTopic, rawNodes, nodes, edges, paths, mastered, selectedPath, toFlowNodes, setNodes, setEdges]);

  // ── Derived ─────────────────────────────────────────────────────────────────

  const selectedSummary = selectedId ? summaryCache[selectedId] : null;
  const selectedRaw     = rawNodes.find(n => n.id === selectedId)?.data ?? null;
  const currentPath     = paths.find(p => p.id === selectedPath);

  const handleAddToNeuroMap = useCallback(() => {
    if (rawNodes.length === 0) {
      toast.error("No graph data to add yet");
      return;
    }
    const result = addAiGraphToNeuroMap({
      nodes: rawNodes,
      edges: edges.map((e) => ({ source: e.source, target: e.target })),
    });
    setAddedToNeuroMap(true);
    toast.success(`Added ${result.addedTopics} topic(s) and ${result.addedRelations} relation(s) to NeuroMap`);
  }, [rawNodes, edges, addAiGraphToNeuroMap]);

  // ── Loading / error ─────────────────────────────────────────────────────────

  if (loading) return (
    <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-violet-50 to-white">
      <div className="text-center max-w-sm px-4">
        <NeuroMapLogo className="size-16 mx-auto mb-4 animate-pulse" />
        <p className="text-lg font-semibold text-gray-800 mb-1">Building your knowledge graph…</p>
        <p className="text-sm text-gray-500">Web scraping → spectral layout → ACO path optimisation → difficulty analysis</p>
      </div>
    </div>
  );

  if (error) return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-red-600 flex gap-2"><AlertTriangle className="size-5" />Error</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-gray-600 mb-4">{error}</p>
          <Link to="/workspace"><Button className="w-full bg-violet-600 hover:bg-violet-700">Back to Workspace</Button></Link>
        </CardContent>
      </Card>
    </div>
  );

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="h-screen flex flex-col bg-gray-50 overflow-hidden">

      {/* ── Header ── */}
      <header className="bg-white border-b shadow-sm z-20 px-4 py-2.5 shrink-0">
        <div className="flex items-center justify-between gap-4">
          <Link to="/" className="flex items-center gap-2 min-w-0">
            <NeuroMapLogo className="size-6 shrink-0" />
            <span className="font-bold text-gray-800 truncate">{decoded}</span>
          </Link>

          <div className="flex items-center gap-3 shrink-0">
            {/* Progress */}
            <div className="hidden sm:flex items-center gap-2 min-w-[160px]">
              <TrendingUp className="size-4 text-emerald-600 shrink-0" />
              <Progress value={progress * 100} className="h-2 flex-1" />
              <span className="text-xs font-medium text-gray-600 whitespace-nowrap">
                {(progress * 100).toFixed(0)}%
              </span>
            </div>

            <Button
              variant={addedToNeuroMap ? "secondary" : "outline"}
              size="sm"
              onClick={handleAddToNeuroMap}
              disabled={addedToNeuroMap}
            >
              <Network className="size-4 mr-1" />
              {addedToNeuroMap ? "Added to NeuroMap" : "Add to NeuroMap"}
            </Button>

            <Button variant="outline" size="sm" onClick={() => setAddOpen(true)}>
              <Plus className="size-4 mr-1" /> Add Topic
            </Button>
            <Link to="/workspace">
              <Button variant="ghost" size="sm">
                <Home className="size-4 mr-1" /> Back
              </Button>
            </Link>
          </div>
        </div>
      </header>

      {/* ── Body ── */}
      <div className="flex-1 flex overflow-hidden">

        {/* Graph canvas */}
        <div className="flex-1 relative">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes as any}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            fitView
            fitViewOptions={{ padding: 0.15 }}
          >
            <Background color="#e5e7eb" gap={20} />
            <Controls />
            <MiniMap
              nodeColor={(n) => {
                const topicData = n.data as Record<string, unknown> as TopicNodeData;
                if (topicData.mastered)  return "#10b981";
                if (topicData.isInPath)  return "#8b5cf6";
                return "#cbd5e1";
              }}
              maskColor="rgba(0,0,0,0.06)"
            />
          </ReactFlow>

          {/* Click hint */}
          {!selectedId && (
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-white/90 backdrop-blur px-4 py-2 rounded-full shadow text-xs text-gray-500 pointer-events-none select-none">
              Click any node to see its AI summary, resources, and difficulty breakdown
            </div>
          )}
        </div>

        {/* ── Right sidebar ── */}
        <div className="w-[400px] border-l bg-white flex flex-col overflow-hidden shrink-0">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-col h-full">
            <TabsList className="grid grid-cols-4 mx-3 mt-3 mb-0 shrink-0">
              <TabsTrigger value="detail"   className="text-xs">Detail</TabsTrigger>
              <TabsTrigger value="paths"    className="text-xs">Paths</TabsTrigger>
              <TabsTrigger value="insights" className="text-xs">Insights</TabsTrigger>
              <TabsTrigger value="next"     className="text-xs">Next Up</TabsTrigger>
            </TabsList>

            {/* ── Detail Tab ── */}
            <TabsContent value="detail" className="flex-1 overflow-y-auto px-3 pb-4 mt-3">
              {!selectedId ? (
                <div className="flex flex-col items-center justify-center h-full text-gray-400 py-16 text-center">
                  <Layers className="size-12 mb-3 opacity-25" />
                  <p className="text-sm font-medium">No topic selected</p>
                  <p className="text-xs mt-1">Click any node in the graph</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Header row */}
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <h2 className="font-bold text-base leading-snug truncate">
                        {selectedSummary?.name ?? selectedRaw?.originalName ?? selectedRaw?.label ?? "—"}
                      </h2>
                      <div className="flex flex-wrap gap-1.5 mt-1">
                        <Badge variant="secondary" className="text-xs capitalize">
                          {selectedSummary?.level ?? selectedRaw?.level}
                        </Badge>
                        {selectedRaw?.isBridge && (
                          <Badge className="text-xs bg-orange-100 text-orange-700 border-orange-200">
                            Bridge Concept
                          </Badge>
                        )}
                        {mastered.has(selectedId) && (
                          <Badge className="text-xs bg-emerald-100 text-emerald-700 border-emerald-200">
                            ✓ Mastered
                          </Badge>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => { setSelectedId(null); setActiveTab("paths"); }}
                      className="text-gray-300 hover:text-gray-500 mt-1"
                    >
                      <X className="size-4" />
                    </button>
                  </div>

                  {/* Difficulty meter */}
                  {(() => {
                    const sc = selectedSummary?.difficultyScore ?? (selectedRaw?.difficultyScore as number) ?? 0.5;
                    const { pct, col, text } = diffBar(sc);
                    return (
                      <div className="bg-gray-50 rounded-xl p-3 border border-gray-100">
                        <div className="flex justify-between items-center mb-2">
                          <span className="text-xs font-medium text-gray-600">Difficulty Meter</span>
                          <span className={`text-sm font-bold ${text}`}>{pct}%</span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-3">
                          <div className={`h-3 rounded-full transition-all duration-500 ${col}`} style={{ width: `${pct}%` }} />
                        </div>
                        <div className="flex justify-between text-[10px] text-gray-400 mt-1">
                          <span>Beginner</span><span>Intermediate</span><span>Expert</span>
                        </div>
                      </div>
                    );
                  })()}

                  {/* AI Summary */}
                  {summaryLoading ? (
                    <div className="flex items-center gap-2 text-gray-400 text-sm py-2">
                      <Loader2 className="size-4 animate-spin" />
                      Generating AI summary…
                    </div>
                  ) : selectedSummary ? (
                    <>
                      {/* Description */}
                      {selectedSummary.description && (
                        <div>
                          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">What it is</p>
                          <p className="text-sm text-gray-700 leading-relaxed">{selectedSummary.description}</p>
                        </div>
                      )}

                      {/* GNN explanation card */}
                      <div className="bg-blue-50 border border-blue-100 rounded-xl p-3">
                        <div className="flex items-start gap-2">
                          <Sparkles className="size-4 text-blue-500 mt-0.5 shrink-0" />
                          <p className="text-xs text-blue-800 leading-relaxed">{selectedSummary.difficultyExplanation}</p>
                        </div>
                      </div>

                      {/* Key points */}
                      {selectedSummary.keyPoints.length > 0 && (
                        <div>
                          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1.5">Key points</p>
                          <ul className="space-y-1.5">
                            {selectedSummary.keyPoints.map((pt, i) => (
                              <li key={i} className="flex items-start gap-1.5 text-xs text-gray-700">
                                <ChevronRight className="size-3 text-violet-500 mt-0.5 shrink-0" />
                                {pt}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Study tip */}
                      <div className="bg-amber-50 border border-amber-100 rounded-xl p-3">
                        <div className="flex items-start gap-2">
                          <Target className="size-4 text-amber-600 mt-0.5 shrink-0" />
                          <p className="text-xs text-amber-800 leading-relaxed">
                            <span className="font-semibold">Study tip: </span>
                            {selectedSummary.studyTip}
                          </p>
                        </div>
                      </div>

                      {/* Stats grid */}
                      <div className="grid grid-cols-3 gap-2 text-center">
                        {[
                          { val: selectedSummary.prerequisiteCount, label: "Prerequisites" },
                          { val: selectedSummary.unlocksCount,      label: "Unlocks" },
                          { val: `${selectedSummary.estimatedMinutes}m`, label: "Est. study" },
                        ].map(({ val, label }) => (
                          <div key={label} className="bg-gray-50 rounded-lg p-2 border border-gray-100">
                            <div className="text-base font-bold text-gray-800">{val}</div>
                            <div className="text-[10px] text-gray-500">{label}</div>
                          </div>
                        ))}
                      </div>

                      {/* Resources */}
                      {selectedSummary.resources.length > 0 && (
                        <div>
                          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1.5 flex items-center gap-1">
                            <BookOpen className="size-3" /> Learning resources
                          </p>
                          <div className="space-y-1.5">
                            {selectedSummary.resources.map((r, i) => (
                              <a
                                key={i}
                                href={r.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center gap-2 p-2 rounded-lg border hover:bg-violet-50 hover:border-violet-200 transition-colors group"
                              >
                                <ExternalLink className="size-3 text-violet-400 group-hover:text-violet-600 shrink-0" />
                                <div className="flex-1 min-w-0">
                                  <div className="text-xs font-medium text-gray-800 truncate">{r.title}</div>
                                  <div className="text-[10px] text-gray-400">{r.source}</div>
                                </div>
                                <Badge variant="outline" className="text-[10px] shrink-0">{r.type}</Badge>
                              </a>
                            ))}
                          </div>
                        </div>
                      )}
                    </>
                  ) : selectedRaw?.description ? (
                    <p className="text-sm text-gray-600 leading-relaxed">{selectedRaw.description as string}</p>
                  ) : null}

                  {/* Master button */}
                  {!mastered.has(selectedId) && (
                    <Button
                      className="w-full bg-emerald-600 hover:bg-emerald-700"
                      onClick={() => masterTopic(selectedId)}
                      disabled={isMastering}
                    >
                      {isMastering ? (
                        <>
                          <Loader2 className="size-4 mr-2 animate-spin" />
                          Mastering...
                        </>
                      ) : (
                        <>
                          <CheckCircle2 className="size-4 mr-2" />
                          Mark as Mastered
                        </>
                      )}
                    </Button>
                  )}
                </div>
              )}
            </TabsContent>

            {/* ── Paths Tab ── */}
            <TabsContent value="paths" className="flex-1 overflow-y-auto px-3 pb-4 mt-3">
              <div className="space-y-2 mb-3">
                {paths.map((p) => (
                  <Card
                    key={p.id}
                    className={`cursor-pointer transition-all ${
                      selectedPath === p.id
                        ? "ring-2 ring-violet-600 bg-violet-50"
                        : "hover:shadow-md"
                    }`}
                    onClick={() => setSelectedPath(p.id)}
                  >
                    <CardHeader className="pt-3 pb-1 px-3">
                      <CardTitle className="text-xs font-semibold flex items-center gap-1.5">
                        {selectedPath === p.id && (
                          <div className="size-2 rounded-full bg-violet-600 shrink-0" />
                        )}
                        {p.name}
                      </CardTitle>
                      <p className="text-[10px] text-gray-500 mt-0.5 leading-snug">{p.description}</p>
                    </CardHeader>
                    <CardContent className="pb-3 px-3">
                      <div className="flex gap-1.5">
                        <Badge className="text-[10px]">{p.duration}</Badge>
                        <Badge variant="outline" className="text-[10px]">{p.difficulty}</Badge>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>

              {currentPath && (
                <div className="bg-gray-50 rounded-xl p-3 border border-gray-100">
                  <h4 className="text-xs font-semibold text-gray-700 mb-2 flex items-center gap-1.5">
                    <ArrowRight className="size-3 text-violet-500" />
                    Steps — {currentPath.name}
                  </h4>
                  <div className="space-y-1.5 max-h-[380px] overflow-y-auto pr-1">
                    {currentPath.steps.map((step, idx) => (
                      <button
                        key={step.topicId}
                        className={`w-full text-left p-2 rounded-lg border text-xs transition-colors ${
                          mastered.has(step.topicId)
                            ? "bg-emerald-50 border-emerald-200"
                            : "bg-white border-gray-200 hover:bg-violet-50 hover:border-violet-200"
                        }`}
                        onClick={() => {
                          setSelectedId(step.topicId);
                          setActiveTab("detail");
                        }}
                      >
                        <div className="flex items-center gap-2">
                          <span className={`size-5 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 ${
                            mastered.has(step.topicId)
                              ? "bg-emerald-500 text-white"
                              : "bg-violet-100 text-violet-700"
                          }`}>
                            {mastered.has(step.topicId) ? "✓" : idx + 1}
                          </span>
                          <span className="font-medium truncate">{step.name}</span>
                        </div>
                        {step.reason && (
                          <p className="text-gray-400 mt-0.5 ml-7 truncate text-[10px]">{step.reason}</p>
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </TabsContent>

            {/* ── Insights Tab ── */}
            <TabsContent value="insights" className="flex-1 overflow-y-auto px-3 pb-4 mt-3">
              {stats ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-2">
                    <div className="bg-violet-50 rounded-xl p-3 text-center border border-violet-100">
                      <div className="text-2xl font-bold text-violet-700">{stats.numTopics}</div>
                      <div className="text-xs text-gray-500">Topics</div>
                    </div>
                    <div className="bg-blue-50 rounded-xl p-3 text-center border border-blue-100">
                      <div className="text-2xl font-bold text-blue-700">{stats.numEdges ?? "–"}</div>
                      <div className="text-xs text-gray-500">Connections</div>
                    </div>
                    {stats.algebraicConnectivity != null && (
                      <div className="bg-emerald-50 rounded-xl p-3 text-center border border-emerald-100">
                        <div className="text-xl font-bold text-emerald-700">{stats.algebraicConnectivity.toFixed(3)}</div>
                        <div className="text-xs text-gray-500">Connectivity λ₂</div>
                      </div>
                    )}
                    {stats.connectedComponents != null && (
                      <div className="bg-amber-50 rounded-xl p-3 text-center border border-amber-100">
                        <div className="text-xl font-bold text-amber-700">{stats.connectedComponents}</div>
                        <div className="text-xs text-gray-500">Components</div>
                      </div>
                    )}
                  </div>

                  {stats.insights && Object.entries(stats.insights).map(([key, val]) => {
                    if (!val) return null;
                    const insightVal = val as { rating?: string; type?: string; description: string };
                    const label = insightVal.rating ?? insightVal.type ?? "";
                    const desc  = insightVal.description;
                    const icons: Record<string, ReactNode> = {
                      curriculumCohesion:  <Zap           className="size-3.5 text-violet-500" />,
                      bottleneckRisk:      <AlertTriangle className="size-3.5 text-amber-500"  />,
                      prerequisiteLoad:    <BarChart3     className="size-3.5 text-blue-500"   />,
                      curriculumShape:     <Layers        className="size-3.5 text-emerald-500"/>,
                    };
                    return (
                      <Alert key={key} className="py-2">
                        <AlertDescription>
                          <div className="flex items-center gap-1.5 font-semibold text-xs mb-0.5">
                            {icons[key] ?? null}
                            {label}
                          </div>
                          <p className="text-xs text-gray-600">{desc}</p>
                        </AlertDescription>
                      </Alert>
                    );
                  })}
                </div>
              ) : (
                <p className="text-sm text-gray-400 text-center py-8">No insights available</p>
              )}
            </TabsContent>

            {/* ── Next Up Tab ── */}
            <TabsContent value="next" className="flex-1 overflow-y-auto px-3 pb-4 mt-3">
              {recs.length > 0 ? (
                <div className="space-y-2">
                  {recs.map((rec, idx) => {
                    const { pct, col, text } = diffBar(rec.difficulty ?? 0.5);
                    return (
                      <Card
                        key={idx}
                        className="cursor-pointer hover:shadow-md transition-all"
                        onClick={() => { setSelectedId(rec.id); setActiveTab("detail"); }}
                      >
                        <CardContent className="pt-3 pb-3 px-3">
                          <div className="flex items-start justify-between gap-2 mb-2">
                            <div className="flex-1 min-w-0">
                              <div className="font-semibold text-sm truncate">{rec.name}</div>
                              <div className="text-xs text-gray-500 mt-0.5 line-clamp-2">{rec.reason}</div>
                            </div>
                            <div className="shrink-0 text-right">
                              <div className={`text-sm font-bold ${text}`}>{pct}%</div>
                              <div className="text-[10px] text-gray-400">difficulty</div>
                            </div>
                          </div>
                          <div className="w-full bg-gray-100 rounded-full h-1.5 mb-2">
                            <div className={`h-1.5 rounded-full ${col}`} style={{ width: `${pct}%` }} />
                          </div>
                          <Button
                            size="sm"
                            className="w-full bg-emerald-600 hover:bg-emerald-700 h-7 text-xs"
                            onClick={(e) => { e.stopPropagation(); masterTopic(rec.id); }}
                          >
                            Mark Mastered
                          </Button>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-gray-400 py-16 text-center">
                  <Target className="size-12 mb-3 opacity-25" />
                  <p className="text-sm font-medium">No recommendations yet</p>
                  <p className="text-xs mt-1">Master a few topics to unlock personalized next-step suggestions</p>
                </div>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </div>

      {/* ── Add Topic Modal ── */}
      {addOpen && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <Card className="w-full max-w-sm shadow-2xl">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Add Related Topic</CardTitle>
                <button onClick={() => setAddOpen(false)} className="text-gray-400 hover:text-gray-600">
                  <X className="size-4" />
                </button>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                Enter a topic name — NeuroMap will scrape it and merge it into the current graph.
              </p>
            </CardHeader>
            <CardContent className="space-y-3">
              <Input
                placeholder="e.g., Neural Networks, Statistics…"
                value={newTopic}
                onChange={(e) => setNewTopic(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !addingTopic && handleAddTopic()}
                autoFocus
              />
              <div className="flex gap-2">
                <Button variant="outline" className="flex-1" onClick={() => setAddOpen(false)} disabled={addingTopic}>
                  Cancel
                </Button>
                <Button
                  className="flex-1 bg-violet-600 hover:bg-violet-700"
                  onClick={handleAddTopic}
                  disabled={addingTopic || !newTopic.trim()}
                >
                  {addingTopic
                    ? <><Loader2 className="size-4 mr-2 animate-spin" />Scraping…</>
                    : <><Plus className="size-4 mr-2" />Add</>
                  }
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
