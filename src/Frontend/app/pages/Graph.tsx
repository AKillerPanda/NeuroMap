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
import { Brain, Home, Route as RouteIcon, ZoomIn, ZoomOut } from "lucide-react";
import { NeuroMapLogo } from "../components/NeuroMapLogo";
import { Badge } from "../components/ui/badge";

const nodeWidth = 200;
const nodeHeight = 120;

export function Graph() {
  const { topics, relations } = useTopics();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  useEffect(() => {
    if (topics.length === 0) return;

    // Create nodes with automatic layout
    const newNodes: Node[] = topics.map((topic, index) => {
      // Circular layout
      const angle = (index / topics.length) * 2 * Math.PI;
      const radius = Math.max(250, topics.length * 30);
      const x = Math.cos(angle) * radius + 400;
      const y = Math.sin(angle) * radius + 300;

      const difficultyColor = {
        beginner: "bg-green-100 border-green-300",
        intermediate: "bg-yellow-100 border-yellow-300",
        advanced: "bg-red-100 border-red-300",
      }[topic.difficulty];

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

    // Create edges
    const newEdges: Edge[] = relations.map((relation) => {
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
  }, [topics, relations, setNodes, setEdges]);

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
          
          <Panel position="top-right" className="bg-white rounded-lg shadow-lg p-4 m-4">
            <h3 className="font-semibold mb-3 text-sm">Relationship Types</h3>
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
          </Panel>
        </ReactFlow>
      </div>
    </div>
  );
}