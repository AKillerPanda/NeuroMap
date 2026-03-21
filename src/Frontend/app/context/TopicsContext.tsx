import React, { createContext, useContext, useState, ReactNode } from "react";

export type RelationType = "prerequisite" | "related" | "overlap" | "hierarchical";

export interface Topic {
  id: string;
  name: string;
  description: string;
  category: string;
  difficulty: "beginner" | "intermediate" | "advanced";
  difficultyScore?: number;
  status: "not-started" | "in-progress" | "completed";
  resources?: Array<{ title: string; url: string; source?: string; type?: string }>;
  importedFromAi?: boolean;
}

export interface TopicRelation {
  id: string;
  source: string;
  target: string;
  type: RelationType;
  strength: number; // 0-1
}

interface TopicsContextType {
  topics: Topic[];
  relations: TopicRelation[];
  addTopic: (topic: Omit<Topic, "id">) => void;
  removeTopic: (id: string) => void;
  updateTopic: (id: string, updates: Partial<Topic>) => void;
  generateRelations: () => void;
  clearAll: () => void;
  loadDemoData: () => void;
  exportData: () => string;
  importData: (jsonData: string) => boolean;
  addAiGraphToNeuroMap: (graph: {
    nodes: Array<{ id: string; data?: Record<string, unknown> }>;
    edges: Array<{ source: string; target: string }>;
  }) => { addedTopics: number; addedRelations: number };
}

const TopicsContext = createContext<TopicsContextType | undefined>(undefined);

export function TopicsProvider({ children }: { children: ReactNode }) {
  const [topics, setTopics] = useState<Topic[]>(() => {
    // Load from localStorage on init
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("neuromap-topics");
      return saved ? JSON.parse(saved) : [];
    }
    return [];
  });
  const [relations, setRelations] = useState<TopicRelation[]>(() => {
    // Load from localStorage on init
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("neuromap-relations");
      return saved ? JSON.parse(saved) : [];
    }
    return [];
  });

  const topicsRef = React.useRef<Topic[]>(topics);
  const relationsRef = React.useRef<TopicRelation[]>(relations);

  // Save to localStorage whenever topics or relations change
  React.useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem("neuromap-topics", JSON.stringify(topics));
    }
    topicsRef.current = topics;
  }, [topics]);

  React.useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem("neuromap-relations", JSON.stringify(relations));
    }
    relationsRef.current = relations;
  }, [relations]);

  const addTopic = (topic: Omit<Topic, "id">) => {
    const newTopic: Topic = {
      ...topic,
      id: `topic-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
    };
    setTopics((prev) => [...prev, newTopic]);
  };

  const removeTopic = (id: string) => {
    setTopics((prev) => prev.filter((t) => t.id !== id));
    setRelations((prev) =>
      prev.filter((r) => r.source !== id && r.target !== id)
    );
  };

  const updateTopic = (id: string, updates: Partial<Topic>) => {
    setTopics((prev) =>
      prev.map((t) => (t.id === id ? { ...t, ...updates } : t))
    );
  };

  // AI-like algorithm to generate relationships between topics
  const generateRelations = () => {
    const newRelations: TopicRelation[] = [];
    const topicPairs: [Topic, Topic][] = [];

    // Create all possible pairs
    for (let i = 0; i < topics.length; i++) {
      for (let j = i + 1; j < topics.length; j++) {
        topicPairs.push([topics[i], topics[j]]);
      }
    }

    topicPairs.forEach(([topic1, topic2]) => {
      const relationId = `rel-${topic1.id}-${topic2.id}`;
      
      // Same category = hierarchical or overlap
      if (topic1.category === topic2.category) {
        if (topic1.difficulty !== topic2.difficulty) {
          // Different difficulty levels = prerequisite
          const [easier, harder] =
            topic1.difficulty === "beginner"
              ? [topic1, topic2]
              : topic2.difficulty === "beginner"
              ? [topic2, topic1]
              : topic1.difficulty === "intermediate"
              ? [topic1, topic2]
              : [topic2, topic1];

          newRelations.push({
            id: relationId,
            source: easier.id,
            target: harder.id,
            type: "prerequisite",
            strength: 0.8,
          });
        } else {
          // Same difficulty = overlap
          newRelations.push({
            id: relationId,
            source: topic1.id,
            target: topic2.id,
            type: "overlap",
            strength: 0.6,
          });
        }
      } else {
        // Different categories = related (interdisciplinary)
        // Check for common keywords
        const words1 = topic1.name.toLowerCase().split(/\s+/);
        const words2 = topic2.name.toLowerCase().split(/\s+/);
        const commonWords = words1.filter((w) => words2.includes(w));

        if (commonWords.length > 0 || Math.random() > 0.7) {
          newRelations.push({
            id: relationId,
            source: topic1.id,
            target: topic2.id,
            type: "related",
            strength: 0.4,
          });
        }
      }
    });

    setRelations(newRelations);
  };

  const clearAll = () => {
    setTopics([]);
    setRelations([]);
  };

  const loadDemoData = () => {
    // Import demo data dynamically
    import("../utils/demoData").then(({ demoTopics }) => {
      const newTopics = demoTopics.map((topic, index) => ({
        ...topic,
        id: `demo-topic-${index}-${Date.now()}`,
      }));
      setTopics(newTopics);
      setRelations([]); // Clear existing relations
    });
  };

  const exportData = () => {
    return JSON.stringify({ topics, relations }, null, 2);
  };

  const importData = (jsonData: string): boolean => {
    try {
      const data = JSON.parse(jsonData);
      if (data.topics && Array.isArray(data.topics)) {
        setTopics(data.topics);
        setRelations(data.relations || []);
        return true;
      }
      return false;
    } catch (error) {
      return false;
    }
  };

  const addAiGraphToNeuroMap = (graph: {
    nodes: Array<{ id: string; data?: Record<string, unknown> }>;
    edges: Array<{ source: string; target: string }>;
  }): { addedTopics: number; addedRelations: number } => {
    const levelToDifficulty = (level?: string): Topic["difficulty"] => {
      const v = (level ?? "").toLowerCase();
      if (v === "foundational") return "beginner";
      if (v === "advanced" || v === "expert") return "advanced";
      return "intermediate";
    };

    const incomingIdToTopicId = new Map<string, string>();
    const topicsToAdd: Topic[] = [];
    const newRelations: TopicRelation[] = [];

    // Process nodes first to build the mapping and collect topics to add
    const existingByName = new Map(
      topics.map((t) => [t.name.trim().toLowerCase(), t.id] as const)
    );

    for (const n of graph.nodes) {
      const raw = (n.data ?? {}) as Record<string, unknown>;
      const label = String(raw.originalName ?? raw.label ?? "").trim();
      if (!label) continue;

      const key = label.toLowerCase();
      const existingId = existingByName.get(key);
      if (existingId) {
        incomingIdToTopicId.set(n.id, existingId);
        continue;
      }

      const newId = `topic-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      incomingIdToTopicId.set(n.id, newId);
      existingByName.set(key, newId);

      const sourceSkill = String(raw.sourceSkill ?? "AI Graph").trim();
      const resourcesRaw = Array.isArray(raw.resources) ? raw.resources : [];
      const resources = resourcesRaw
        .filter((r): r is Record<string, unknown> => !!r && typeof r === "object")
        .map((r) => ({
          title: String(r.title ?? "Learning resource"),
          url: String(r.url ?? "").trim(),
          source: String(r.source ?? ""),
          type: String(r.type ?? "link"),
        }))
        .filter((r) => r.url.length > 0);

      topicsToAdd.push({
        id: newId,
        name: label,
        description: String(raw.description ?? "").trim(),
        category: sourceSkill || "AI Graph",
        difficulty: levelToDifficulty(String(raw.level ?? "")),
        difficultyScore: (typeof raw.difficultyScore === "number" && Number.isFinite(raw.difficultyScore))
          ? raw.difficultyScore
          : undefined,
        status: "not-started",
        resources,
        importedFromAi: true,
      });
    }

    // Process edges to build relations
    const existingRelSet = new Set(
      relations.map((r) => `${r.source}->${r.target}:${r.type}`)
    );

    for (const e of graph.edges) {
      const source = incomingIdToTopicId.get(e.source);
      const target = incomingIdToTopicId.get(e.target);
      if (!source || !target || source === target) continue;
      const key = `${source}->${target}:prerequisite`;
      if (existingRelSet.has(key)) continue;
      existingRelSet.add(key);
      newRelations.push({
        id: `rel-${source}-${target}`,
        source,
        target,
        type: "prerequisite",
        strength: 0.8,
      });
    }

    // Now update state and return correct counts
    setTopics((prev) => (topicsToAdd.length > 0 ? [...prev, ...topicsToAdd] : prev));
    setRelations((prev) => (newRelations.length > 0 ? [...prev, ...newRelations] : prev));

    return { addedTopics: topicsToAdd.length, addedRelations: newRelations.length };
  };

  return (
    <TopicsContext.Provider
      value={{
        topics,
        relations,
        addTopic,
        removeTopic,
        updateTopic,
        generateRelations,
        clearAll,
        loadDemoData,
        exportData,
        importData,
        addAiGraphToNeuroMap,
      }}
    >
      {children}
    </TopicsContext.Provider>
  );
}

export function useTopics() {
  const context = useContext(TopicsContext);
  if (!context) {
    throw new Error("useTopics must be used within TopicsProvider");
  }
  return context;
}