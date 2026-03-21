import { useEffect, useState } from "react";
import { Link } from "react-router";
import { useTopics, Topic } from "../context/TopicsContext";
import { Button } from "../components/ui/button";
import { Brain, Home, Network, CheckCircle2, Circle, PlayCircle, ArrowRight } from "lucide-react";
import { NeuroMapLogo } from "../components/NeuroMapLogo";
import { Badge } from "../components/ui/badge";
import { Progress } from "../components/ui/progress";

interface PathStep {
  topic: Topic;
  order: number;
  prerequisites: Topic[];
  reason: string;
}

export function LearningPath() {
  const { topics, relations, updateTopic } = useTopics();
  const [learningPath, setLearningPath] = useState<PathStep[]>([]);

  useEffect(() => {
    if (topics.length === 0) return;

    // Generate an optimal learning path based on prerequisites and difficulty
    const path: PathStep[] = [];
    const processed = new Set<string>();
    const topicMap = new Map(topics.map((t) => [t.id, t]));

    // Helper function to get prerequisites for a topic
    const getPrerequisites = (topicId: string): Topic[] => {
      return relations
        .filter((r) => r.target === topicId && r.type === "prerequisite")
        .map((r) => topicMap.get(r.source))
        .filter((t): t is Topic => t !== undefined);
    };

    // Topological sort with difficulty consideration
    const sortedTopics = [...topics].sort((a, b) => {
      // First by difficulty
      const difficultyOrder = { beginner: 0, intermediate: 1, advanced: 2 };
      const diffDiff = difficultyOrder[a.difficulty] - difficultyOrder[b.difficulty];
      if (diffDiff !== 0) return diffDiff;
      
      // Then alphabetically
      return a.name.localeCompare(b.name);
    });

    // Build path
    let order = 1;
    for (const topic of sortedTopics) {
      if (!processed.has(topic.id)) {
        const prerequisites = getPrerequisites(topic.id).filter((p) =>
          processed.has(p.id)
        );

        let reason = "";
        if (prerequisites.length > 0) {
          reason = `Builds on: ${prerequisites.map((p) => p.name).join(", ")}`;
        } else if (topic.difficulty === "beginner") {
          reason = "Great starting point - foundational topic";
        } else if (topic.difficulty === "intermediate") {
          reason = "Intermediate level - requires some background";
        } else {
          reason = "Advanced topic - master basics first";
        }

        path.push({
          topic,
          order: order++,
          prerequisites,
          reason,
        });
        processed.add(topic.id);
      }
    }

    setLearningPath(path);
  }, [topics, relations]);

  const handleToggleStatus = (topicId: string, currentStatus: Topic["status"]) => {
    const newStatus =
      currentStatus === "not-started"
        ? "in-progress"
        : currentStatus === "in-progress"
        ? "completed"
        : "not-started";
    updateTopic(topicId, { status: newStatus });
  };

  const completedCount = topics.filter((t) => t.status === "completed").length;
  const progressPercentage = topics.length > 0 ? (completedCount / topics.length) * 100 : 0;

  const getStatusIcon = (status: Topic["status"]) => {
    switch (status) {
      case "completed":
        return <CheckCircle2 className="size-5 text-green-600" />;
      case "in-progress":
        return <PlayCircle className="size-5 text-blue-600" />;
      default:
        return <Circle className="size-5 text-gray-300" />;
    }
  };

  const getDifficultyColor = (diff: string) => {
    switch (diff) {
      case "beginner":
        return "bg-green-100 text-green-700 border-green-300";
      case "intermediate":
        return "bg-yellow-100 text-yellow-700 border-yellow-300";
      case "advanced":
        return "bg-red-100 text-red-700 border-red-300";
      default:
        return "bg-gray-100 text-gray-700";
    }
  };

  if (topics.length === 0) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-violet-50 via-white to-blue-50 flex items-center justify-center">
        <div className="text-center">
          <Brain className="size-16 mx-auto mb-4 text-gray-300" />
          <h2 className="font-semibold mb-2">No Topics Yet</h2>
          <p className="text-gray-600 mb-6">
            Add some topics in the workspace to generate a learning path
          </p>
          <Link to="/workspace">
            <Button className="bg-violet-600 hover:bg-violet-700">Go to Workspace</Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-violet-50 via-white to-blue-50">
      {/* Header */}
      <div className="bg-white border-b shadow-sm sticky top-0 z-10">
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
              <Link to="/graph">
                <Button variant="outline" size="sm">
                  <Network className="size-4 mr-2" />
                  View Graph
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </div>

      <div className="container mx-auto px-4 py-8 max-w-4xl">
        {/* Progress Overview */}
        <div className="bg-white rounded-2xl p-6 shadow-lg mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold">Your Learning Progress</h2>
            <span className="text-sm text-gray-600">
              {completedCount} of {topics.length} completed
            </span>
          </div>
          <Progress value={progressPercentage} className="h-3" />
          <div className="flex items-center gap-6 mt-4 text-sm">
            <div className="flex items-center gap-2">
              <Circle className="size-4 text-gray-300" />
              <span className="text-gray-600">
                {topics.filter((t) => t.status === "not-started").length} Not Started
              </span>
            </div>
            <div className="flex items-center gap-2">
              <PlayCircle className="size-4 text-blue-600" />
              <span className="text-gray-600">
                {topics.filter((t) => t.status === "in-progress").length} In Progress
              </span>
            </div>
            <div className="flex items-center gap-2">
              <CheckCircle2 className="size-4 text-green-600" />
              <span className="text-gray-600">{completedCount} Completed</span>
            </div>
          </div>
        </div>

        {/* Learning Path */}
        <div className="bg-white rounded-2xl p-6 shadow-lg">
          <h2 className="font-semibold mb-6">Recommended Learning Path</h2>
          <div className="space-y-6">
            {learningPath.map((step, index) => (
              <div key={step.topic.id}>
                <div className="flex gap-4">
                  {/* Order number */}
                  <div className="flex flex-col items-center">
                    <div className="size-10 rounded-full bg-violet-100 text-violet-700 font-semibold flex items-center justify-center flex-shrink-0">
                      {step.order}
                    </div>
                    {index < learningPath.length - 1 && (
                      <div className="w-0.5 flex-1 bg-gray-200 my-2" />
                    )}
                  </div>

                  {/* Content */}
                  <div className="flex-1 pb-4">
                    <div className="border rounded-xl p-4 hover:border-violet-300 transition-colors">
                      <div className="flex items-start justify-between gap-4 mb-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-3 mb-2">
                            <h3 className="font-medium">{step.topic.name}</h3>
                            <Badge
                              className={getDifficultyColor(step.topic.difficulty)}
                              variant="outline"
                            >
                              {step.topic.difficulty}
                            </Badge>
                          </div>
                          <p className="text-sm text-gray-600 mb-2">{step.reason}</p>
                          {step.topic.description && (
                            <p className="text-sm text-gray-500 italic">{step.topic.description}</p>
                          )}
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleToggleStatus(step.topic.id, step.topic.status)}
                        >
                          {getStatusIcon(step.topic.status)}
                        </Button>
                      </div>

                      {step.prerequisites.length > 0 && (
                        <div className="mt-3 pt-3 border-t">
                          <p className="text-xs text-gray-500 mb-2">Prerequisites:</p>
                          <div className="flex flex-wrap gap-2">
                            {step.prerequisites.map((prereq) => (
                              <Badge key={prereq.id} variant="secondary" className="text-xs">
                                {prereq.name}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Next Steps Suggestion */}
        {completedCount < topics.length && (
          <div className="mt-6 bg-blue-50 border border-blue-200 rounded-xl p-6">
            <h3 className="font-medium mb-2 text-blue-900">What to study next?</h3>
            <p className="text-sm text-blue-700 mb-4">
              {(() => {
                const nextTopic = learningPath.find((s) => s.topic.status !== "completed");
                return nextTopic
                  ? `We recommend starting with "${nextTopic.topic.name}". ${nextTopic.reason}`
                  : "Great job! You've completed all topics in your path.";
              })()}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}