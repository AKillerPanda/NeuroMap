/**
 * EnhancedGraph.tsx
 * 
 * NeuroMap Topological Spectral Knowledge Graph Visualization
 * 
 * Features:
 * - Spectral Laplacian layout (Fiedler vector-based positioning)
 * - Real-time mastery tracking with prerequisite validation
 * - GAT-based difficulty prediction with recommendations
 * - Multiple learning paths (Full / Optimal ACO / Quick Start)
 * - Spectral clustering for color-coded topic groups
 * - Learning insights (curriculum cohesion, bottleneck risk, etc.)
 */

import { useEffect, useState, useCallback } from "react";
import { useParams, Link } from "react-router";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  useNodesState,
  useEdgesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Brain, Home, BarChart3, Zap, AlertTriangle, TrendingUp } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";

interface TopicNode {
  id: string;
  name: string;
  level: string;
  difficulty: string;
  prerequisites: string[];
  unlocks: string[];
  depth: number;
  cluster: number;
  resources?: Array<{ title: string; url: string; source: string; type: string }>;
  estimatedMinutes?: number;
  mastered: boolean;
  spectralX?: number;
  spectralY?: number;
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
    unlocks: string[];
    reason: string;
  }>;
}

interface CurriculumStats {
  numTopics: number;
  numEdges: number;
  algebraicConnectivity?: number;
  spectralGap?: number;
  connectedComponents?: number;
  avgOutDegree?: number;
  avgInDegree?: number;
  maxOutDegree?: number;
  maxInDegree?: number;
  insights?: {
    curriculumCohesion?: { rating: string; description: string; value?: number };
    bottleneckRisk?: { rating: string; description: string; chokepoints?: string[] };
    prerequisiteLoad?: { rating: string; description: string };
    curriculumShape?: { type: string; description: string; depth?: number };
  };
}

export function EnhancedGraph() {
  const { skill } = useParams<{ skill: string }>();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesState] = useEdgesState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [topics, setTopics] = useState<Record<string, TopicNode>>({});
  const [paths, setPaths] = useState<LearningPath[]>([]);
  const [stats, setStats] = useState<CurriculumStats | null>(null);
  const [selectedPath, setSelectedPath] = useState("path-full");
  const [recommendations, setRecommendations] = useState<any[]>([]);
  const [progress, setProgress] = useState(0);
  const [mastered, setMastered] = useState<Set<string>>(new Set());

  // Fetch & initialize graph
  useEffect(() => {
    if (!skill) return;
    fetchGraph();
  }, [skill]);

  const fetchGraph = async () => {
    try {
      setLoading(true);
      const response = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ skill }),
      });
      if (!response.ok) throw new Error(`Failed to generate graph: ${response.statusText}`);

      const data = await response.json();

      // Build topic map
      const topicsMap: Record<string, TopicNode> = {};
      data.nodes.forEach((n: any) => {
        topicsMap[n.id] = {
          id: n.id,
          name: n.data.label,
          level: n.data.level,
          difficulty: n.data.difficulty,
          prerequisites: n.data.prerequisites || [],
          unlocks: n.data.unlocks || [],
          depth: n.data.depth || 0,
          cluster: n.data.cluster || 0,
          resources: n.data.resources || [],
          estimatedMinutes: n.data.estimatedMinutes || 90,
          mastered: n.data.mastered,
        };
      });
      setTopics(topicsMap);
      setPaths(data.paths || []);
      setStats(data.stats);

      // Convert nodes to ReactFlow format with spectral positions
      const flowNodes: Node[] = data.nodes.map((n: any) => {
        const clusterColors = [
          "bg-blue-100 border-blue-300",
          "bg-green-100 border-green-300",
          "bg-purple-100 border-purple-300",
          "bg-orange-100 border-orange-300",
          "bg-pink-100 border-pink-300",
        ];
        const colorClass = clusterColors[n.data.cluster % clusterColors.length];

        return {
          id: n.id,
          type: "default",
          position: n.position,
          data: {
            label: (
              <div className="p-2 text-center">
                <div className="font-semibold text-sm mb-1 truncate">{n.data.label}</div>
                <div className="flex gap-1 justify-center flex-wrap">
                  <Badge variant="secondary" className="text-xs">
                    {n.data.level}
                  </Badge>
                  <Badge className={`text-xs ${colorClass}`}>{n.data.difficulty}</Badge>
                </div>
              </div>
            ),
          },
          style: {
            width: 180,
            borderRadius: "8px",
            border: n.data.mastered ? "3px solid #10b981" : "2px solid #d1d5db",
            background: n.data.mastered ? "#ecfdf5" : "white",
            boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
          },
        };
      });

      const flowEdges: Edge[] = data.edges.map((e: any) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        animated: e.animated,
        markerEnd: e.markerEnd,
        style: e.style,
      }));

      setNodes(flowNodes);
      setEdges(flowEdges);

      // Fetch difficulty & recommendations
      const diffResponse = await fetch(`/api/difficulty/${encodeURIComponent(skill)}`);
      if (diffResponse.ok) {
        const diffData = await diffResponse.json();
        setRecommendations(diffData.recommendations || []);
      }

      // Calculate progress
      const masteredCount = Object.values(topicsMap).filter((t) => t.mastered).length;
      const totalCount = Object.keys(topicsMap).length;
      setProgress(totalCount > 0 ? masteredCount / totalCount : 0);
      setMastered(new Set(Object.entries(topicsMap).filter(([_, t]) => t.mastered).map(([id, _]) => id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleMasterTopic = async (topicId: string) => {
    try {
      const response = await fetch("/api/master", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ skill, topicId }),
      });

      if (!response.ok) throw new Error("Failed to master topic");

      const data = await response.json();
      if (data.success) {
        setProgress(data.progress);
        const newMastered = new Set(mastered);
        newMastered.add(topicId);
        setMastered(newMastered);

        // Update node colors
        setNodes((nds) =>
          nds.map((n) =>
            n.id === topicId
              ? {
                  ...n,
                  style: {
                    ...n.style,
                    background: "#ecfdf5",
                    border: "3px solid #10b981",
                  },
                }
              : n
          )
        );
      } else {
        alert(`Cannot master: ${data.reason}`);
      }
    } catch (err) {
      console.error("Failed to master topic:", err);
      alert("Failed to master topic");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <Brain className="size-16 mx-auto mb-4 animate-pulse text-violet-600" />
          <p className="text-gray-600">Building your knowledge graph...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-red-50 to-white flex items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-red-600">
              <AlertTriangle className="size-5" />
              Error
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-gray-600 mb-4">{error}</p>
            <Link to="/workspace">
              <Button className="w-full bg-violet-600 hover:bg-violet-700">Back to Workspace</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Find the current path data
  const currentPathData = paths.find((p) => p.id === selectedPath);
  const pathTopics = currentPathData?.steps || [];

  return (
    <div className="h-screen flex flex-col bg-gradient-to-br from-gray-50 to-white">
      {/* Header */}
      <div className="bg-white border-b shadow-sm z-20 p-4">
        <div className="flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <Brain className="size-8 text-violet-600" />
            <span className="font-bold">NeuroMap — {skill}</span>
          </Link>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <TrendingUp className="size-4 text-green-600" />
              <span className="font-semibold text-sm">
                {(progress * 100).toFixed(0)}% Complete
              </span>
            </div>
            <Link to="/workspace">
              <Button variant="outline" size="sm">
                <Home className="size-4 mr-2" />
                Workspace
              </Button>
            </Link>
          </div>
        </div>
      </div>

      <div className="flex-1 flex gap-4 p-4 overflow-hidden">
        {/* Main Graph */}
        <div className="flex-1 rounded-lg border bg-white shadow-sm overflow-hidden">
          <ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesState={onEdgesState} fitView>
            <Background />
            <Controls />
            <MiniMap />
          </ReactFlow>
        </div>

        {/* Sidebar */}
        <div className="w-96 flex flex-col gap-4 overflow-y-auto">
          <Tabs defaultValue="paths" className="w-full h-full flex flex-col">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="paths">Paths</TabsTrigger>
              <TabsTrigger value="insights">Insights</TabsTrigger>
              <TabsTrigger value="recommend">Next Steps</TabsTrigger>
            </TabsList>

            <TabsContent value="paths" className="flex-1 overflow-y-auto">
              <div className="space-y-3 pr-2">
                {paths.map((path) => (
                  <Card
                    key={path.id}
                    className={`cursor-pointer transition-all ${
                      selectedPath === path.id
                        ? "ring-2 ring-violet-600 bg-violet-50"
                        : "hover:shadow-md"
                    }`}
                    onClick={() => setSelectedPath(path.id)}
                  >
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">{path.name}</CardTitle>
                      <p className="text-xs text-gray-600 mt-1">{path.description}</p>
                    </CardHeader>
                    <CardContent>
                      <div className="flex items-center justify-between text-xs">
                        <Badge>{path.duration}</Badge>
                        <Badge variant="outline">{path.difficulty}</Badge>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>

              {currentPathData && (
                <div className="mt-4 p-3 bg-gray-50 rounded-lg border">
                  <h4 className="font-semibold text-sm mb-3">Steps</h4>
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {pathTopics.map((step, idx) => (
                      <div
                        key={step.topicId}
                        className="p-2 bg-white rounded border-l-2 border-violet-600 text-xs cursor-pointer hover:bg-violet-50 transition-colors"
                        onClick={() => {
                          const el = document.getElementById(`node-${step.topicId}`);
                          if (el) el.scrollIntoView({ behavior: "smooth" });
                        }}
                      >
                        <div className="font-semibold">{step.reason}</div>
                        <div className="text-gray-600 mt-1">{step.name}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </TabsContent>

            <TabsContent value="insights" className="flex-1 overflow-y-auto">
              {stats?.insights && (
                <div className="space-y-3 pr-2">
                  {stats.insights.curriculumCohesion && (
                    <Alert>
                      <Zap className="h-4 w-4" />
                      <AlertDescription>
                        <div className="font-semibold">
                          Curriculum Cohesion: {stats.insights.curriculumCohesion.rating}
                        </div>
                        <p className="text-xs mt-1">{stats.insights.curriculumCohesion.description}</p>
                      </AlertDescription>
                    </Alert>
                  )}

                  {stats.insights.bottleneckRisk && (
                    <Alert>
                      <AlertTriangle className="h-4 w-4" />
                      <AlertDescription>
                        <div className="font-semibold">Bottleneck Risk: {stats.insights.bottleneckRisk.rating}</div>
                        <p className="text-xs mt-1">{stats.insights.bottleneckRisk.description}</p>
                      </AlertDescription>
                    </Alert>
                  )}

                  {stats.insights.prerequisiteLoad && (
                    <Alert>
                      <BarChart3 className="h-4 w-4" />
                      <AlertDescription>
                        <div className="font-semibold">Prerequisite Load: {stats.insights.prerequisiteLoad.rating}</div>
                        <p className="text-xs mt-1">{stats.insights.prerequisiteLoad.description}</p>
                      </AlertDescription>
                    </Alert>
                  )}
                </div>
              )}
            </TabsContent>

            <TabsContent value="recommend" className="flex-1 overflow-y-auto">
              <div className="space-y-2 pr-2">
                {recommendations.length > 0 ? (
                  recommendations.map((rec, idx) => (
                    <Card key={idx}>
                      <CardContent className="pt-4">
                        <div className="font-semibold text-sm">{rec.name}</div>
                        <div className="text-xs text-gray-600 mt-1">{rec.reason}</div>
                        <div className="flex items-center justify-between mt-3">
                          <Badge variant="outline" className="text-xs">
                            {(rec.difficulty * 100).toFixed(0)}% Difficulty
                          </Badge>
                          <Button
                            size="sm"
                            className="bg-green-600 hover:bg-green-700 text-xs"
                            onClick={() => handleMasterTopic(rec.id)}
                          >
                            Master
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  ))
                ) : (
                  <p className="text-sm text-gray-600 text-center py-4">
                    Learn more topics to get personalized recommendations!
                  </p>
                )}
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
