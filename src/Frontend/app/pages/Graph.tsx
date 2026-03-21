import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  useNodesState,
  useEdgesState,
  MarkerType,
  Panel,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useTopics } from "../context/TopicsContext";
import { Button } from "../components/ui/button";
import { Brain, Home, Route as RouteIcon, ExternalLink, X, ArrowRight, Loader2 } from "lucide-react";
import { NeuroMapLogo } from "../components/NeuroMapLogo";
import { Badge } from "../components/ui/badge";
import { toast } from "sonner";

const nodeWidth = 200;
const nodeHeight = 120;

export function Graph() {
  const { topics, relations, updateTopic } = useTopics();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedTopicId, setSelectedTopicId] = useState<string | null>(null);
  const [showOnlyAiImported, setShowOnlyAiImported] = useState(false);
  const [loadingResources, setLoadingResources] = useState(false);
  const [gnnScores, setGnnScores] = useState<Record<string, number>>({});
  const [acoPath, setAcoPath] = useState<Array<{ name: string; order: number; reason: string }>>([]);
  const [pathLoading, setPathLoading] = useState(false);

  const visibleTopics = showOnlyAiImported
    ? topics.filter((t) => t.importedFromAi)
    : topics;

  const selectedTopic = selectedTopicId
    ? topics.find((t) => t.id === selectedTopicId) ?? null
    : null;
  const selectedTopicGnnScore = selectedTopic
    ? gnnScores[selectedTopic.id] ?? selectedTopic.difficultyScore
    : undefined;

  const handleNodeClick = useCallback(async (nodeId: string) => {
    setSelectedTopicId(nodeId);
    const topic = topics.find((t) => t.id === nodeId);
    if (!topic) return;
    if (topic.resources && topic.resources.length > 0) return;

    setLoadingResources(true);
    try {
      const res = await fetch("/api/sub-graph", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic: topic.name }),
      });
      if (!res.ok) return;
      const data = await res.json();
      const nodes = Array.isArray(data.nodes) ? data.nodes : [];
      const normalizedName = topic.name.trim().toLowerCase();
      const match = nodes.find((n: any) => {
        const label = String(n?.data?.label ?? "").trim().toLowerCase();
        const original = String(n?.data?.originalName ?? "").trim().toLowerCase();
        return label === normalizedName || original === normalizedName;
      }) ?? nodes[0];

      const resources = Array.isArray(match?.data?.resources)
        ? match.data.resources
            .filter((r: any) => r && typeof r === "object" && typeof r.url === "string" && r.url.trim())
            .map((r: any) => ({
              title: String(r.title ?? "Learning resource"),
              url: String(r.url),
              source: String(r.source ?? ""),
              type: String(r.type ?? "link"),
            }))
        : [];

      if (resources.length > 0) {
        updateTopic(topic.id, { resources });
      }
    } catch {
      toast.error("Could not load topic resources right now");
    } finally {
      setLoadingResources(false);
    }
  }, [topics, updateTopic]);

  useEffect(() => {
    if (topics.length === 0) {
      setGnnScores({});
      return;
    }

    const fetchOverallDifficulty = async () => {
      try {
        const res = await fetch("/api/overall-difficulty", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ topics, relations }),
        });
        if (!res.ok) {
          setGnnScores({});
          return;
        }
        const data = await res.json();
        const raw = (data?.difficulties ?? {}) as Record<string, unknown>;
        const normalized = Object.fromEntries(
          Object.entries(raw)
            .filter(([, v]) => typeof v === "number" && Number.isFinite(v))
            .map(([k, v]) => [k, Number(v)])
        ) as Record<string, number>;
        setGnnScores(normalized);
      } catch {
        setGnnScores({});
      }
    };

    void fetchOverallDifficulty();
  }, [topics, relations]);

  useEffect(() => {
    if (visibleTopics.length === 0) {
      setNodes([]);
      setEdges([]);
      return;
    }

    // Create nodes with automatic layout
    const newNodes: Node[] = visibleTopics.map((topic, index) => {
      // Circular layout
      const angle = (index / visibleTopics.length) * 2 * Math.PI;
      const radius = Math.max(250, visibleTopics.length * 30);
      const x = Math.cos(angle) * radius + 400;
      const y = Math.sin(angle) * radius + 300;

      const difficultyColor = {
        beginner: "bg-green-100 border-green-300",
        intermediate: "bg-yellow-100 border-yellow-300",
        advanced: "bg-red-100 border-red-300",
      }[topic.difficulty];
      const gnnScore = gnnScores[topic.id] ?? topic.difficultyScore;

      return {
        id: topic.id,
        type: "default",
        position: { x, y },
        data: {
          label: (
            <div className="p-3">
              <div className="font-medium mb-2 text-sm leading-tight">{topic.name}</div>
              <div className="flex flex-wrap gap-1">
                <Badge variant="secondary" className="text-xs px-1.5 py-0">
                  {topic.category}
                </Badge>
                <Badge className={`text-xs px-1.5 py-0 ${difficultyColor}`} variant="outline">
                  {topic.difficulty}
                </Badge>
                {typeof gnnScore === "number" && (
                  <Badge variant="outline" className="text-xs px-1.5 py-0 border-violet-300 text-violet-700">
                    GNN {(gnnScore * 100).toFixed(0)}%
                  </Badge>
                )}
              </div>
            </div>
          ),
        },
        style: {
          width: nodeWidth,
          borderRadius: "12px",
          border: "2px solid #e5e7eb",
          background: "white",
          boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)",
        },
      };
    });

    setNodes(newNodes);

    const visibleIds = new Set(visibleTopics.map((t) => t.id));

    // Create edges
    const newEdges: Edge[] = relations
      .filter((relation) => visibleIds.has(relation.source) && visibleIds.has(relation.target))
      .map((relation) => {
      const edgeStyle = {
        prerequisite: {
          color: "#7c3aed", // violet
          label: "prerequisite",
          animated: true,
        },
        related: {
          color: "#3b82f6", // blue
          label: "related",
          animated: false,
        },
        overlap: {
          color: "#10b981", // emerald
          label: "overlap",
          animated: false,
        },
        hierarchical: {
          color: "#f59e0b", // amber
          label: "hierarchical",
          animated: true,
        },
      }[relation.type];

      return {
        id: relation.id,
        source: relation.source,
        target: relation.target,
        type: relation.type === "prerequisite" || relation.type === "hierarchical" ? "default" : "default",
        animated: edgeStyle.animated,
        style: { stroke: edgeStyle.color, strokeWidth: 2 },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: edgeStyle.color,
        },
        label: edgeStyle.label,
        labelStyle: { fill: edgeStyle.color, fontSize: 10 },
        labelBgStyle: { fill: "white" },
      };
    });

    setEdges(newEdges);
  }, [visibleTopics, relations, setNodes, setEdges, gnnScores]);

  useEffect(() => {
    if (topics.length === 0) {
      setAcoPath([]);
      return;
    }

    const fetchAcoPath = async () => {
      setPathLoading(true);
      try {
        const res = await fetch("/api/aco-path", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ topics, relations }),
        });
        if (!res.ok) {
          setAcoPath([]);
          return;
        }
        const data = await res.json();
        const steps = Array.isArray(data.path) ? data.path : [];
        setAcoPath(
          steps
            .map((s: any) => ({
              name: String(s.name ?? ""),
              order: Number(s.order) || 0,
              reason: String(s.reason ?? ""),
            }))
            .filter((s: { name: string; order: number; reason: string }) => s.name.length > 0)
            .sort((a: { order: number }, b: { order: number }) => a.order - b.order)
        );
      } catch {
        setAcoPath([]);
      } finally {
        setPathLoading(false);
      }
    };

    void fetchAcoPath();
  }, [topics, relations]);

  if (topics.length === 0) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-violet-50 via-white to-blue-50 flex items-center justify-center">
        <div className="text-center">
          <Brain className="size-16 mx-auto mb-4 text-gray-300" />
          <h2 className="font-semibold mb-2">No Topics Yet</h2>
          <p className="text-gray-600 mb-6">Add some topics in the workspace to see your knowledge graph</p>
          <Link to="/workspace">
            <Button className="bg-violet-600 hover:bg-violet-700">Go to Workspace</Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <div className="bg-white border-b shadow-sm z-20">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <Link to="/" className="flex items-center gap-2">
              <NeuroMapLogo className="size-8" />
              <span className="font-bold">NeuroMap</span>
            </Link>
            <div className="flex items-center gap-2">
              <Link to="/workspace">
                <Button variant="outline" size="sm">
                  <Home className="size-4 mr-2" />
                  Workspace
                </Button>
              </Link>
              <Link to="/path">
                <Button variant="outline" size="sm">
                  <RouteIcon className="size-4 mr-2" />
                  Learning Path
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* Graph */}
      <div className="flex-1 relative">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={(_, node) => { void handleNodeClick(node.id); }}
          fitView
          attributionPosition="bottom-left"
        >
          <Background />
          <Controls />
          <MiniMap 
            nodeColor={(node) => {
              const topic = topics.find(t => t.id === node.id);
              if (!topic) return "#e5e7eb";
              return {
                beginner: "#bbf7d0",
                intermediate: "#fef08a",
                advanced: "#fecaca",
              }[topic.difficulty];
            }}
            maskColor="rgba(0, 0, 0, 0.1)"
          />

          <Panel position="top-left" className="bg-white rounded-lg shadow-lg p-4 m-4 w-[320px] max-h-[70vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-sm">Learning Path</h3>
              <Badge variant="default" className="text-[10px]">ACO</Badge>
            </div>

            {pathLoading ? (
              <div className="flex items-center gap-2 text-xs text-gray-500 py-2">
                <Loader2 className="size-3.5 animate-spin" />
                Building optimized path...
              </div>
            ) : acoPath.length > 0 ? (
              <div className="space-y-1.5">
                {acoPath.map((step) => {
                  const topic = topics.find((t) => t.name === step.name);
                  const isSelected = topic?.id === selectedTopicId;
                  return (
                    <button
                      key={`aco-step-${step.order}-${step.name}`}
                      className={`w-full text-left p-2 rounded-md border transition-colors ${
                        isSelected
                          ? "bg-violet-50 border-violet-300"
                          : "bg-white border-gray-200 hover:bg-violet-50 hover:border-violet-200"
                      }`}
                      onClick={() => {
                        if (topic) {
                          setSelectedTopicId(topic.id);
                        } else {
                          toast.error("This topic is not currently visible in the graph filter.");
                        }
                      }}
                    >
                      <div className="flex items-center gap-2">
                        <span className="size-5 rounded-full bg-violet-100 text-violet-700 text-[10px] font-bold flex items-center justify-center shrink-0">
                          {step.order}
                        </span>
                        <span className="text-xs font-medium truncate">{step.name}</span>
                      </div>
                      {step.reason && (
                        <div className="ml-7 mt-0.5 text-[10px] text-gray-400 truncate flex items-center gap-1">
                          <ArrowRight className="size-3 shrink-0" />
                          {step.reason}
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            ) : (
              <p className="text-xs text-gray-400">No optimized path available yet.</p>
            )}
          </Panel>
          
          <Panel position="top-right" className="bg-white rounded-lg shadow-lg p-4 m-4">
            <h3 className="font-semibold mb-3 text-sm">Relationship Types</h3>
            <div className="mb-3 flex gap-1.5">
              <Button
                size="sm"
                variant={showOnlyAiImported ? "outline" : "default"}
                className="h-7 text-[11px]"
                onClick={() => setShowOnlyAiImported(false)}
              >
                All Topics
              </Button>
              <Button
                size="sm"
                variant={showOnlyAiImported ? "default" : "outline"}
                className="h-7 text-[11px]"
                onClick={() => setShowOnlyAiImported(true)}
              >
                AI Imported
              </Button>
            </div>
            <div className="space-y-2 text-xs">
              <div className="flex items-center gap-2">
                <div className="w-8 h-0.5 bg-violet-600" />
                <span>Prerequisite</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-8 h-0.5 bg-blue-600" />
                <span>Related</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-8 h-0.5 bg-emerald-600" />
                <span>Overlap</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-8 h-0.5 bg-amber-600" />
                <span>Hierarchical</span>
              </div>
            </div>
            {showOnlyAiImported && visibleTopics.length === 0 && (
              <p className="text-[11px] text-gray-400 mt-3">No AI-imported topics yet.</p>
            )}
          </Panel>

          {selectedTopic && (
            <Panel position="bottom-right" className="bg-white rounded-lg shadow-lg p-4 m-4 w-[340px] max-h-[60vh] overflow-y-auto">
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="min-w-0">
                  <h3 className="font-semibold text-sm truncate">{selectedTopic.name}</h3>
                  <div className="flex gap-1.5 mt-1">
                    <Badge variant="secondary" className="text-[10px]">{selectedTopic.category}</Badge>
                    <Badge variant="outline" className="text-[10px]">{selectedTopic.difficulty}</Badge>
                    {typeof selectedTopicGnnScore === "number" && (
                      <Badge variant="outline" className="text-[10px] border-violet-300 text-violet-700">
                        GNN {(selectedTopicGnnScore * 100).toFixed(0)}%
                      </Badge>
                    )}
                  </div>
                </div>
                <Button variant="ghost" size="sm" onClick={() => setSelectedTopicId(null)}>
                  <X className="size-4" />
                </Button>
              </div>

              {selectedTopic.description && (
                <p className="text-xs text-gray-600 mb-3 leading-relaxed">{selectedTopic.description}</p>
              )}

              {selectedTopic.resources && selectedTopic.resources.length > 0 ? (
                <div className="space-y-1.5">
                  <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide">Learning resources</p>
                  {selectedTopic.resources.map((r, idx) => (
                    <a
                      key={`${selectedTopic.id}-resource-${idx}`}
                      href={r.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-2 p-2 rounded-md border hover:bg-violet-50 hover:border-violet-200"
                    >
                      <ExternalLink className="size-3 text-violet-500 shrink-0" />
                      <div className="min-w-0">
                        <div className="text-xs font-medium text-gray-800 truncate">{r.title}</div>
                        <div className="text-[10px] text-gray-400 truncate">{r.source || r.type || "resource"}</div>
                      </div>
                    </a>
                  ))}
                </div>
              ) : loadingResources ? (
                <p className="text-xs text-gray-400">Finding learning links…</p>
              ) : (
                <p className="text-xs text-gray-400">No learning links available for this topic yet.</p>
              )}
            </Panel>
          )}
        </ReactFlow>
      </div>
    </div>
  );
}